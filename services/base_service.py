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


def archived_list(db, base_query, search_fields, search, page, deleted_at_column='deleted_at'):
    where = [f'{deleted_at_column} IS NOT NULL']
    params = []
    if search and search_fields:
        conditions = [f'({f} LIKE ?)' for f in search_fields]
        where.append('(' + ' OR '.join(conditions) + ')')
        params.extend([f'%{search}%'] * len(search_fields))
    where_clause = ' AND '.join(where)
    query = f'{base_query} WHERE {where_clause} ORDER BY {deleted_at_column} DESC'
    return paginate(query, params, page)
