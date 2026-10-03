# -*- coding: utf-8 -*-
"""رئيس قسم الدراسة والامتحانات (exam) — الأقسام فقط.

The exam role sees «الأقسام» in its sidebar and manages departments
(departments.manage). Since الجدول الدراسي (timetable) is no longer part of
the exams department, the role must NOT see the timetable nav item and must
not be able to open or edit timetable pages.
"""

import json
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'exam_role.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)

    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('examoffice', 'x', 'exam', 'رئيس قسم الدراسة والامتحانات')"
    )
    conn.execute(
        "INSERT INTO departments (name, semesters, majors, hidden, has_sections, type) "
        "VALUES ('قسم الحاسوب', 8, 8, 0, 1, 'academic')"
    )
    dept_id = conn.execute(
        "SELECT id FROM departments WHERE name='قسم الحاسوب'").fetchone()['id']
    conn.execute(
        "INSERT INTO teachers (name, department_id) VALUES ('مدرس الأول', ?)",
        (dept_id,),
    )
    conn.execute("INSERT INTO rooms (name) VALUES ('قاعة 101')")
    conn.execute(
        "INSERT INTO courses (code, name, year, theoretical_hours, practical_hours, total_hours) "
        "VALUES ('CS101', 'مقرر اختبار', 1, 2, 0, 2)"
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(app_fx, db_fx):
    c = app_fx.test_client()
    exam_user_id = _q(
        "SELECT id FROM users WHERE username='examoffice'"
    )[0]['id']
    with c.session_transaction() as sess:
        sess['user_id'] = exam_user_id
        sess['role'] = 'exam'
        sess['username'] = 'examoffice'
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


def _ids(db_fx):
    """Resolve seeded ids for the exam role fixtures."""
    dept_id = _q("SELECT id FROM departments WHERE name='قسم الحاسوب'")[0]['id']
    teacher_id = _q("SELECT id FROM teachers WHERE name='مدرس الأول'")[0]['id']
    room_id = _q("SELECT id FROM rooms WHERE name='قاعة 101'")[0]['id']
    course_id = _q("SELECT id FROM courses WHERE code='CS101'")[0]['id']
    return {
        'dept_id': dept_id, 'teacher_id': teacher_id,
        'room_id': room_id, 'course_id': course_id,
    }


def test_exam_nav_shows_departments_without_timetable(app_fx):
    """«الأقسام» تظهر في قائمة الامتحانات ولا يظهر «الجدول الدراسي»."""
    from flask import session
    from security.authorization import inject_navigation
    with app_fx.test_request_context('/'):
        session['role'] = 'exam'
        session['roles'] = ['exam']
        eps = {i['endpoint'] for i in inject_navigation()['nav_items']}
    assert 'departments.departments_list' in eps
    assert 'timetable.timetable' not in eps


def test_exam_views_departments_page(client, db_fx):
    """صفحة الأقسام تفتح لدور الامتحانات وتعرض القسم الموجود."""
    r = client.get('/departments')
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'قسم الحاسوب' in body


def test_exam_creates_department(client, db_fx):
    """دور الامتحانات يقدر يضيف قسم جديد (صلاحية departments.manage)."""
    r = client.post('/departments/create', data={
        'name': 'قسم جديد', 'semesters': 4, 'majors': 3, '_csrf_token': 't',
    })
    assert r.status_code == 302
    rows = _q("SELECT name FROM departments WHERE name='قسم جديد'")
    assert rows and rows[0]['name'] == 'قسم جديد'


def test_exam_cannot_view_weekly_timetable(client, db_fx):
    """الجدول الأسبوعي محجوب عن الامتحانات (لا يملك timetable.view)."""
    dept_id = _ids(db_fx)['dept_id']
    r = client.get('/timetable/department?department_id={}&semester=2'.format(dept_id))
    assert r.status_code == 302


def test_exam_cannot_create_timetable_entry(client, db_fx):
    """الامتحانات لا تقدر تضيف حصة في الجدول (لا تملك timetable.edit)."""
    ids = _ids(db_fx)
    r = client.post('/timetable/create', data={
        'day': 'الأحد', 'semester': 2, 'section': 'A',
        'course_id': ids['course_id'], 'teacher_id': ids['teacher_id'],
        'room_id': ids['room_id'], 'department_id': ids['dept_id'],
        'start_time': '08:00', 'end_time': '09:00',
        'lecture_type': 'theory', 'hours': 1,
        '_csrf_token': 't',
    })
    assert r.status_code == 302
    rows = _q(
        'SELECT teacher_id, department_id FROM timetable '
        'WHERE department_id=? AND semester=? AND teacher_id=?',
        (ids['dept_id'], 2, ids['teacher_id']),
    )
    assert len(rows) == 0


def test_delete_confirmation_uses_native_top_layer_dialog():
    with open('templates/shared/layouts/base.html', encoding='utf-8') as f:
        base_layout = f.read()
    with open('static/js/confirm_dialog.js', encoding='utf-8') as f:
        dialog_script = f.read()
    with open('static/css/components/modals.css', encoding='utf-8') as f:
        modal_styles = f.read()

    assert '<dialog class="modal-overlay confirm-overlay" id="confirmDialog"' in base_layout
    assert "overlay.showModal()" in dialog_script
    assert "overlay.addEventListener('cancel'" in dialog_script
    assert "e.key === 'Escape' && overlay.open" in dialog_script
    assert "dataset.confirmDialogWired" in dialog_script
    assert '.confirm-overlay::backdrop' in modal_styles
    assert '.confirm-overlay[open]' in modal_styles


def test_exam_schedule_changes_record_actor_and_before_after_values(client, db_fx):
    ids = _ids(db_fx)
    headers = {'X-CSRFToken': 't'}
    payload = {
        'dept_id': ids['dept_id'],
        'semester': 1,
        'week': 1,
        'day': 'الأحد',
        'course_id': ids['course_id'],
        'room_id': ids['room_id'],
        'start_time': '09:00',
        'end_time': '10:00',
        'exam_type': 'written',
    }

    created = client.post(
        '/api/exams/department-schedule/cell', json=payload, headers=headers
    )
    assert created.status_code == 200
    schedule_id = created.get_json()['data']['id']

    updated = client.post(
        '/api/exams/department-schedule/cell',
        json={**payload, 'schedule_id': schedule_id, 'start_time': '10:00',
              'end_time': '11:00'},
        headers=headers,
    )
    assert updated.status_code == 200

    deleted = client.delete(
        f'/api/exams/department-schedule/cell/{schedule_id}', headers=headers
    )
    assert deleted.status_code == 200

    events = _q(
        "SELECT action, actor_user_id, actor_username, old_value, new_value "
        "FROM history WHERE entity_type='exam_schedule' AND entity_id=? "
        "ORDER BY id",
        (schedule_id,),
    )
    assert [event['action'] for event in events] == [
        'create', 'update', 'delete',
    ]
    assert all(event['actor_username'] == 'examoffice' for event in events)
    assert all(
        event['actor_user_id'] == _q(
            "SELECT id FROM users WHERE username='examoffice'"
        )[0]['id']
        for event in events
    )
    assert json.loads(events[0]['new_value'])['start_time'] == '09:00'
    assert json.loads(events[1]['old_value'])['start_time'] == '09:00'
    assert json.loads(events[1]['new_value'])['start_time'] == '10:00'
    assert json.loads(events[2]['old_value'])['start_time'] == '10:00'
    assert events[2]['new_value'] is None


# ── the exam period is the publish gate for the public site ──────────────────
# The public site (/index.html#exams) calls /public/api/exam-schedule, which
# builds the payload with published_only=True. Publishing the period must be
# what makes the whole schedule public in one go; a draft period must expose
# nothing, so a half-built schedule never leaks.

def _seed_exam(ids, period_status='draft'):
    conn = sqlite3.connect(flask_db.DATABASE)
    conn.execute('DELETE FROM exam_settings')
    conn.execute(
        "INSERT INTO exam_settings "
        "(exam_start_date, exam_end_date, period_status) VALUES (?, ?, ?)",
        ('2026-09-01', '2026-10-30', period_status),
    )
    conn.execute(
        'INSERT INTO exam_schedule '
        '(department_id, course_id, room_id, week, day_ar, semester, '
        "start_time, end_time, exam_type, status) "
        "VALUES (?, ?, ?, 1, 'الأحد', 2, '09:00', '10:00', 'written', 'scheduled')",
        (ids['dept_id'], ids['course_id'], ids['room_id']),
    )
    conn.commit()
    conn.close()


def _public_exam_count(app_fx):
    payload = app_fx.test_client().get('/public/api/exam-schedule').get_json()
    return sum(len(d.get('exams') or []) for d in payload['departments'])


def test_draft_period_publishes_nothing(app_fx, db_fx):
    """While the period is a draft the public site sees no exam at all."""
    _seed_exam(_ids(db_fx), period_status='draft')
    assert _public_exam_count(app_fx) == 0


def test_publishing_the_period_reveals_the_whole_schedule(app_fx, db_fx):
    """One publish action exposes every scheduled row, whatever its status.

    Rows stay 'scheduled' here: the period is the gate, so no per-row publish
    step is required.
    """
    ids = _ids(db_fx)
    _seed_exam(ids, period_status='draft')
    assert _public_exam_count(app_fx) == 0

    _q("UPDATE exam_settings SET period_status='published'")
    assert _public_exam_count(app_fx) == 1


def test_saving_the_period_dates_returns_it_to_draft(app_fx, db_fx, client):
    """Editing the dates must not leave a stale published period public."""
    ids = _ids(db_fx)
    _seed_exam(ids, period_status='published')
    assert _public_exam_count(app_fx) == 1

    r = client.put('/api/exams/semester-period', json={
        'exam_start_date': '2026-09-06', 'exam_end_date': '2026-10-24',
        '_csrf_token': 't',
    })
    assert r.status_code == 200
    assert _q("SELECT period_status FROM exam_settings")[0]['period_status'] == 'draft'
    assert _public_exam_count(app_fx) == 0


def test_period_publish_endpoint_flips_the_gate(app_fx, db_fx, client):
    """The publish route the UI button calls must open the gate."""
    _seed_exam(_ids(db_fx), period_status='draft')
    r = client.post('/api/exams/period/publish', json={'_csrf_token': 't'})
    assert r.status_code == 200
    assert _q("SELECT period_status FROM exam_settings")[0]['period_status'] == 'published'
    assert _public_exam_count(app_fx) == 1