"""Classroom (room) service — CRUD, lookups, archive.

Uses ``RoomRepository`` for data access.  Module-level functions are kept
for backward compatibility with existing routes.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Natural ordering: halls first then labs, each sorted naturally
# (قاعة 1, قاعة 2, ... قاعة 10) instead of lexicographic order.
NATURAL_ROOM_ORDER = (
    "CASE WHEN COALESCE(rt.css_class,'') = 'lab' THEN 1 ELSE 0 END, "
    'length(r.name), r.name'
)


class ClassroomService:
    """Class-based classroom service with repository injection."""

    def __init__(self, db, room_repo):
        self.db = db
        self._repo = room_repo

    def list_rooms(self, search: str, dept_filter: str, page: int = 1) -> tuple:
        where = ['r.deleted_at IS NULL']
        params: list = []
        if search:
            where.append('(r.name LIKE ? OR r.code LIKE ?)')
            params.extend([f'%{search}%'] * 2)
        if dept_filter:
            where.append('r.department_id = ?')
            params.append(dept_filter)
        where_clause = ' AND '.join(where) if where else '1=1'
        rows, total, pg, pp = self._repo.list_rooms(where_clause, params, page)
        departments = self._repo.list_visible_departments()
        return rows, total, pg, pp, departments

    def get_create_lookups(self) -> Dict[str, list]:
        return self._repo.get_create_lookups()

    def create_room(self, data: Dict[str, Any]) -> int:
        quantity = data.get('quantity', 1) or 1
        if quantity < 1:
            quantity = 1
        base_name = (data.get('name') or '').strip()

        if quantity == 1:
            # Keep the exact typed name for a single room (e.g. «مسرح»,
            # «قاعة العرض»), matching the original behaviour.
            names = [base_name]
        else:
            # If the given base name already ends with a number (e.g.
            # «قاعة 6»), continue that exact sequence («قاعة 6»,
            # «قاعة 7», ...), skipping any already-occupied numbers (so
            # «معمل إلكترونيات 2» when it exists yields 3, 4, ...).
            # Otherwise treat the whole name as a prefix and start from the
            # next available number (e.g. «قاعة» with «قاعة 14» present →
            # 15, 16, ...). Names without a trailing number (e.g. «قاعة
            # العرض», «معمل الكلية») are ignored when computing the number.
            prefix_match = re.match(r'^(.*?\D)(\d+)$', base_name)
            if prefix_match:
                text_part = prefix_match.group(1).rstrip()
                given_number = int(prefix_match.group(2))
                prefix = re.escape(text_part)
                pattern = re.compile(rf'^{prefix}\s*(\d+)$')
                existing = self.db.execute(
                    'SELECT name FROM rooms WHERE deleted_at IS NULL AND name LIKE ?',
                    (f'{text_part} %',),
                ).fetchall()
                numbers = []
                for row in existing:
                    m = pattern.match(row['name'])
                    if m:
                        numbers.append(int(m.group(1)))
                if numbers:
                    given_number = max(given_number, max(numbers) + 1)
                names = [f'{text_part} {given_number + i}' for i in range(quantity)]
            else:
                prefix = re.escape(base_name)
                pattern = re.compile(rf'^{prefix}\s*(\d+)$')
                existing = self.db.execute(
                    'SELECT name FROM rooms WHERE deleted_at IS NULL AND name LIKE ?',
                    (f'{base_name} %',),
                ).fetchall()
                numbers = []
                for row in existing:
                    m = pattern.match(row['name'])
                    if m:
                        numbers.append(int(m.group(1)))
                next_number = max(numbers) + 1 if numbers else 1
                names = [f'{base_name} {next_number + i}' for i in range(quantity)]
        # Prevent duplicate room names among active rooms.
        placeholders = ','.join('?' * len(names))
        dup = self.db.execute(
            f'SELECT name FROM rooms WHERE deleted_at IS NULL '
            f'AND name IN ({placeholders}) LIMIT 1',
            names,
        ).fetchone()
        if dup:
            raise ValueError(
                f"الاسم «{dup['name']}» مستخدم مسبقاً — يرجى اختيار اسم آخر."
            )
        last_id = None
        try:
            for room_name in names:
                room_data = dict(data)
                room_data['name'] = room_name
                last_id = self._repo.create(room_data, commit=False)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return last_id

    def get_room(self, room_id: int) -> Optional[Dict]:
        return self._repo.find_by_id(room_id)

    def update_room(self, room_id: int, data: Dict[str, Any]) -> None:
        self._repo.update(room_id, data)

    def get_room_detail(self, room_id: int) -> Optional[Dict]:
        return self._repo.find_detail(room_id)

    def room_delete(self, room_id: int, history_callback=None) -> None:
        self._repo.soft_delete(room_id)
        if history_callback:
            history_callback(self.db)

    def room_restore(self, room_id: int) -> None:
        self._repo.restore(room_id)

    def room_hard_delete(self, room_id: int) -> None:
        self._repo.delete(room_id)



# ── Backward-compatible module-level API ──────────────────────────────────

def list_rooms(db, search, dept_filter, page):
    from utils.format import paginate
    from database.repositories.room_repository import RoomRepository
    where = ['r.deleted_at IS NULL']
    params = []
    if search:
        where.append('(r.name LIKE ? OR r.code LIKE ?)')
        params.extend([f'%{search}%'] * 2)
    if dept_filter:
        where.append('r.department_id = ?')
        params.append(dept_filter)
    where_clause = ' AND '.join(where) if where else '1=1'
    query = (
        'SELECT r.*, rt.name_ar as type_name, rs.name_ar as status_name, '
        'f.name_ar as floor_name, d.name as dept_name FROM rooms r '
        'LEFT JOIN room_types rt ON r.room_type_id = rt.id '
        'LEFT JOIN room_statuses rs ON r.status_id = rs.id '
        'LEFT JOIN floors f ON r.floor_id = f.id '
        'LEFT JOIN departments d ON r.department_id = d.id '
        f'WHERE {where_clause} ORDER BY {NATURAL_ROOM_ORDER}'
    )
    rows, total, page, per_page = paginate(query, params, page)
    departments = db.execute(
        'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
    ).fetchall()
    return rows, total, page, per_page, [dict(d) for d in departments]


def get_create_lookups(db):
    from database.repositories.room_repository import RoomRepository
    lookups = RoomRepository(db).get_create_lookups()
    return (
        lookups['room_types'], lookups['statuses'],
        lookups['floors'], lookups['departments'],
    )


def create_room(db, data):
    from database.repositories.room_repository import RoomRepository
    return ClassroomService(db, RoomRepository(db)).create_room(data)


def get_room(db, id):
    return db.execute('SELECT * FROM rooms WHERE id = ?', (id,)).fetchone()


def update_room(db, id, data):
    from database.repositories.room_repository import RoomRepository
    RoomRepository(db).update(id, data)


def get_room_detail(db, id):
    from database.repositories.room_repository import RoomRepository
    return RoomRepository(db).find_detail(id)


def room_delete(db, id, history_callback):
    from services.base_service import soft_delete
    soft_delete(db, 'rooms', id, history_callback)


def room_restore(db, id):
    from services.base_service import restore
    restore(db, 'rooms', id)


def room_hard_delete(db, id):
    from services.base_service import hard_delete
    hard_delete(db, 'rooms', id)


def room_archive_list(db, search, page):
    from database.repositories.room_repository import RoomRepository
    return RoomRepository(db).archive_list(search, page)
