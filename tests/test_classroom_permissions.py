"""Regression tests: القاعات وحدة إدارة ملك مكتب أعضاء هيئة التدريس.

``rooms.manage`` (إنشاء/تعديل/حذف) يعود لمكتب إدارة أعضاء هيئة التدريس.
قسم الدراسة والامتحانات يحتفظ بـ ``rooms.view`` فقط لعرض القاعات عند
جدولة الامتحانات — لا يظهر له تعديل أو حذف ولا تفتح له صفحة التعديل.
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'rooms_perm.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('exam', 'x', 'exam', 'قسم الامتحانات')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    # جداول مرجعية مطلوبة لعرض/تعديل القاعات
    conn.execute(
        "INSERT INTO room_types (name_ar, name_en, sort_order) VALUES ('قاعة دراسية', 'Room', 1)"
    )
    conn.execute(
        "INSERT INTO room_statuses (name_ar, name_en, sort_order) VALUES ('متاحة', 'Available', 1)"
    )
    conn.execute(
        "INSERT INTO rooms (name, code, capacity, room_type_id, status_id, department_id) "
        "VALUES ('قاعة 101', 'R101', 40, 1, 1, NULL)"
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(app_fx, db_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'exam'
        sess['username'] = 'exam'
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    return c


def _room_exists():
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, deleted_at FROM rooms WHERE name='قاعة 101'"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def test_exam_rooms_list_visible_without_manage_buttons(client):
    """قائمة القاعات ظاهرة لقسم الامتحانات (view) بدون أزرار تعديل/حذف."""
    r = client.get('/rooms')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'قاعة 101' in body
    assert '/rooms/edit/' not in body
    assert '/rooms/delete/' not in body


def test_exam_cannot_open_room_edit_page(client):
    """صفحة تعديل القاعة غير مفتوحة لقسم الامتحانات (rooms.manage للfaculty_affairs فقط)."""
    room = _room_exists()
    r = client.get('/rooms/edit/{}'.format(room['id']))
    assert r.status_code == 302


def test_exam_cannot_delete_room(client):
    """حذف القاعة مرفوض لمستخدم قسم الامتحانات."""
    room_id = _room_exists()['id']
    r = client.post(
        '/rooms/delete/{}'.format(room_id),
        data={'_csrf_token': 't'},
    )
    assert r.status_code == 302
    row = _room_exists()
    assert row is None or row['deleted_at'] is None


def test_exam_cannot_edit_room_via_post(client):
    """تعديل القاعة عبر POST مرفوض لمستخدم قسم الامتحانات."""
    room_id = _room_exists()['id']
    r = client.post(
        '/rooms/edit/{}'.format(room_id),
        data={
            '_csrf_token': 't',
            'name': 'قاعة 202',
            'code': 'R202',
            'capacity': 50,
            'room_type_id': '1',
            'status_id': '1',
        },
    )
    assert r.status_code == 302
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT name, capacity FROM rooms WHERE id = ?', (room_id,)).fetchone()
    conn.close()
    assert row['name'] == 'قاعة 101'