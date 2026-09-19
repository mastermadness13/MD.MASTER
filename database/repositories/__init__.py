"""Repository layer — data access encapsulation.

Every repository inherits from ``database.repositories.base_repository`` and
owns the SQL for a single domain table (or closely-related group of tables).
"""

# /     /     >---- طبقة المستودعات: تغليف الوصول إلى البيانات

from database.repositories.base_repository import BaseRepository
from database.repositories import _helpers

__all__ = ['BaseRepository']