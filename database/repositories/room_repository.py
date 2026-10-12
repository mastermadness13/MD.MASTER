from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository

# /     /     >---- مستودع القاعات — كل العمليات على جدول rooms
class RoomRepository(BaseRepository):
    table = 'rooms'

    # /     /     >---- نجيب قاعة بالمعرف
    def find_by_id(self, room_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM rooms WHERE id = ?', (room_id,)
        ).fetchone()
        return dict(row) if row else None

    # /     /     >---- نجيب قاعة بكل تفاصيلها (النوع، الحالة، الطابق، القسم)
    def find_detail(self, room_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            '''SELECT r.*, rt.name_ar as type_name, rs.name_ar as status_name,
               f.name_ar as floor_name, d.name as dept_name
               FROM rooms r
               LEFT JOIN room_types rt ON r.room_type_id = rt.id
               LEFT JOIN room_statuses rs ON r.status_id = rs.id
               LEFT JOIN floors f ON r.floor_id = f.id
               LEFT JOIN departments d ON r.department_id = d.id
               WHERE r.id = ?''',
            (room_id,),
        ).fetchone()
        return dict(row) if row else None

    # /     /     >---- نجيب القاعات مع الترقيم (المختبرات الأول)
    def list_rooms(self, where_clause: str, params: list,
                   page: int = 1, per_page: int = 20) -> tuple:
        base = (
            'SELECT r.*, rt.name_ar as type_name, rs.name_ar as status_name, '
            'f.name_ar as floor_name, d.name as dept_name '
            'FROM rooms r '
            'LEFT JOIN room_types rt ON r.room_type_id = rt.id '
            'LEFT JOIN room_statuses rs ON r.status_id = rs.id '
            'LEFT JOIN floors f ON r.floor_id = f.id '
            'LEFT JOIN departments d ON r.department_id = d.id '
            f'WHERE {where_clause} '
            "ORDER BY CASE WHEN COALESCE(rt.css_class,'') = 'lab' THEN 1 ELSE 0 END, "
            'length(r.name), r.name'
        )
        return self.paginate(base, params, page, per_page)

    # /     /     >---- الأقسام المظهرة (غير المخفية)
    def list_visible_departments(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
        ).fetchall()]

    # /     /     >---- القيم المساعدة لصفحة الإنشاء (الأنواع، الحالات، الطوابق)
    def get_create_lookups(self) -> Dict[str, list]:
        from database.seed_data import CANONICAL_ROOM_TYPES
        canonical = ','.join('?' * len(CANONICAL_ROOM_TYPES))
        return {
            'room_types': [dict(r) for r in self.db.execute(
                f'SELECT * FROM room_types WHERE name_ar IN ({canonical}) ORDER BY sort_order',
                list(CANONICAL_ROOM_TYPES),
            ).fetchall()],
            'statuses': [dict(r) for r in self.db.execute(
                'SELECT * FROM room_statuses ORDER BY sort_order'
            ).fetchall()],
            'floors': [dict(r) for r in self.db.execute(
                'SELECT * FROM floors ORDER BY sort_order'
            ).fetchall()],
            'departments': self.list_visible_departments(),
        }

    # /     /     >---- كل القاعات (اللي ما فيهمش حذف ناعم)
    def list_all(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT id, name, type, capacity FROM rooms WHERE deleted_at IS NULL ORDER BY name'
        ).fetchall()]

    # /     /     >---- الجداول التي تشير إلى القاعة، وهل لكل منها حذف ناعم.
    # /     /     >---- exam_schedule ليس له deleted_at: أي صف موجود فيها-count.
    USAGE_TABLES = (
        ('exam_schedule', False),
        ('timetable', True),
        ('teacher_taught_courses', False),
    )

    @staticmethod
    def _empty_usage() -> Dict[str, int]:
        return {'exam_schedule': 0, 'timetable': 0, 'teacher_taught_courses': 0,
                'total': 0}

    # /     /     >---- مراجع القاعة: كم صف يشير إليها في كل جدول.
    # /     /     >---- خدمات الحذف لا تفحص المراجع إطلاقاً، ومفاتيح SQLite
    # /     /     >---- قد تكون متوقفة، فالحذف النهائي يفكك exam_schedule
    # /     /     >---- ويُفرغ exam.hall بصمت. العدّ هنا هو ما يمنع ذلك.
    def usage_counts(self, room_id: int) -> Dict[str, int]:
        """Reference counts for one room, in every table that points at it."""
        return self.usage_map([room_id]).get(int(room_id), self._empty_usage())

    # /     /     >---- نفس العدّ لكن دفعة واحدة: ثلاثة استعلامات مُجمّعة
    # /     /     >---- (GROUP BY room_id) بدل حلقة على كل قاعة في الصفحة.
    def usage_map(self, room_ids) -> Dict[int, Dict[str, int]]:
        """Reference counts for many rooms, keyed by room id."""
        ids = []
        for room_id in room_ids or ():
            try:
                ids.append(int(room_id))
            except (TypeError, ValueError):
                continue
        result = {room_id: self._empty_usage() for room_id in ids}
        if not ids:
            return result
        placeholders = ','.join('?' * len(ids))
        for table, has_soft_delete in self.USAGE_TABLES:
            query = (f'SELECT room_id, COUNT(*) AS uses FROM {table} '
                     f'WHERE room_id IN ({placeholders})')
            if has_soft_delete:
                query += ' AND deleted_at IS NULL'
            query += ' GROUP BY room_id'
            for row in self.db.execute(query, ids).fetchall():
                counts = result.get(row['room_id'])
                if counts is not None:
                    counts[table] = row['uses']
        for counts in result.values():
            counts['total'] = sum(counts[table] for table, _soft in self.USAGE_TABLES)
        return result

    # /     /     >---- نصنع قاعة جديدة ونرجع معرّفها
    def create(self, data: Dict[str, Any], commit: bool = True) -> int:
        self.db.execute(
            'INSERT INTO rooms (name, code, capacity, room_type_id, status_id, '
            'floor_id, building, department_id, computers) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (data['name'], data.get('code', ''), data.get('capacity', 0),
             data.get('room_type_id'), data.get('status_id'), data.get('floor_id'),
             data.get('building', ''), data.get('department_id'), data.get('computers', 0)),
        )
        if commit:
            self.db.commit()
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    # /     /     >---- نحدّث بيانات القاعة
    def update(self, room_id: int, data: Dict[str, Any]) -> None:
        self.db.execute(
            'UPDATE rooms SET name=?, code=?, capacity=?, room_type_id=?, '
            'status_id=?, floor_id=?, building=?, department_id=?, computers=? WHERE id=?',
            (data['name'], data.get('code', ''), data.get('capacity', 0),
             data.get('room_type_id'), data.get('status_id'), data.get('floor_id'),
             data.get('building', ''), data.get('department_id'), data.get('computers', 0), room_id),
        )
        self.db.commit()