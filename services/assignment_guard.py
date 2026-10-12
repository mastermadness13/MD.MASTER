# services/assignment_guard.py
# /     /     >---- حارس التفرد: يضمن ألا يشغل «المنصب الفريد» أكثر من عضو
# /     /     >---- فعّال في نطاقه (النظام كلّه أو كل قسم). التفرد قاعدة مطبّقة
# /     /     >---- على مستوى التكليف (عمود admin_assignment_types.uniqueness):
# /     /     >---- '' بلا قيد، 'global' شاغل واحد، 'department' لكل قسم.
"""Enforce at-most-one active holder for unique administrative assignments."""

# /     /     >---- التكليفات المرتبطة بآلية نقلٍ بتأكيد (رئيس القسم والعميد)
# /     /     >---- لا يوقفها الحارس بجدار صلب؛ مسار الاستبدال المعتمد الحالي
# /     /     >---- (confirm_replace_hod / confirm_dean_transfer) يتولى نقلها.
_EXEMPT_ROLE_CODES = frozenset({'head_of_department', 'dean'})

_RULE_COLUMNS = 'id, name, internal_code, uniqueness'


def resolve_rule(db, assignment_type_id, position):
    """Resolve the uniqueness rule row for an assignment, or ``None``.

    The identity is the stable type id first (FK), falling back to the display
    label, so both the typed position and the dropdown choice match the same
    type row.
    """
    value = (position or '').strip()
    if assignment_type_id:
        row = db.execute(
            f'SELECT {_RULE_COLUMNS} FROM admin_assignment_types WHERE id = ?',
            (assignment_type_id,),
        ).fetchone()
    elif value:
        row = db.execute(
            f'SELECT {_RULE_COLUMNS} FROM admin_assignment_types WHERE name = ?',
            (value,),
        ).fetchone()
    else:
        return None
    return dict(row) if row else None


def is_exempt(rule):
    """Roles with their own confirmed-transfer flow are not hard-blocked."""
    return bool(rule) and rule.get('internal_code') in _EXEMPT_ROLE_CODES


def _rule_identity_sql(rule):
    """Same-assignment predicate: stable FK or label fallback for old rows."""
    return (
        '(t.admin_assignment_type_id = ? OR (t.admin_assignment_type_id IS NULL AND t.position = ?))',
        (rule['id'], rule['name']),
    )


def active_holders(db, rule, department_id=None):
    """Active teachers holding ``rule`` within its scope (safe to call with rule)."""
    if not rule or not rule.get('uniqueness'):
        return []
    identity_sql, identity_params = _rule_identity_sql(rule)
    scope_sql = ''
    params = []
    if rule['uniqueness'] == 'department' and department_id is not None:
        scope_sql = 'AND t.department_id = ?'
        params.append(department_id)
    rows = db.execute(
        f'''SELECT t.id, t.name, t.department_id
            FROM teachers t
            WHERE t.deleted_at IS NULL
              AND {identity_sql}
              {scope_sql}''',
        list(identity_params) + params,
    ).fetchall()
    return [dict(r) for r in rows]


def all_active_holders(db, rule):
    """Every active holder of ``rule`` regardless of scope (for diagnostics)."""
    if not rule or not rule.get('uniqueness'):
        return []
    identity_sql, identity_params = _rule_identity_sql(rule)
    rows = db.execute(
        f'''SELECT t.id, t.name, t.department_id
            FROM teachers t
            WHERE t.deleted_at IS NULL
              AND {identity_sql}''',
        identity_params,
    ).fetchall()
    return [dict(r) for r in rows]


def proposed_identity(assignment_type_id, position, department_id):
    return (assignment_type_id, (position or '').strip(), department_id)


def current_identity(db, teacher_id):
    row = db.execute(
        '''SELECT admin_assignment_type_id, COALESCE(position, ''),
                  COALESCE(department_id, NULL)
           FROM teachers WHERE id = ?''',
        (teacher_id,),
    ).fetchone()
    if not row:
        return proposed_identity(None, '', None)
    return (row[0], row[1] or '', row[2])


def identity_unchanged(db, teacher_id, assignment_type_id, position, department_id):
    """True when the proposed assignment matches the stored one.

    Editing a holder who already occupies the slot keeps working; only a change
    that would *create* a second holder is refused.
    """
    return current_identity(db, teacher_id) == proposed_identity(
        assignment_type_id, position, department_id
    )


def holder_conflict(db, teacher_id, assignment_type_id, position, department_id):
    """Return the conflict dict for an occupied unique assignment, else ``None``.

    ``teacher_id`` is the teacher being created or edited; when it already
    holds this exact assignment the request sails through so existing records
    (including inherited duplicates) remain editable.
    """
    rule = resolve_rule(db, assignment_type_id, position)
    if not rule or not rule.get('uniqueness') or is_exempt(rule):
        return None
    if teacher_id and identity_unchanged(
        db, teacher_id, assignment_type_id, position, department_id
    ):
        return None
    holders = active_holders(db, rule, department_id)
    if not holders:
        return None
    taken_by = [h for h in holders if not teacher_id or h['id'] != teacher_id]
    if not taken_by:
        return None
    return {
        'rule': rule,
        'holder': taken_by[0],
        'holder_count': len(holders),
        'department_id': department_id,
    }


def conflict_message(conflict):
    """Arabic, actionable message describing why the assignment is refused."""
    rule = conflict['rule']
    holder = conflict['holder']
    if rule['uniqueness'] == 'global':
        scope = 'في النظام'
        hint = 'المنصب يشغله مسبقاً عضو آخر.'
    else:
        scope = f'في هذا القسم (الرقم {conflict.get("department_id") or "غير محدد"})'
        hint = 'المنصب يشغله مسبقاً عضو آخر في هذا القسم.'
    return (
        f'تعذّر إسناد التكليف «{rule["name"]}»: {hint} '
        f'لا يمكن تعيين عضو جديد ما دام التكليف مسنداً إلى '
        f'{holder["name"]} {scope}. '
        'أنهِ التكليف الحالي أو انقله قبل إسناده لمستخلف آخر.'
    )


def uniqueness_diagnostics(db):
    """List unique assignments currently holding more than one active teacher.

    Purely informational: the guard never auto-reassigns or deletes; the lookup
    page renders these so the dean can resolve inherited duplicates.
    """
    rules = db.execute(
        f'''SELECT {_RULE_COLUMNS} FROM admin_assignment_types
            WHERE uniqueness IN ('global', 'department')'''
    ).fetchall()
    issues = []
    for raw in rules:
        rule = dict(raw)
        for scope_group, holders in _grouped_holders(db, rule).items():
            if len(holders) > 1:
                issues.append({
                    'rule': rule,
                    'scope': scope_group if scope_group is not None else 'global',
                    'department_id': scope_group if scope_group is not None else None,
                    'holders': holders,
                })
    return issues


def _grouped_holders(db, rule):
    """group key = department_id for 'department' scope, else single group."""
    holders = all_active_holders(db, rule)
    if rule['uniqueness'] == 'global':
        return {None: holders}
    grouped = {}
    for h in holders:
        grouped.setdefault(h.get('department_id'), []).append(h)
    return grouped


def replacement_guard(db, replacement_id, moving_teacher_ids=()):
    """Block lookup merges that would assign a unique role to a fresh holder.

    Used when a value is deleted/replaced and its members are moved onto
    another type: if that type is already uniquely held by someone *not* being
    moved, the move would silently create a duplicate holder.
    """
    if not replacement_id:
        return None
    rule = resolve_rule(db, replacement_id, None)
    if not rule or not rule.get('uniqueness') or is_exempt(rule):
        return None
    moving = set(moving_teacher_ids)
    for holder in all_active_holders(db, rule):
        if holder['id'] not in moving:
            return {
                'rule': rule,
                'holder': holder,
                'department_id': holder.get('department_id'),
            }
    return None