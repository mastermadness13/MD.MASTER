"""Regression tests for the teacher qualification edit control."""

import re

import flask_db
import pytest
from database.connection import connect
from database.schema import ensure_schema
from page_routes.teachers import _roles_from_position
from tests.test_bottom_nav import _client_for, _user_id


@pytest.fixture
def office_client(app_fx, tmp_path, monkeypatch):
    db_path = tmp_path / 'teacher_qualification.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as schema:
        conn.executescript(schema.read())
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role, label) "
        "VALUES ('office_manager', 'x', 'faculty_affairs', 'مدير المكتب')"
    )
    qualification_id = conn.execute(
        "INSERT INTO qualifications (name_ar, name_en) VALUES (?, ?)",
        ('بكالوريوس', "Bachelor's degree"),
    ).lastrowid
    teacher_id =     teacher_id = conn.execute(
        "INSERT INTO teachers (name, qualification, qualification_id) "
        "VALUES (?, ?, ?)",
        ('عضو هيئة التدريس', 'بكالوريوس', qualification_id),
    ).lastrowid
    conn.commit()
    conn.close()

    client = _client_for(
        app_fx,
        _user_id(db_path, 'office_manager'),
        'faculty_affairs',
        'office_manager',
    )

    return client, teacher_id, qualification_id


def test_existing_qualification_does_not_populate_custom_entry(office_client):
    client, teacher_id, qualification_id = office_client
    response = client.get(f'/teachers/edit/{teacher_id}')

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    custom_entry = re.search(
        r'<input type="text" name="custom_qualification_id"[^>]*>', body
    )
    assert custom_entry is not None
    assert re.search(r'\bvalue=""', custom_entry.group(0))
    qualification_select = re.search(
        r'<select[^>]*data-editable-select="qualification_id"[^>]*>(.*?)</select>',
        body,
        re.DOTALL,
    )
    assert qualification_select is not None
    assert re.search(
        rf'<option value="{qualification_id}" selected>بكالوريوس</option>',
        qualification_select.group(1),
    )


def test_admin_assignment_options_use_canonical_titles(office_client):
    client, _teacher_id, _qualification_id = office_client
    response = client.get('/teachers/create')
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    position_select = re.search(
        r'<select[^>]*id="positionSelect"[^>]*>(.*?)</select>',
        body,
        re.DOTALL,
    )
    assert position_select is not None
    option_labels = re.findall(
        r'<option\b[^>]*>(.*?)</option>', position_select.group(1)
    )
    assert option_labels.count('رئيس القسم العلمي') == 1
    assert option_labels.count('رئيس قسم') == 0
    assert option_labels.count('قسم الإدارة والامتحانات') == 0
    assert option_labels.count('رئيس قسم الامتحانات') == 1
    assert _roles_from_position('رئيس القسم العلمي') == {'head_of_department'}
