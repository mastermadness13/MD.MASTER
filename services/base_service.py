"""Base service helpers: shared delete/restore operations.

/     /     >---- عمليات الحذف والاسترجاع المشتركة بين كل الخدمات.
"""
from utils.format import paginate


# /     /     >---- حذف ناعم: ما نحذفش السجل نهائياً، فقط نعلّم عليه وقت الحذف
def soft_delete(db, table, id, history_callback=None):
    db.execute(f'UPDATE {table} SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?', (id,))
    if history_callback:
        history_callback(db)
    db.commit()


# /     /     >---- استرجاع: نرجع السجل المحذوف ناعماً (نفضي وقت الحذف)
def restore(db, table, id):
    db.execute(f'UPDATE {table} SET deleted_at = NULL WHERE id = ?', (id,))
    db.commit()


# /     /     >---- حذف نهائي: نشيل السجل من قاعدة البيانات بالإجمال
def hard_delete(db, table, id):
    db.execute(f'DELETE FROM {table} WHERE id = ?', (id,))
    db.commit()