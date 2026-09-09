from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository):
    table = 'users'

    # ── Reads ────────────────────────────────────────────────────────────

    def find_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()
        return dict(row) if row else None

    def find_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def find_by_username_or_email(self, identifier: str) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM users WHERE username = ? OR email = ?',
            (identifier, identifier),
        ).fetchone()
        return dict(row) if row else None

    def find_with_department(self, user_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT u.*, d.name AS department_name, '
            'ad.name AS administrative_department_name '
            'FROM users u '
            'LEFT JOIN departments d ON u.department_id = d.id '
            'LEFT JOIN departments ad ON u.administrative_department_id = ad.id '
            'WHERE u.id = ?',
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_teacher_by_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM teachers WHERE user_id = ?', (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_visible_departments(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
        ).fetchall()]

    def username_exists(self, username: str) -> bool:
        return self.db.execute(
            'SELECT 1 FROM users WHERE username = ?', (username,)
        ).fetchone() is not None

    def list_users(self, search: str = '', page: int = 1,
                   per_page: int = 20) -> tuple:
        base = ('SELECT u.*, d.name AS department_name, '
                'ad.name AS administrative_department_name '
                'FROM users u '
                'LEFT JOIN departments d ON u.department_id = d.id '
                'LEFT JOIN departments ad ON u.administrative_department_id = ad.id')
        params: list = []
        if search:
            base += ' WHERE u.username LIKE ? OR u.email LIKE ? OR u.label LIKE ?'
            params = [f'%{search}%'] * 3
        return self.paginate(base, params, page, per_page)

    # ── Writes ───────────────────────────────────────────────────────────

    def create_user(self, data: Dict[str, Any]) -> int:
        cols = ', '.join(data.keys())
        ph = ', '.join(['?'] * len(data))
        self.db.execute(
            f'INSERT INTO users ({cols}) VALUES ({ph})', list(data.values())
        )
        self.db.commit()
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    def update_user(self, user_id: int, data: Dict[str, Any]) -> None:
        if not data:
            return
        set_clause = ', '.join(f'{k} = ?' for k in data.keys())
        self.db.execute(
            f'UPDATE users SET {set_clause} WHERE id = ?',
            list(data.values()) + [user_id],
        )
        self.db.commit()

    def update_password(self, user_id: int, hashed_password: str) -> None:
        self.db.execute(
            'UPDATE users SET password = ?, password_changed_at = CURRENT_TIMESTAMP WHERE id = ?',
            (hashed_password, user_id),
        )
        self.db.commit()

    def update_theme(self, user_id: int, theme: str) -> None:
        self.db.execute(
            'UPDATE users SET theme = ? WHERE id = ?', (theme, user_id)
        )
        self.db.commit()

    def delete_user(self, user_id: int) -> None:
        self.db.execute('UPDATE teachers SET user_id = NULL WHERE user_id = ?', (user_id,))
        self.db.execute('DELETE FROM password_resets WHERE user_id = ?', (user_id,))
        self.db.execute('DELETE FROM notifications WHERE user_id = ?', (user_id,))
        self.db.execute('DELETE FROM user_roles WHERE user_id = ?', (user_id,))
        self.db.execute('DELETE FROM users WHERE id = ?', (user_id,))
        self.db.commit()

    # ── Multi-role (user_roles) ─────────────────────────────────────────

    def find_roles_by_user(self, user_id: int) -> List[str]:
        rows = self.db.execute(
            'SELECT role FROM user_roles WHERE user_id = ?', (user_id,)
        ).fetchall()
        return [r['role'] for r in rows]

    def set_user_roles(self, user_id: int, roles) -> None:
        """Replace the user's granted role set with *roles* (list/tuple/set)."""
        roles = list(dict.fromkeys(r for r in (roles or []) if r))
        self.db.execute('DELETE FROM user_roles WHERE user_id = ?', (user_id,))
        if roles:
            self.db.executemany(
                'INSERT OR IGNORE INTO user_roles (user_id, role) VALUES (?, ?)',
                [(user_id, r) for r in roles],
            )
        self.db.commit()

    def add_user_role(self, user_id: int, role: str) -> None:
        self.db.execute(
            'INSERT OR IGNORE INTO user_roles (user_id, role) VALUES (?, ?)',
            (user_id, role),
        )
        self.db.commit()

    def remove_user_role(self, user_id: int, role: str) -> None:
        self.db.execute(
            'DELETE FROM user_roles WHERE user_id = ? AND role = ?',
            (user_id, role),
        )
        self.db.commit()

    def set_user_active(self, user_id: int, active: bool) -> None:
        """Enable/disable a user account via the ``is_active`` flag."""
        self.db.execute(
            'UPDATE users SET is_active = ? WHERE id = ?',
            (1 if active else 0, user_id),
        )
        self.db.commit()

    # ── Password reset ───────────────────────────────────────────────────

    def create_password_reset(self, user_id: int, token: str,
                              expires_at: str) -> None:
        self.db.execute(
            'INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)',
            (user_id, token, expires_at),
        )
        self.db.commit()

    def find_valid_reset_token(self, token: str) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            'SELECT * FROM password_resets WHERE token = ? AND used = 0 '
            'AND expires_at > datetime("now")',
            (token,),
        ).fetchone()
        return dict(row) if row else None

    def mark_reset_used(self, reset_id: int) -> None:
        self.db.execute(
            'UPDATE password_resets SET used = 1 WHERE id = ?', (reset_id,)
        )
        self.db.commit()
