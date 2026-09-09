"""Phase 2: neither ensure_schema nor bootstrap_defaults may seed a hardcoded
admin123 default. Password policy is shared: ADMIN_PASSWORD env, else a random
password printed once on creation. Existing accounts are never overwritten.
"""

import re

import pytest
from werkzeug.security import check_password_hash

import flask_db
from database.connection import connect
from database.schema import ensure_schema

_PW_PAT = re.compile(r'password: (\S+)')


def _make_db(tmp_path, monkeypatch, admin_password):
    db_path = tmp_path / 'seed_pw_test.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))
    if admin_password is None:
        monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    else:
        monkeypatch.setenv('ADMIN_PASSWORD', admin_password)
    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())
    ensure_schema(conn)
    conn.close()
    return db_path


def _pws(db_path):
    conn = connect(str(db_path))
    rows = {r[0]: r[1] for r in conn.execute('SELECT username, password FROM users').fetchall()}
    conn.close()
    return rows


def test_fresh_db_generates_random_password_not_admin123(tmp_path, monkeypatch, capsys):
    db_path = _make_db(tmp_path, monkeypatch, None)
    pws = _pws(db_path)
    assert 'superadmin' in pws
    assert not check_password_hash(pws['superadmin'], 'admin123')
    m = _PW_PAT.search(capsys.readouterr().out)
    assert m, 'expected a printed generated password'
    assert check_password_hash(pws['superadmin'], m.group(1))


def test_admin_password_env_is_used_everywhere(tmp_path, monkeypatch, capsys):
    db_path = _make_db(tmp_path, monkeypatch, 'S3curePass!2026')
    pws = _pws(db_path)
    assert check_password_hash(pws['superadmin'], 'S3curePass!2026')
    assert 'generated super_admin password:' not in capsys.readouterr().out

    from scripts.seed import bootstrap_defaults
    bootstrap_defaults(str(db_path))
    pws2 = _pws(db_path)
    assert check_password_hash(pws2['superadmin'], 'S3curePass!2026')
    assert check_password_hash(pws2['admin'], 'S3curePass!2026')
    assert 'generated login superadmin/admin password:' not in capsys.readouterr().out


def test_existing_account_password_never_overwritten(tmp_path, monkeypatch, capsys):
    _make_db(tmp_path, monkeypatch, 'First-Pass!')
    from scripts.seed import bootstrap_defaults
    dp = str(tmp_path / 'seed_pw_test.db')
    superadmin_before = _pws(dp)['superadmin']

    monkeypatch.setenv('ADMIN_PASSWORD', 'Second-Pass!')
    bootstrap_defaults(dp)

    pws = _pws(dp)
    assert pws['superadmin'] == superadmin_before
    assert check_password_hash(pws['superadmin'], 'First-Pass!')
    assert 'generated login superadmin/admin password:' not in capsys.readouterr().out