# -*- coding: utf-8 -*-
"""Area 3 (general security) — the file-upload boundary.

Area 3 asked one question: *can a file a user uploads come back as active
content in somebody's browser?*  The audit found no reachable path, so this
file does not fix a defect — it **pins the decisions** that were verified, so a
later change that drops one fails loudly instead of silently re-opening the
boundary.

Why the extensions are the whole defence here.  Nothing sniffs the bytes: a
photo is accepted because its *name* ends in ``.jpg``, never because it is a
JPEG.  So the boundary rests on three allowlists, and every one of them is
pinned below.  Serving then adds ``X-Content-Type-Options: nosniff``
globally, so a file whose bytes are HTML but whose name ends ``.jpg`` is
delivered as ``image/jpeg`` and the browser renders it as a broken image rather
than executing it.  ``test_html_bytes_behind_an_allowed_extension_are_served
_as_inert_content`` proves that inertness over real HTTP instead of assuming it.

What is deliberately *not* claimed: that the serving route is safe on its own.
``test_uploads_route_has_no_extension_policy_of_its_own`` records the gap — the
CSP carries ``'unsafe-inline'``, so an SVG in the tree would run, and only the
allowlists keep one out.  It is marked ``xfail`` to keep the gap visible.

Dummy tenants and dummy bytes only; no real user data is touched.
"""

import io
import os
import pathlib
import re
import sqlite3

import pytest
from werkzeug.datastructures import FileStorage

import flask_db
from core.constants.uploads import ALLOWED_UPLOAD_EXTENSIONS
from database.connection import connect
from database.schema import ensure_schema
from page_routes.teachers import _PHOTO_EXTENSIONS, _PHOTO_MAX_BYTES

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Extensions a browser will execute, or render as a document that can script,
# if the response is ever treated as one.  ``svg`` and ``xml`` matter most:
# they are their own document type, so ``nosniff`` does not help and only an
# extension allowlist keeps them out.
EXECUTABLE_EXTENSIONS = {
    'html', 'htm', 'xhtml', 'shtml', 'svg', 'svgz', 'xml', 'xsl', 'xslt',
    'js', 'mjs', 'cjs', 'php', 'phtml', 'asp', 'aspx', 'jsp', 'py', 'pl',
    'cgi', 'exe', 'com', 'bat', 'cmd', 'scr', 'vbs', 'jar', 'hta', 'swf',
}

# A polyglot: valid bytes for nothing in particular, but a complete HTML
# document with an inline script.  If any layer ever sniffs or trusts the
# bytes, this is the payload that would fire.
HTML_PAYLOAD = b'<html><script>alert(document.domain)</script></html>'


def _seed(tmp_path, monkeypatch):
    """One dummy department, a teacher who may upload, and a HOD who may serve.

    Two principals because the boundary is asymmetric by design: the
    ``teacher`` role holds ``uploads.view`` (upload) but *not* ``uploads.serve``,
    while the HOD holds both.  A test that used one role for both halves would
    pass for the wrong reason.
    """
    db_path = tmp_path / 'area3_uploads.db'
    monkeypatch.setattr(flask_db, 'DATABASE', str(db_path))

    conn = connect(str(db_path))
    with open('database/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())

    conn.execute(
        "INSERT INTO departments (name, type) VALUES ('قسم الفحص', 'academic')"
    )
    dept = conn.execute(
        "SELECT id FROM departments WHERE name = 'قسم الفحص'"
    ).fetchone()['id']

    def _user(username, role):
        conn.execute(
            'INSERT INTO users (username, password, role, label) '
            "VALUES (?, 'x', ?, '|area3|')",
            (username, role),
        )
        uid = conn.execute(
            'SELECT id FROM users WHERE username = ?', (username,)
        ).fetchone()['id']
        conn.execute(
            'INSERT INTO user_roles (user_id, role) VALUES (?, ?)', (uid, role)
        )
        return uid

    ids = {'dept': dept}
    for key, role in (('teacher', 'teacher'), ('hod', 'head_of_department')):
        uid = _user(f'a3_{key}', role)
        conn.execute(
            'INSERT INTO teachers (name, user_id, department_id, hod_department_id) '
            "VALUES (?, ?, ?, ?)",
            (f'عضو {key}', uid, dept, dept),
        )
        tid = conn.execute(
            'SELECT id FROM teachers WHERE user_id = ?', (uid,)
        ).fetchone()['id']
        ids[f'{key}_uid'] = uid
        ids[f'{key}_tid'] = tid

    conn.commit()
    ensure_schema(conn)
    conn.commit()
    conn.close()
    return db_path, ids


def _login(client, user_id, role, **extra):
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 't'
        sess['user_id'] = user_id
        sess['role'] = role
        sess['roles'] = [role]
        sess['username'] = f'a3_{role}'
        for k, v in extra.items():
            sess[k] = v


def _norm_ext(value):
    """Reduce a source-literal extension to a bare lowercase token.

    Allowlists are written three different ways in this codebase — bare words
    (``'pdf'``), dotted literals (``'.pdf'``) and quoted literals — so a guard
    that forgets to strip quotes silently compares ``"'html'"`` against
    ``"html"`` and passes forever.  That bug is exactly what reverse validation
    caught the first time round.
    """
    return value.strip().strip('"\'').lstrip('.').lower()


def _material_allowlist():
    """The inline allowlist inside ``teacher_upload``.

    It is a local literal, not a constant, so it has to be read out of the
    source.  Parsing is acceptable here precisely because the test's job is to
    fail the moment someone widens that literal.
    """
    src = (ROOT / 'page_routes' / 'teacher_pages.py').read_text(encoding='utf-8-sig')
    body = src.split('def teacher_upload(', 1)[1].split('\ndef ', 1)[0]
    match = re.search(r'allowed\s*=\s*\{([^}]*)\}', body)
    assert match, 'the inline allowlist in teacher_upload() moved or vanished'
    return {_norm_ext(ext) for ext in match.group(1).split(',') if _norm_ext(ext)}


@pytest.fixture
def world(tmp_path, monkeypatch):
    db_path, ids = _seed(tmp_path, monkeypatch)
    return db_path, ids


@pytest.fixture
def uploads(tmp_path, monkeypatch, app_fx):
    """A real upload tree with real dummy bytes on disk."""
    folder = tmp_path / 'uploads'
    (folder / 'photos').mkdir(parents=True, exist_ok=True)
    (folder / 'secret.txt').write_bytes(b'TOP-SECRET')
    monkeypatch.setitem(app_fx.config, 'UPLOAD_FOLDER', str(folder))
    return folder


def _store(teacher_id, folder, name, data):
    return FileStorage(io.BytesIO(data), filename=name)


# ── 1. the allowlists ────────────────────────────────────────────────────


def test_shared_upload_allowlist_admits_no_executable_extension():
    allowed = {_norm_ext(e) for e in ALLOWED_UPLOAD_EXTENSIONS}
    leaked = EXECUTABLE_EXTENSIONS & allowed
    assert not leaked, f'core upload policy now accepts active content: {sorted(leaked)}'


def test_photo_allowlist_admits_no_executable_extension():
    allowed = {_norm_ext(e) for e in _PHOTO_EXTENSIONS}
    leaked = EXECUTABLE_EXTENSIONS & allowed
    assert not leaked, f'photo policy now accepts active content: {sorted(leaked)}'


def test_material_allowlist_admits_no_executable_extension():
    allowed = _material_allowlist()
    assert allowed, 'parsed an empty material allowlist'
    leaked = EXECUTABLE_EXTENSIONS & allowed
    assert not leaked, f'material policy now accepts active content: {sorted(leaked)}'


# ── 2. profile photos: the accept/reject decisions themselves ────────────


@pytest.mark.parametrize('name', ['evil.html', 'evil.htm', 'evil.svg', 'evil.xml',
                                 'evil.js', 'evil.php', 'evil.exe', 'noextension'])
def test_photo_upload_rejects_active_or_unnamed_extension(app_fx, uploads, name):
    with app_fx.test_request_context():
        from page_routes.teachers import _store_teacher_photo
        with pytest.raises(ValueError):
            _store_teacher_photo(1, _store(1, uploads, name, HTML_PAYLOAD))
    assert not list((uploads / 'photos').iterdir()), f'{name} reached the disk'


def test_photo_upload_rejects_oversized_file(app_fx, uploads):
    with app_fx.test_request_context():
        from page_routes.teachers import _store_teacher_photo
        oversized = b'\x00' * (_PHOTO_MAX_BYTES + 1)
        with pytest.raises(ValueError):
            _store_teacher_photo(1, _store(1, uploads, 'big.jpg', oversized))
    assert not list((uploads / 'photos').iterdir()), 'oversized photo reached the disk'


def test_photo_upload_rejects_empty_file(app_fx, uploads):
    with app_fx.test_request_context():
        from page_routes.teachers import _store_teacher_photo
        with pytest.raises(ValueError):
            _store_teacher_photo(1, _store(1, uploads, 'empty.jpg', b''))
    assert not list((uploads / 'photos').iterdir()), 'empty photo reached the disk'


def test_photo_upload_stores_a_generated_name_outside_user_control(app_fx, uploads):
    """The stored name is built from the teacher id and a uuid, not the upload."""
    with app_fx.test_request_context():
        from page_routes.teachers import _store_teacher_photo
        relative = _store_teacher_photo(
            7, _store(7, uploads, '../../../../etc/passwd.jpg', b'\xff\xd8\xff\xe0JFIF')
        )
    assert relative.startswith('photos/teacher_7_')
    assert '..' not in relative and '/' not in relative[len('photos/'):]
    stored = uploads / relative
    assert stored.is_file() and stored.read_bytes() == b'\xff\xd8\xff\xe0JFIF'


# ── 3. the upload route: traversal and active content, over HTTP ─────────


def _upload(client, filename, data=b'%PDF-1.4 dummy\n', **extra):
    payload = {'title': 'مادة', 'file_type': 'other', '_csrf_token': 't'}
    payload.update(extra)
    return client.post(
        '/teacher/upload',
        data={**payload, 'file': (io.BytesIO(data), filename)},
        content_type='multipart/form-data',
    )


def test_material_upload_with_traversal_filename_stays_inside_upload_folder(
    app_fx, world, uploads
):
    """A traversing ``filename`` must not become a path component on disk.

    The submitted name is still recorded in ``original_filename`` for display,
    which is why the assertion is about the *stored* path and the filesystem,
    not about the name being absent from the row.
    """
    db_path, ids = world
    c = app_fx.test_client()
    _login(c, ids['teacher_uid'], 'teacher', department_id=ids['dept'])

    r = _upload(c, '../../../../escape.pdf')
    assert r.status_code == 302, f'upload was not accepted (status {r.status_code})'

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        'SELECT filename, original_filename FROM teacher_materials ORDER BY id DESC LIMIT 1'
    ).fetchone()
    conn.close()

    stored = row['filename']
    assert row['original_filename'] == '../../../../escape.pdf'
    assert stored.startswith(f"teacher_{ids['teacher_tid']}/")
    assert '..' not in stored and '\\' not in stored
    # one real file, inside the teacher's own folder
    assert [p.name for p in (uploads / f"teacher_{ids['teacher_tid']}").iterdir()] == [
        stored.split('/', 1)[1]
    ]
    assert not list(uploads.parent.rglob('escape.pdf')), 'a file escaped the upload root'


def test_material_upload_rejects_html_and_writes_nothing(app_fx, world, uploads):
    db_path, ids = world
    teacher_dir = uploads / f"teacher_{ids['teacher_tid']}"
    teacher_dir.mkdir(parents=True, exist_ok=True)
    c = app_fx.test_client()
    _login(c, ids['teacher_uid'], 'teacher', department_id=ids['dept'])

    r = _upload(c, 'evil.html', data=HTML_PAYLOAD)
    assert r.status_code == 200
    assert 'نوع الملف غير مدعوم' in r.get_data(as_text=True)
    assert list(teacher_dir.iterdir()) == [], 'a rejected upload still reached the disk'

    conn = sqlite3.connect(str(db_path))
    count = conn.execute('SELECT COUNT(*) FROM teacher_materials').fetchone()[0]
    conn.close()
    assert count == 0, 'a rejected upload still created a row'


# ── 4. the serving route: traversal and folder ownership ────────────────


@pytest.fixture
def served(app_fx, world, uploads):
    """A HOD's own teacher folder holding a real dummy file.

    The file must live in the *caller's own* folder: ``_allowed_folder_prefixes``
    grants ``teacher_<user_id>`` plus the folders of teachers linked to the
    caller, so a file in a colleague's folder is refused — correctly, but for a
    reason that has nothing to do with traversal.
    """
    _, ids = world
    folder = uploads / f"teacher_{ids['hod_tid']}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'polyglot.jpg').write_bytes(HTML_PAYLOAD)
    c = app_fx.test_client()
    _login(c, ids['hod_uid'], 'head_of_department',
           department_id=ids['dept'], hod_department_id=ids['dept'])
    return c, folder


def test_uploads_route_serves_the_callers_own_folder(served):
    """Positive control: without this, every refusal below proves nothing."""
    c, folder = served
    r = c.get(f'/uploads/{folder.name}/polyglot.jpg')
    assert r.status_code == 200, 'own-folder baseline drifted'


@pytest.mark.parametrize('suffix', [
    '../secret.txt',
    '../../secret.txt',
    '..%2fsecret.txt',
    '..%5csecret.txt',
    '%2e%2e%2fsecret.txt',
    '....//secret.txt',
    '%2e%2e/%2e%2e/secret.txt',
])
def test_uploads_route_rejects_traversal(app_fx, served, suffix):
    """No traversal variant may escape the upload root.

    The status is deliberately not pinned to 403: ``..`` is refused by the
    handler, while a variant like ``....//`` carries no ``..`` segment at all
    and simply fails to resolve (404).  Both are refusals, and the property
    worth pinning is that the file outside the root is never served.
    """
    c, folder = served
    r = c.get(f'/uploads/{folder.name}/{suffix}')
    assert r.status_code in (403, 404), f'{suffix} was not refused (status {r.status_code})'
    assert b'TOP-SECRET' not in r.data


def test_uploads_route_refuses_another_owners_folder(app_fx, world, uploads):
    _, ids = world
    other = uploads / f"teacher_{ids['teacher_tid']}"
    other.mkdir(parents=True, exist_ok=True)
    (other / 'private.jpg').write_bytes(HTML_PAYLOAD)
    c = app_fx.test_client()
    _login(c, ids['hod_uid'], 'head_of_department',
           department_id=ids['dept'], hod_department_id=ids['dept'])
    r = c.get(f'/uploads/{other.name}/private.jpg')
    assert r.status_code == 403, 'a folder owned by another teacher was served'


def test_teacher_role_cannot_serve_uploads_at_all(app_fx, world, uploads):
    """``uploads.view`` is upload rights; it must not imply download rights."""
    db_path, ids = world
    folder = uploads / f"teacher_{ids['teacher_tid']}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'mine.jpg').write_bytes(HTML_PAYLOAD)
    c = app_fx.test_client()
    _login(c, ids['teacher_uid'], 'teacher', department_id=ids['dept'])
    r = c.get(f'/uploads/{folder.name}/mine.jpg')
    # permission_required redirects an unprivileged caller rather than
    # rendering a 403, so the denial shows up as a 302 away from the file.
    assert r.status_code in (302, 403, 404), (
        f'the teacher role reached the serving route (status {r.status_code})'
    )
    assert r.data != HTML_PAYLOAD, 'the file was served to a role without uploads.serve'


# ── 5. why the extensions are sufficient: the bytes are never trusted ────


def test_html_bytes_behind_an_allowed_extension_are_served_as_inert_content(
    app_fx, world, uploads
):
    """The non-exploitability claim, demonstrated rather than assumed.

    HTML bytes behind an allowed name must arrive under a non-executable
    content type with ``nosniff`` set, because that pair — not any content
    inspection — is what stops them running.
    """
    _, ids = world
    folder = uploads / f"teacher_{ids['hod_tid']}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'polyglot.jpg').write_bytes(HTML_PAYLOAD)
    (folder / 'polyglot.txt').write_bytes(HTML_PAYLOAD)

    c = app_fx.test_client()
    _login(c, ids['hod_uid'], 'head_of_department',
           department_id=ids['dept'], hod_department_id=ids['dept'])

    jpg = c.get(f'/uploads/{folder.name}/polyglot.jpg')
    assert jpg.status_code == 200
    assert jpg.headers['Content-Type'].split(';')[0] == 'image/jpeg'
    assert jpg.headers['X-Content-Type-Options'] == 'nosniff'
    assert jpg.data == HTML_PAYLOAD, 'the file was altered, so the type is not the defence'

    txt = c.get(f'/uploads/{folder.name}/polyglot.txt')
    assert txt.status_code == 200
    assert txt.headers['Content-Type'].split(';')[0] == 'text/plain'
    assert txt.headers['X-Content-Type-Options'] == 'nosniff'


@pytest.mark.xfail(
    reason=(
        'defense-in-depth gap, not a reachable vulnerability: /uploads/ applies no '
        'extension or content-type policy of its own, so a file already in the tree is '
        "served inline under its native type. CSP carries 'unsafe-inline', so an SVG or "
        'HTML file would run. Today no upload path can produce one — the three '
        'allowlists above are the only barrier — but a future allowlist change or a '
        'second writer into the tree would re-open stored XSS with no second gate.'
    ),
    strict=False,
)
def test_uploads_route_has_no_extension_policy_of_its_own(app_fx, world, uploads):
    _, ids = world
    folder = uploads / f"teacher_{ids['hod_tid']}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'planted.svg').write_bytes(HTML_PAYLOAD)
    c = app_fx.test_client()
    _login(c, ids['hod_uid'], 'head_of_department',
           department_id=ids['dept'], hod_department_id=ids['dept'])
    r = c.get(f'/uploads/{folder.name}/planted.svg')
    assert r.status_code == 403, (
        'the serving route now refuses active content — drop the xfail and record '
        'the policy that replaced this'
    )
