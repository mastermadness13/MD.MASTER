"""Unit tests for the classroom (room) service bulk-create behaviour."""

import sqlite3

import pytest

from database.repositories.room_repository import RoomRepository
from services import classroom_service
from services.classroom_service import ClassroomService

SCHEMA = """
CREATE TABLE IF NOT EXISTS room_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL,
    icon TEXT DEFAULT '',
    css_class TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS room_statuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS floors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    hidden INTEGER DEFAULT 0,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT,
    capacity INTEGER DEFAULT 0,
    building TEXT DEFAULT '',
    department_id INTEGER,
    room_type_id INTEGER,
    status_id INTEGER,
    floor_id INTEGER,
    computers INTEGER DEFAULT 0,
    deleted_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture()
def db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO room_types (name_ar, name_en, sort_order) VALUES (?, ?, ?)",
        ('قاعة دراسية', 'Room', 1),
    )
    conn.execute(
        "INSERT INTO room_statuses (name_ar, sort_order) VALUES (?, ?)",
        ('متاحة', 1),
    )
    conn.commit()
    yield conn
    conn.close()


def room_count(conn) -> int:
    return conn.execute('SELECT COUNT(*) FROM rooms').fetchone()[0]


def fetch_names(conn):
    return [r['name'] for r in conn.execute(
        'SELECT name FROM rooms ORDER BY id'
    ).fetchall()]


def make_service(conn):
    return ClassroomService(conn, RoomRepository(conn))


def make_room_data(**overrides):
    data = {
        'name': 'Lab',
        'code': 'LAB-1',
        'capacity': 24,
        'room_type_id': 1,
        'status_id': 1,
        'floor_id': None,
        'building': 'B',
        'department_id': None,
        'computers': 1,
        'quantity': 1,
    }
    data.update(overrides)
    return data


class TestCreateRoom:
    def test_quantity_one_keeps_base_name(self, db):
        make_service(db).create_room(make_room_data())
        assert room_count(db) == 1
        assert fetch_names(db) == ['Lab']

    def test_bulk_create_generates_numbered_rooms(self, db):
        service = make_service(db)
        service.create_room(make_room_data(quantity=3))
        assert room_count(db) == 3
        assert fetch_names(db) == ['Lab 1', 'Lab 2', 'Lab 3']

    def test_bulk_create_persists_metadata(self, db):
        service = make_service(db)
        last_id = service.create_room(make_room_data(quantity=2))
        rows = [dict(r) for r in db.execute(
            'SELECT * FROM rooms WHERE name LIKE ? ORDER BY id',
            ('Lab%',),
        ).fetchall()]
        assert len(rows) == 2
        assert all(r['computers'] == 1 for r in rows)
        assert all(r['capacity'] == 24 for r in rows)
        assert rows[-1]['id'] == last_id

    def test_bulk_create_rolls_back_on_failure(self, db):
        service = make_service(db)
        repo = service._repo
        calls = {'n': 0}

        def flaky_create(data, commit=True):
            calls['n'] += 1
            if calls['n'] == 2:
                raise RuntimeError('boom')
            return repo.create(data, commit=commit)

        service._repo.create = flaky_create
        with pytest.raises(RuntimeError):
            service.create_room(make_room_data(quantity=3))
        assert calls['n'] == 2
        assert room_count(db) == 0

    def test_module_level_create_room_bulk(self, db):
        classroom_service.create_room(db, make_room_data(quantity=3))
        assert room_count(db) == 3
        assert fetch_names(db) == ['Lab 1', 'Lab 2', 'Lab 3']


class TestUpdateRoom:
    def test_update_persists_computers(self, db):
        service = make_service(db)
        room_id = service.create_room(make_room_data())
        service.update_room(room_id, make_room_data(name='Lab', computers=0))
        row = db.execute('SELECT computers FROM rooms WHERE id = ?', (room_id,)).fetchone()
        assert row['computers'] == 0
        service.update_room(room_id, make_room_data(name='Lab', computers=1))
        row = db.execute('SELECT computers FROM rooms WHERE id = ?', (room_id,)).fetchone()
        assert row['computers'] == 1


class TestLookups:
    def test_get_create_lookups_returns_room_types(self, db):
        lookups = make_service(db).get_create_lookups()
        assert [t['name_ar'] for t in lookups['room_types']] == ['قاعة دراسية']
        assert lookups['statuses'][0]['name_ar'] == 'متاحة'

    def test_module_get_create_lookups(self, db):
        room_types, statuses, floors, departments = classroom_service.get_create_lookups(db)
        assert room_types[0]['name_ar'] == 'قاعة دراسية'


class TestApiRoomForm:
    def _form(self, **data):
        from api.rooms import _room_form
        return _room_form(data)

    def test_computers_parsed_from_variants(self):
        assert self._form(name='X', computers='1')['computers'] == 1
        assert self._form(name='X', computers=1)['computers'] == 1
        assert self._form(name='X', computers=True)['computers'] == 1
        assert self._form(name='X', computers=0)['computers'] == 0
        assert self._form(name='X', computers='0')['computers'] == 0
        assert self._form(name='X')['computers'] == 0

    def test_update_keeps_existing_computers_when_omitted(self):
        from api.rooms import _room_form
        defaults = {'computers': 1}
        form = _room_form({'name': 'X'}, defaults=defaults)
        assert form['computers'] == 1
