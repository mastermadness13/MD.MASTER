import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def lookup_setup(tmp_path, monkeypatch, app_fx):
    db_path = tmp_path / 'lookup-lists.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as schema_file:
        conn.executescript(schema_file.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES ('lookup_manager', 'x', 'faculty_affairs', 'مدير المكتب')"
    )
    manager_id = conn.execute(
        "SELECT id FROM users WHERE username = 'lookup_manager'"
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO users (username, password, role, label) "
        "VALUES ('lookup_hod', 'x', 'head_of_department', 'رئيس قسم')"
    )
    hod_id = conn.execute(
        "SELECT id FROM users WHERE username = 'lookup_hod'"
    ).fetchone()['id']
    conn.commit()
    conn.close()

    def client_for(user_id, role, username):
        client = app_fx.test_client()
        with client.session_transaction() as session:
            session['user_id'] = user_id
            session['role'] = role
            session['username'] = username
            session['_csrf_token'] = 'test-token'
        return client

    return db_path, client_for(manager_id, 'faculty_affairs', 'lookup_manager'), (
        client_for(hod_id, 'head_of_department', 'lookup_hod')
    )


def _post(client, category, action, **values):
    return client.post(
        '/teachers/lookup-lists',
        data={
            '_csrf_token': 'test-token',
            'category': category,
            'action': action,
            **values,
        },
        follow_redirects=True,
    )


def _fetchone(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return dict(row) if row else None


def test_lookup_lists_are_restricted_to_faculty_affairs(lookup_setup):
    _, manager, hod = lookup_setup

    assert manager.get('/teachers/lookup-lists').status_code == 200
    assert hod.get('/teachers/lookup-lists').status_code == 403


def test_system_assignment_rename_keeps_its_internal_role(lookup_setup):
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    row = _fetchone(
        db_path,
        "SELECT id FROM admin_assignment_types "
        "WHERE name = 'رئيس قسم' AND internal_code = 'head_of_department'",
    )
    assert row
    conn.execute("INSERT INTO teachers (name) VALUES ('عضو رئيس قسم')")
    teacher_id = conn.execute(
        "SELECT id FROM teachers WHERE name = 'عضو رئيس قسم'"
    ).fetchone()['id']
    conn.commit()
    conn.close()

    response = _post(
        manager, 'admin_assignment_type', 'rename',
        id=str(row['id']), name='رئيس القسم الأكاديمي',
    )

    assert response.status_code == 200
    renamed = _fetchone(
        db_path, 'SELECT name, internal_code, is_system_linked '
        'FROM admin_assignment_types WHERE id = ?', (row['id'],)
    )
    assert renamed == {
        'name': 'رئيس القسم الأكاديمي',
        'internal_code': 'head_of_department',
        'is_system_linked': 1,
    }
    page = manager.get(f'/teachers/edit/{teacher_id}')
    assert page.status_code == 200
    assert 'data-role="head_of_department"' in page.get_data(as_text=True)


def test_deleting_an_assignment_in_use_requires_confirmation_and_clears_references(
    lookup_setup,
):
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        "INSERT INTO admin_assignment_types "
        "(name, default_hours, is_active, sort_order, is_system_linked) "
        "VALUES ('تكليف تجريبي', 0, 1, 99, 0)"
    )
    task_id = conn.execute(
        "SELECT id FROM admin_assignment_types WHERE name = 'تكليف تجريبي'"
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO teachers (name, position) VALUES ('عضو تجريبي', 'تكليف تجريبي')"
    )
    conn.commit()
    conn.close()

    response = _post(
        manager, 'admin_assignment_type', 'delete', id=str(task_id)
    )
    assert 'تأكيد حذف «تكليف تجريبي»' in response.get_data(as_text=True)

    response = _post(
        manager, 'admin_assignment_type', 'delete',
        id=str(task_id), clear_references='1',
    )
    assert response.status_code == 200
    assert _fetchone(
        db_path, 'SELECT position FROM teachers WHERE name = ?', ('عضو تجريبي',)
    )['position'] == ''
    assert _fetchone(
        db_path, 'SELECT id FROM admin_assignment_types WHERE id = ?', (task_id,)
    ) is None


def test_rank_replacement_migrates_teacher_and_workload_rules(lookup_setup):
    db_path, manager, _ = lookup_setup
    conn = connect(str(db_path))
    conn.execute(
        "INSERT INTO academic_ranks (name_ar, name_en, sort_order) "
        "VALUES ('رتبة تجريبية', 'Test rank', 999)"
    )
    old_id = conn.execute(
        "SELECT id FROM academic_ranks WHERE name_ar = 'رتبة تجريبية'"
    ).fetchone()['id']
    replacement = conn.execute(
        'SELECT id FROM academic_ranks WHERE id != ? AND is_active = 1 LIMIT 1',
        (old_id,),
    ).fetchone()['id']
    qualification_id = conn.execute(
        'SELECT id FROM qualifications WHERE is_active = 1 LIMIT 1'
    ).fetchone()['id']
    conn.execute(
        "INSERT INTO teachers (name, rank_id, academic_rank) "
        "VALUES ('عضو رتبة تجريبية', ?, 'رتبة تجريبية')", (old_id,)
    )
    conn.execute(
        'INSERT INTO rank_rules (qualification_id, rank_id) VALUES (?, ?)',
        (qualification_id, old_id),
    )
    conn.execute(
        'INSERT INTO faculty_workload_rules '
        '(rank_id, category, min_hours, max_hours, academic_year) '
        "VALUES (?, 'lookup-test', 2, 8, '2099-2100')", (old_id,)
    )
    conn.commit()
    conn.close()

    response = _post(
        manager, 'academic_rank', 'delete',
        id=str(old_id), replacement_id=str(replacement),
    )

    assert response.status_code == 200
    assert _fetchone(
        db_path, 'SELECT rank_id, academic_rank FROM teachers WHERE name = ?',
        ('عضو رتبة تجريبية',),
    ) == {
        'rank_id': replacement,
        'academic_rank': _fetchone(
            db_path, 'SELECT name_ar FROM academic_ranks WHERE id = ?',
            (replacement,),
        )['name_ar'],
    }
    assert _fetchone(
        db_path, 'SELECT rank_id FROM faculty_workload_rules '
        "WHERE category = 'lookup-test' AND academic_year = '2099-2100'"
    ) == {'rank_id': replacement}
    assert _fetchone(
        db_path, 'SELECT rank_id FROM rank_rules WHERE qualification_id = ?',
        (qualification_id,),
    ) == {'rank_id': replacement}


def test_removed_default_assignment_does_not_reappear_on_schema_recheck(
    lookup_setup,
):
    db_path, _, _ = lookup_setup
    conn = connect(str(db_path))
    qualification = conn.execute(
        'SELECT name_ar FROM qualifications ORDER BY id LIMIT 1'
    ).fetchone()['name_ar']
    specialization = conn.execute(
        'SELECT id, name FROM specializations ORDER BY id LIMIT 1'
    ).fetchone()
    conn.execute(
        "DELETE FROM admin_assignment_types WHERE name = 'منسق القاعات'"
    )
    conn.execute('DELETE FROM qualifications WHERE name_ar = ?', (qualification,))
    if specialization:
        conn.execute('DELETE FROM specializations WHERE id = ?', (specialization['id'],))
    conn.commit()
    ensure_schema(conn)
    remaining = conn.execute(
        "SELECT COUNT(*) FROM admin_assignment_types WHERE name = 'منسق القاعات'"
    ).fetchone()[0]
    remaining_qualifications = conn.execute(
        'SELECT COUNT(*) FROM qualifications WHERE name_ar = ?', (qualification,)
    ).fetchone()[0]
    remaining_specializations = (
        conn.execute(
            'SELECT COUNT(*) FROM specializations WHERE id = ? AND name = ?',
            (specialization['id'], specialization['name']),
        ).fetchone()[0]
        if specialization else 0
    )
    conn.close()

    assert remaining == 0
    assert remaining_qualifications == 0
    assert remaining_specializations == 0
