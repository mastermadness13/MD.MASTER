from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository


class HistoryRepository(BaseRepository):
    table = 'history'

    def list_history(self, search: str = '', page: int = 1,
                     per_page: int = 20) -> tuple:
        base = 'SELECT * FROM history'
        params: list = []
        if search:
            base += ' WHERE message LIKE ? OR actor_username LIKE ? OR entity_type LIKE ?'
            params = [f'%{search}%'] * 3
        return self.paginate(base, params, page, per_page)

    def find_by_id(self, history_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM history WHERE id = ?', (history_id,)
        ).fetchone()
        return dict(row) if row else None

    def add(self, action: str, entity_type: str, entity_id: int = None,
            actor_user_id: int = None, actor_username: str = None,
            message: str = '', old_value: str = None, new_value: str = None) -> None:
        self.db.execute(
            'INSERT INTO history (action, entity_type, entity_id, actor_user_id, '
            'actor_username, message, old_value, new_value) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (action, entity_type, entity_id, actor_user_id,
             actor_username, message, old_value, new_value),
        )
        self.db.commit()

    def get_recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM history ORDER BY created_at DESC LIMIT ?', (limit,)
        ).fetchall()]

    def count_all(self) -> int:
        row = self.db.execute('SELECT COUNT(*) FROM history').fetchone()
        return row[0] if row else 0
