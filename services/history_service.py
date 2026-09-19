"""History service — audit log listing and detail.

Uses ``HistoryRepository`` for data access.  Module-level functions are kept
for backward compatibility with existing routes.

/     /     >---- خدمة سجل العمليات: عرض سجل المتابعة وتفاصيل العمليات.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# /     /     >---- الخدمة بشكل كلاس: حقن المستودع في المُنشئ
class HistoryService:
    """Class-based history service with repository injection."""

    def __init__(self, db, history_repo):
        self.db = db
        self._repo = history_repo

    # /     /     >---- جلب السجل الكامل مع البحث والترقيم
    def list_history(self, search: str = '', page: int = 1) -> tuple:
        return self._repo.list_history(search, page)

    # /     /     >---- جلب تفاصيل عملية معينة من السجل
    def get_history_detail(self, history_id: int) -> Optional[Dict]:
        return self._repo.find_by_id(history_id)


# /     /     >---- دوال مستوى الوحدة للمحافظة على التوافق مع المسارات القديمة
def list_history(db, search, page):
    from utils.format import paginate
    query = 'SELECT * FROM history'
    params = []
    if search:
        query += ' WHERE message LIKE ? OR actor_username LIKE ? OR entity_type LIKE ?'
        params = [f'%{search}%'] * 3
    query += ' ORDER BY created_at DESC'
    return paginate(query, params, page)


# /     /     >---- جلب عملية وحدة من السجل حسب المعرّف
def get_history_detail(db, id):
    return db.execute('SELECT * FROM history WHERE id = ?', (id,)).fetchone()