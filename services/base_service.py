from utils.format import paginate

def soft_delete(db, table, id, history_callback=None):
    db.execute(f'UPDATE {table} SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?', (id,))
    if history_callback:
        history_callback(db)
    db.commit()


def restore(db, table, id):
    db.execute(f'UPDATE {table} SET deleted_at = NULL WHERE id = ?', (id,))
    db.commit()


def hard_delete(db, table, id):
    db.execute(f'DELETE FROM {table} WHERE id = ?', (id,))
    db.commit()


