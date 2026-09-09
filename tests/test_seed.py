"""Tests for seed deduplication — bootstrap_defaults must not create duplicates."""

import sqlite3

import pytest

import flask_db
from database.connection import connect
from database.schema import ensure_schema


@pytest.fixture
def db_fx(tmp_path, monkeypatch):
    db_path = tmp_path / 'seed_test.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.close()
    return db_path


def _count_teachers(db_path):
    conn = sqlite3.connect(str(db_path))
    n = conn.execute('SELECT COUNT(*) FROM teachers').fetchone()[0]
    conn.close()
    return n


def _teacher_names(db_path):
    conn = sqlite3.connect(str(db_path))
    names = {r[0] for r in conn.execute('SELECT name FROM teachers').fetchall()}
    conn.close()
    return names


def test_bootstrap_defaults_creates_teachers(db_fx):
    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_fx))
    assert _count_teachers(db_fx) > 0


def test_bootstrap_defaults_no_duplicates_on_second_run(db_fx):
    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_fx))
    count_after_first = _count_teachers(db_fx)
    names_after_first = _teacher_names(db_fx)

    bootstrap_defaults(str(db_fx))
    count_after_second = _count_teachers(db_fx)
    names_after_second = _teacher_names(db_fx)

    assert count_after_second == count_after_first, (
        f"Second bootstrap_defaults run created duplicates: "
        f"{count_after_first} -> {count_after_second}"
    )
    assert names_after_second == names_after_first
