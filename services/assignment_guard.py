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
        f'''SELECT t.id, t.name, t.department_id, t.user_id
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


def holder_conflict(
    db, teacher_id, assignment_type_id, position, department_id, user_id=None
):
    """Return the conflict dict for an occupied unique assignment, else ``None``.

    ``teacher_id`` and ``user_id`` identify the teacher/account being edited.
    Global system roles also include existing RBAC holders without a matching
    teacher row, such as the original office-manager account.
    """
    rule = resolve_rule(db, assignment_type_id, position)
    if not rule or not rule.get('uniqueness') or is_exempt(rule):
        return None
    if rule['uniqueness'] == 'department' and department_id is None:
        return None

    holders = active_holders(db, rule, department_id)
    conflicts = []
    for holder in holders:
        if teacher_id and holder['id'] == teacher_id:
            continue
        holder = dict(holder)
        holder['teacher_id'] = holder['id']
        holder['holder_key'] = (
            f'user:{holder["user_id"]}' if holder.get('user_id')
            else f'teacher:{holder["id"]}'
        )
        conflicts.append(holder)

    if rule['uniqueness'] == 'global' and rule.get('internal_code'):
        role = rule['internal_code']
        role_holders = db.execute(
            '''SELECT u.id AS user_id, u.username,
                      COALESCE(NULLIF(t.name, ''), NULLIF(u.label, ''), u.username) AS name,
                      t.id AS teacher_id, t.department_id
               FROM users u
               LEFT JOIN teachers t ON t.user_id = u.id AND t.deleted_at IS NULL
               LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.role = ?
               WHERE u.is_active = 1
                 AND (u.role = ? OR ur.user_id IS NOT NULL)
                 AND NOT (u.username = 'office_manager' AND ? = 'faculty_affairs')''',
            (role, role, role),
        ).fetchall()
        known_users = {
            holder.get('user_id') for holder in conflicts
            if holder.get('user_id')
        }
        for raw in role_holders:
            holder = dict(raw)
            if holder['user_id'] == user_id or holder['user_id'] in known_users:
                continue
            if teacher_id and holder.get('teacher_id') == teacher_id:
                continue
            holder['id'] = holder.get('teacher_id')
            holder['holder_key'] = f'user:{holder["user_id"]}'
            conflicts.append(holder)
            known_users.add(holder['user_id'])

    if not conflicts:
        return None
    return {
        'rule': rule,
        'holder': conflicts[0],
        'holders': conflicts,
        'holder_count': len(conflicts),
        'department_id': department_id,
    }


def transfer_holders(db, conflict, target_teacher_id=None, target_user_id=None):
    """Release a confirmed unique assignment from every previous holder.

    Changes are deliberately left uncommitted so the caller can commit them
    with the new teacher assignment and RBAC grant.
    """
    rule = conflict['rule']
    role = rule.get('internal_code')

    if rule['uniqueness'] == 'global' and role:
        role_types = db.execute(
            '''SELECT id, name FROM admin_assignment_types
               WHERE internal_code = ? AND uniqueness = 'global' ''',
            (role,),
        ).fetchall()
        type_ids = [row['id'] for row in role_types]
        type_names = [row['name'] for row in role_types]
        if type_ids:
            placeholders = ','.join('?' for _ in type_ids)
            legacy_predicates = ' OR '.join(
                '(admin_assignment_type_id IS NULL AND position = ?)'
                for _ in type_names
            )
            legacy_clause = f' OR {legacy_predicates}' if legacy_predicates else ''
            teacher_rows = db.execute(
                f'''SELECT id, user_id FROM teachers
                    WHERE deleted_at IS NULL
                      AND id != COALESCE(?, -1)
                      AND (admin_assignment_type_id IN ({placeholders})
                           {legacy_clause})''',
                [target_teacher_id, *type_ids, *type_names],
            ).fetchall()
        else:
            teacher_rows = []
        role_users = db.execute(
            '''SELECT DISTINCT u.id AS user_id, t.id AS teacher_id
               FROM users u
               LEFT JOIN teachers t ON t.user_id = u.id AND t.deleted_at IS NULL
               LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.role = ?
               WHERE u.is_active = 1
                 AND (u.role = ? OR ur.user_id IS NOT NULL)
                 AND NOT (u.username = 'office_manager' AND ? = 'faculty_affairs')''',
            (role, role, role),
        ).fetchall()
    else:
        teacher_rows = [
            holder for holder in conflict['holders']
            if holder.get('teacher_id') is not None
        ]
        type_names = [rule['name']]
        role_users = []

    teacher_ids = set()
    user_ids = set()
    for holder in teacher_rows:
        old_teacher_id = holder['id'] if 'id' in holder.keys() else holder['teacher_id']
        if old_teacher_id == target_teacher_id:
            continue
        teacher_ids.add(old_teacher_id)
        if holder['user_id'] and holder['user_id'] != target_user_id:
            user_ids.add(holder['user_id'])

    for holder in conflict['holders']:
        holder_teacher_id = holder.get('teacher_id')
        holder_user_id = holder.get('user_id')
        if holder_teacher_id and holder_teacher_id != target_teacher_id:
            teacher_ids.add(holder_teacher_id)
        if holder_user_id and holder_user_id != target_user_id:
            user_ids.add(holder_user_id)

    for holder in role_users:
        if holder['user_id'] == target_user_id:
            continue
        user_ids.add(holder['user_id'])
        if holder['teacher_id'] and holder['teacher_id'] != target_teacher_id:
            teacher_ids.add(holder['teacher_id'])

    for teacher_id in teacher_ids:
        db.execute(
            '''UPDATE teachers
               SET position = '', admin_assignment_type_id = NULL
               WHERE id = ? AND deleted_at IS NULL''',
            (teacher_id,),
        )
        if type_names:
            placeholders = ','.join('?' for _ in type_names)
            db.execute(
                f'''UPDATE faculty_admin_assignments
                    SET deleted_at = CURRENT_TIMESTAMP
                    WHERE teacher_id = ? AND task_name IN ({placeholders})
                      AND deleted_at IS NULL''',
                [teacher_id, *type_names],
            )
        holder = db.execute(
            'SELECT user_id FROM teachers WHERE id = ?', (teacher_id,)
        ).fetchone()
        if holder and holder['user_id'] and role:
            has_other_role_assignment = db.execute(
                '''SELECT 1 FROM teachers t
                   JOIN admin_assignment_types a
                     ON a.id = t.admin_assignment_type_id
                   WHERE t.user_id = ? AND t.deleted_at IS NULL
                     AND a.internal_code = ? AND a.uniqueness IN ('global', 'department')
                   LIMIT 1''',
                (holder['user_id'], role),
            ).fetchone()
            if not has_other_role_assignment:
                user_ids.add(holder['user_id'])

    if role:
        for old_user_id in user_ids:
            db.execute(
                'DELETE FROM user_roles WHERE user_id = ? AND role = ?',
                (old_user_id, role),
            )
            remaining = [
                row['role'] for row in db.execute(
                    'SELECT role FROM user_roles WHERE user_id = ?',
                    (old_user_id,),
                ).fetchall()
            ]
            fallback_order = (
                'research_development', 'faculty_affairs', 'exam',
                'head_of_department', 'teacher', 'visitor',
            )
            fallback = next(
                (candidate for candidate in fallback_order if candidate in remaining),
                'teacher',
            )
            db.execute(
                'INSERT OR IGNORE INTO user_roles (user_id, role) VALUES (?, ?)',
                (old_user_id, fallback),
            )
            db.execute(
                '''UPDATE users
                   SET role = CASE WHEN role = ? THEN ? ELSE role END,
                       session_version = session_version + 1
                   WHERE id = ?''',
                (role, fallback, old_user_id),
            )


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