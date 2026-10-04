"""Resolve user-facing role labels from the managed assignment names."""

from core.constants import ROLE_LABELS


def get_role_labels(db) -> dict[str, str]:
    """Return role labels, preferring the assignment currently granting a role."""
    labels = dict(ROLE_LABELS)
    rows = db.execute(
        """SELECT a.internal_code, a.name
           FROM admin_assignment_types a
           WHERE a.is_system_linked = 1
             AND a.internal_code IS NOT NULL
             AND TRIM(a.name) <> ''
           ORDER BY
             EXISTS (
               SELECT 1
               FROM teachers t
               JOIN users u ON u.id = t.user_id
               WHERE t.admin_assignment_type_id = a.id
                 AND (
                   u.role = a.internal_code
                   OR EXISTS (
                     SELECT 1 FROM user_roles ur
                     WHERE ur.user_id = u.id AND ur.role = a.internal_code
                   )
                 )
             ) DESC,
             a.is_active DESC, a.sort_order, a.id"""
    ).fetchall()
    resolved = set()
    for row in rows:
        role = row['internal_code']
        if role in labels and role not in resolved:
            labels[role] = row['name']
            resolved.add(role)
    return labels
