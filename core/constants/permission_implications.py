"""Permission implications — what a coarse grant still covers after the split.

Why this map exists
-------------------
Each page family used to be gated by **one coarse permission**: ``rooms.manage``
guarded create, edit and delete alike.  The routes are now gated by the
granular strings (``rooms.create`` / ``rooms.edit`` / ``rooms.delete``) so an
account can hold exactly one of them.

Without this map that split would silently *revoke* every legacy coarse grant:
a role whose table still says ``rooms.manage`` would own no rooms door at all,
because no route asks for ``rooms.manage`` any more.  So the map states one
thing and nothing else:

    holding a coarse permission implies holding the fine ones it was split into.

Why it is its own file
----------------------
``core/constants/permissions.py`` is a plain literal table read directly by the
consistency tests, and ``security/authorization.py`` needs the closure.  Keeping
the map here means neither module has to import the other, so there is no
import cycle to reason about.

``exams.department_schedule`` is a key **and** an implication on purpose: the
head of department reaches it directly, and ``exams.manage`` implies it because
the exam department reached it through the coarse grant before the split.
"""

# /     /     >---- المفتاح: الصلاحية الخام. القيمة: ما تشمله بعد تفكيكها
# /     /     >---- إلى ديكوريتورات دقيقة (rooms.manage ← create/edit/delete).
PERMISSION_IMPLICATIONS: dict[str, tuple[str, ...]] = {
    'rooms.manage': ('rooms.view', 'rooms.create', 'rooms.edit', 'rooms.delete'),
    'exams.manage': ('exams.view', 'exams.period', 'exams.planning',
                     'exams.assign_room', 'exams.create', 'exams.edit',
                     'exams.delete', 'exams.department_schedule'),
    'exams.department_schedule': ('exams.view', 'exams.create', 'exams.edit',
                                  'exams.delete'),
}


# /     /     >---- الإغلاق até نقطة الثبات: الخوارزمية تعيد نفسها بعد
# /     /     >---- إضافة كل ما تنبّ عليه القيم المُضافة. هي الحالة الثابتة
# /     /     >---- الوحيدة التي تعني «لهذا الدور هذه الأبواب».
def expand_permissions(perms) -> set:
    """*perms* plus everything it implies, closed to a fixpoint.

    Idempotent (the result expands to itself) and total: anything that is not a
    permission string is dropped, never raised on, because this runs inside
    ``get_user_permissions`` where a bad session value must not 500 a page.
    """
    if perms is None:
        return set()
    # /     /     >---- سلسلة واحدة تُعامل كصلاحية واحدة لا كحروف
    if isinstance(perms, str):
        perms = (perms,)
    resolved = {str(p) for p in perms if p}
    pending = list(resolved)
    while pending:
        current = pending.pop()
        for implied in PERMISSION_IMPLICATIONS.get(current, ()):
            if implied not in resolved:
                resolved.add(implied)
                pending.append(implied)
    return resolved


def permission_implies(held: str, required: str) -> bool:
    """True when holding *held* is enough to pass a gate for *required*."""
    return required in expand_permissions({held})