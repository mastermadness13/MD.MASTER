"""Tests for teacher deduplication migration, FK integrity, and audit."""

import json
import os
import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import (
    _deduplicate_teachers_v1,
    _ensure_academic_number_index,
    _ensure_migration_log,
    _mark_migration_done,
    _verify_teacher_fk_integrity,
    ensure_schema,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERGES_PATH = os.path.join(PROJECT_ROOT, 'scripts', 'approved_teacher_merges.json')


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'dedup_test.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.close()
    return db_path


def _conn(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _insert_teacher(conn, name, academic_number=None, user_id=None, email=''):
    conn.execute(
        'INSERT INTO teachers (name, academic_number, user_id, email) '
        'VALUES (?, ?, ?, ?)',
        (name, academic_number, user_id, email),
    )
    conn.commit()
    return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def _insert_timetable(conn, teacher_id):
    conn.execute(
        'INSERT INTO timetable (day, semester, teacher_id, period) '
        'VALUES (?, ?, ?, ?)',
        ('الأحد', 1, teacher_id, 'الفترة الأولى'),
    )
    conn.commit()
    return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def _write_merges(merges):
    with open(MERGES_PATH, 'w', encoding='utf-8') as f:
        json.dump(merges, f)


def _cleanup_merges():
    if os.path.exists(MERGES_PATH):
        os.remove(MERGES_PATH)


@pytest.fixture(autouse=True)
def cleanup_merges_file():
    yield
    _cleanup_merges()


def test_dedup_dry_run_no_merges_file(db_fx):
    """When no approved_teacher_merges.json exists, nothing happens."""
    _cleanup_merges()
    conn = _conn(db_fx)
    _ensure_migration_log(conn)
    _deduplicate_teachers_v1(conn)
    conn.close()


def test_dedup_merges_approved_groups(db_fx):
    """Approved merge groups migrate FKs and delete duplicates."""
    conn = _conn(db_fx)

    canonical_id = _insert_teacher(conn, 'عذارى الادريسي', user_id=10)
    dup1_id = _insert_teacher(conn, 'عذارى الادريسي')
    dup2_id = _insert_teacher(conn, 'عذارى الادريسي')

    tt_id = _insert_timetable(conn, dup1_id)

    _write_merges({
        "groups": [{
            "canonical_teacher_id": canonical_id,
            "duplicate_teacher_ids": [dup1_id, dup2_id],
            "matched_by": "approved_name_match",
            "approved": True,
        }]
    })

    _ensure_migration_log(conn)
    _deduplicate_teachers_v1(conn)

    # Canonical still exists
    assert conn.execute(
        'SELECT id FROM teachers WHERE id = ?', (canonical_id,)
    ).fetchone() is not None

    # Duplicates deleted
    assert conn.execute(
        'SELECT id FROM teachers WHERE id = ?', (dup1_id,)
    ).fetchone() is None
    assert conn.execute(
        'SELECT id FROM teachers WHERE id = ?', (dup2_id,)
    ).fetchone() is None

    # Timetable migrated
    tt = conn.execute(
        'SELECT teacher_id FROM timetable WHERE id = ?', (tt_id,)
    ).fetchone()
    assert tt['teacher_id'] == canonical_id

    # Audit records exist
    audit = conn.execute(
        'SELECT * FROM teacher_dedup_audit WHERE canonical_teacher_id = ?',
        (canonical_id,),
    ).fetchall()
    assert len(audit) == 2

    conn.close()


def test_dedup_not_run_twice(db_fx):
    """Migration is idempotent — _migration_log prevents re-run."""
    conn = _conn(db_fx)
    _ensure_migration_log(conn)
    _mark_migration_done(conn, 'deduplicate_teachers_v1')
    _deduplicate_teachers_v1(conn)
    conn.close()


def test_academic_number_sentinels_normalized(db_fx):
    """Sentinel values in academic_number are collapsed to NULL."""
    conn = _conn(db_fx)
    sentinels = ['', '0', 'غير محدد', '—', '-', 'N/A', 'null', '  ']
    for s in sentinels:
        conn.execute(
            'INSERT INTO teachers (name, academic_number) VALUES (?, ?)',
            (f'teacher_{s!r}', s),
        )
    conn.execute(
        'INSERT INTO teachers (name, academic_number) VALUES (?, ?)',
        ('real_teacher', 'AN-REAL-001'),
    )
    conn.commit()

    _ensure_academic_number_index(conn)

    non_null = conn.execute(
        "SELECT COUNT(*) FROM teachers WHERE academic_number IS NOT NULL"
    ).fetchone()[0]
    assert non_null == 1

    real = conn.execute(
        "SELECT academic_number FROM teachers WHERE name = 'real_teacher'"
    ).fetchone()
    assert real['academic_number'] == 'AN-REAL-001'
    conn.close()


def test_academic_number_unique_constraint(db_fx):
    """Two teachers with same non-NULL academic_number raises IntegrityError."""
    conn = _conn(db_fx)
    _ensure_academic_number_index(conn)

    conn.execute(
        'INSERT INTO teachers (name, academic_number) VALUES (?, ?)',
        ('teacher1', 'AN-DUP'),
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            'INSERT INTO teachers (name, academic_number) VALUES (?, ?)',
            ('teacher2', 'AN-DUP'),
        )
        conn.commit()
    conn.close()


def test_fk_integrity_check_passes_clean(db_fx):
    """No warnings when all FK references are valid."""
    conn = _conn(db_fx)
    _insert_teacher(conn, 'test_teacher')
    _verify_teacher_fk_integrity(conn)
    conn.close()


def test_dedup_migration_handles_nonexistent_ids(db_fx):
    """If migration references non-existent IDs, it handles gracefully."""
    conn = _conn(db_fx)
    canonical_id = _insert_teacher(conn, 'canon', user_id=1)
    dup_id = _insert_teacher(conn, 'dup')

    _write_merges({
        "groups": [{
            "canonical_teacher_id": canonical_id,
            "duplicate_teacher_ids": [99999],
            "matched_by": "test",
            "approved": True,
        }]
    })

    _ensure_migration_log(conn)
    _deduplicate_teachers_v1(conn)

    # Both still exist (bad group skipped)
    assert conn.execute(
        'SELECT id FROM teachers WHERE id = ?', (canonical_id,)
    ).fetchone() is not None
    assert conn.execute(
        'SELECT id FROM teachers WHERE id = ?', (dup_id,)
    ).fetchone() is not None
    conn.close()


def test_dedup_not_approved_skipped(db_fx):
    """Non-approved groups in the JSON are skipped."""
    conn = _conn(db_fx)
    canonical_id = _insert_teacher(conn, 'canon', user_id=1)
    dup_id = _insert_teacher(conn, 'dup')

    _write_merges({
        "groups": [{
            "canonical_teacher_id": canonical_id,
            "duplicate_teacher_ids": [dup_id],
            "matched_by": "test",
            "approved": False,
        }]
    })

    _ensure_migration_log(conn)
    _deduplicate_teachers_v1(conn)

    assert conn.execute(
        'SELECT id FROM teachers WHERE id = ?', (dup_id,)
    ).fetchone() is not None, "Non-approved duplicate should NOT be deleted"
    conn.close()
