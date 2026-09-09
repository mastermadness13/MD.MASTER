"""Smoke tests for the department weekly-timetable page toolbar UX.

Covers: single status badge wording, per-button tooltips, the helper hint,
and the
create-next-year API activating a fresh version.
"""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'tt_department.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('superadmin', 'x', 'super_admin', 'مدير')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    dept_id = conn.execute("SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()['id']
    # Active version for the first available semester (2) — current, editable
    conn.execute(
        "INSERT INTO timetable_versions (department_id, semester, semester_code, status) VALUES (?, 2, 'fall_2026', 'active')",
        (dept_id,),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(app_fx, db_fx):
    c = app_fx.test_client()
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'super_admin'
        sess['username'] = 'superadmin'
        sess['department_id'] = None
        sess['_csrf_token'] = 't'
    return c


def _q(sql, params=()):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.commit()
    conn.close()
    return rows


def _dept_id():
    return _q("SELECT id FROM departments WHERE name='قسم الحاسوب'")[0]['id']


def _version(status):
    return _q(
        "SELECT id FROM timetable_versions WHERE department_id=? AND status=?",
        (_dept_id(), status),
    )[0]['id']


def _read_js():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, '..', 'static', 'js', 'timetable_department.js'),
              encoding='utf-8') as fh:
        return fh.read()


def test_current_table_shows_editable_badge_and_hint(client):
    """الجدول الحالي يُظهر شارة «قابل للتعديل» وسطر المساعدة، بأزرار أدوار واضحة."""
    r = client.get('/timetable/department')
    body = r.get_data(as_text=True)
    js = _read_js()
    assert r.status_code == 200
    # The status labels are built client-side in the external script bundle.
    assert 'الجدول الحالي' in js
    assert 'قابل للتعديل' in js
    assert 'أضِف/عدّل الحصص في الجدول، ثم أنشئ نسخة العام القادم' in body
    # شارة واحدة فقط — ما عاد هنالك «وضع التحرير» ولا «محفوظ (نشط)»
    assert js.count('قابل للتعديل') >= 1
    assert 'وضع التحرير' not in js
    assert 'محفوظ (نشط)' not in js
    # أدوار الأزرار عبر title
    assert 'title="طباعة الجدول الحالي"' in body
    assert 'title="إنشاء نسخة العام القادم"' in body
    assert 'id="nextYearBtn"' in body

def test_create_next_year_activates_new_version(client):
    """واجهة برمجة التطبيقات تنشئ نسخة الفصل القادم وتجعلها نشطة بدل القديمة."""
    active = _version('active')
    r = client.post('/timetable/api/version/create-next', json={
        '_csrf_token': 't',
        'version_id': active,
        'copy_entries': False,
    })
    data = r.get_json()
    assert r.status_code == 200
    assert data['ok'] is True
    assert data['url']
    new_id = data['version_id']

    rows = _q('SELECT id, semester_code, status FROM timetable_versions WHERE department_id=?',
              (_dept_id(),))
    statuses = {row['status'] for row in rows}
    assert 'superseded' in statuses, 'the old current version is superseded'
    new_row = [row for row in rows if row['id'] == new_id][0]
    assert new_row['status'] == 'active', 'the freshly created version becomes active'
    assert new_row['semester_code'] != 'fall_2026', 'name advances to the next semester'