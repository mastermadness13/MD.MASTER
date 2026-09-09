"""History / audit-trail write helper.

Flask-independent: callers pass a ``sqlite3.Connection`` and the actor
fields explicitly.
"""

from __future__ import annotations

import json


def _serialize_history_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return json.dumps(value, ensure_ascii=False)
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def add_history(
    conn,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    actor_user_id: int | None = None,
    actor_username: str | None = None,
    message: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
) -> None:
    """Insert one row into the ``history`` audit table."""
    conn.execute(
        """
        INSERT INTO history (
            action,
            entity_type,
            entity_id,
            actor_user_id,
            actor_username,
            message,
            old_value,
            new_value
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action,
            entity_type,
            entity_id,
            actor_user_id,
            actor_username,
            message,
            _serialize_history_value(old_value),
            _serialize_history_value(new_value),
        ),
    )
    conn.commit()
