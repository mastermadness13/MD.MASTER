"""Create one private folder per user from the shared template.

Every row in the ``users`` table gets its own ``teacher_<id>`` folder inside
``private/faculty``.  Each folder is an empty copy of the shared template
``private/faculty/_template`` (certificates, contracts, documents, materials,
profile, requests, uploads) so every account starts with a complete, isolated
workspace.

Folder naming:
  * ``teacher_<teacher_id>`` when the user is linked to a ``teachers`` row
    (matches the existing ``uploads/teacher_<id>`` convention), otherwise
    ``teacher_<user_id>``.

Existing uploaded files (``uploads/teacher_<id>``) are copied into the user's
``uploads`` subfolder so every user's files live inside their own folder.

Usage::

    python scripts/setup_user_folders.py [--db PATH] [--private-faculty PATH]
        [--uploads PATH] [--role ROLE ...] [--no-sync-uploads] [--dry-run]
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

BASE = Path(__file__).resolve().parent
APP_ROOT = BASE.parent
WORKSPACE_ROOT = BASE.parents[2]

TEMPLATE_SUBDIRS = [
    'certificates',
    'contracts',
    'documents',
    'materials',
    'profile',
    'requests',
    'uploads',
]


def default_private_faculty() -> Path:
    candidate = WORKSPACE_ROOT / 'private' / 'faculty'
    if candidate.is_dir():
        return candidate
    return APP_ROOT / 'private' / 'faculty'


def default_db() -> Path:
    return APP_ROOT / 'database' / 'data.db'


def default_uploads() -> Path:
    return APP_ROOT / 'uploads'


def ensure_template(target: Path, dry_run: bool = False) -> Path:
    """Ensure the shared template folder exists under *target*."""
    template_dir = target / '_template'
    if not template_dir.exists() and not dry_run:
        template_dir.mkdir(parents=True)
    for sub in TEMPLATE_SUBDIRS:
        sub_dir = template_dir / sub
        if not sub_dir.exists() and not dry_run:
            sub_dir.mkdir(parents=True)
    return template_dir


def load_users(db_path: Path, roles: list[str]):
    """Return (users, teacher_id_by_user_id) from the database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    query = 'SELECT id, username, role, label FROM users'
    params: list = []
    if roles:
        placeholders = ','.join('?' for _ in roles)
        query += f' WHERE role IN ({placeholders})'
        params = roles
    query += ' ORDER BY id'
    users = [dict(r) for r in conn.execute(query, params).fetchall()]
    teacher_by_user = {}
    for row in conn.execute(
        'SELECT id, user_id FROM teachers WHERE user_id IS NOT NULL'
    ).fetchall():
        teacher_by_user[row['user_id']] = row['id']
    conn.close()
    return users, teacher_by_user


def resolve_folder_names(users: list[dict], teacher_by_user: dict):
    """Map user id -> folder name, giving linked teachers the canonical name.

    Teacher-linked users keep ``teacher_<teacher_id>`` (matching the uploads
    convention).  Users without a linked teacher get ``teacher_<user_id>`` and
    fall back to a suffixed name if that one is already taken.
    """
    # Teacher-linked users first so their canonical names are never stolen.
    ordered = sorted(
        users,
        key=lambda u: (u['id'] in teacher_by_user, u['id']),
        reverse=True,
    )
    assigned: dict[int, str] = {}
    used: set[str] = set()
    collisions: list[str] = []
    for user in ordered:
        uid = user['id']
        teacher_id = teacher_by_user.get(uid)
        if teacher_id is not None:
            preferred = f'teacher_{teacher_id}'
        else:
            preferred = f'teacher_{uid}'
        if preferred in used:
            base = f'teacher_{uid}'
            candidate = base
            n = 2
            while candidate in used:
                candidate = f'{base}_{n}'
                n += 1
            collisions.append(
                f'user {uid} ({user["username"]}): "{preferred}" taken -> "{candidate}"'
            )
            preferred = candidate
        used.add(preferred)
        assigned[uid] = preferred
    return assigned, collisions


def copy_subfolders(template_dir: Path, user_dir: Path, dry_run: bool = False) -> None:
    for sub in TEMPLATE_SUBDIRS:
        dest = user_dir / sub
        if not dest.exists() and not dry_run:
            dest.mkdir(parents=True)


def sync_uploads(user_dir: Path, uploads_root: Path, teacher_id: int | None,
                 dry_run: bool = False) -> int:
    """Copy the user's uploaded files into their ``uploads`` subfolder."""
    if teacher_id is None or not uploads_root.is_dir():
        return 0
    source = uploads_root / f'teacher_{teacher_id}'
    if not source.is_dir():
        return 0
    copied = 0
    for item in sorted(source.iterdir()):
        if not item.is_file():
            continue
        dest = user_dir / 'uploads' / item.name
        if dest.exists():
            continue
        if dry_run:
            copied += 1
            continue
        shutil.copy2(item, dest)
        copied += 1
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Create one private folder per user from the shared template.',
    )
    parser.add_argument('--db', type=Path, default=None, help='SQLite database path')
    parser.add_argument('--private-faculty', type=Path, default=None,
                        help='Target folder (default: private/faculty)')
    parser.add_argument('--uploads', type=Path, default=None,
                        help='Uploads root to sync from (default: app uploads)')
    parser.add_argument('--role', action='append', default=None,
                        help='Only process this role (repeatable)')
    parser.add_argument('--sync-uploads', dest='sync_uploads', action='store_true',
                        default=True, help='Copy existing uploads into user folders (default)')
    parser.add_argument('--no-sync-uploads', dest='sync_uploads', action='store_false',
                        help='Do not copy existing uploads')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be created without writing anything')
    args = parser.parse_args()

    db_path = args.db or default_db()
    target = args.private_faculty or default_private_faculty()
    uploads_root = args.uploads or default_uploads()

    if not db_path.exists():
        print(f'[Error] database not found: {db_path}')
        return 1

    if not args.dry_run:
        target.mkdir(parents=True, exist_ok=True)
    template_dir = ensure_template(target, dry_run=args.dry_run)

    users, teacher_by_user = load_users(db_path, args.role or [])
    if not users:
        print(f'[Info] no users found in {db_path} (role filter: {args.role})')
        return 0
    names, collisions = resolve_folder_names(users, teacher_by_user)

    created = 0
    skipped = 0
    synced_total = 0
    report: list[str] = []

    print(f'Template : {template_dir}')
    print(f'Target   : {target}')
    print(f'Database : {db_path}')
    print(f'Users    : {len(users)}')
    if args.dry_run:
        print('Mode     : DRY RUN (nothing is written)')
    print('-' * 60)

    for user in users:
        uid = user['id']
        folder = names[uid]
        teacher_id = teacher_by_user.get(uid)
        user_dir = target / folder
        existed = user_dir.exists()
        if not existed:
            if not args.dry_run:
                user_dir.mkdir(parents=True)
            created += 1
        else:
            skipped += 1
        copy_subfolders(template_dir, user_dir, dry_run=args.dry_run)
        synced = sync_uploads(user_dir, uploads_root, teacher_id,
                              dry_run=args.dry_run) if args.sync_uploads else 0
        synced_total += synced
        status = 'exists' if existed else 'created'
        sync_note = f'  [+{synced} uploads]' if synced else ''
        print(f'  {folder:<18} user {uid:<5} role={user["role"]:<24} {status}{sync_note}')
        report.append(f'{folder}\tuser_id={uid}\tteacher_id={teacher_id}\trole={user["role"]}\tusername={user["username"]}')

    print('-' * 60)
    print(f'Created: {created}   Skipped (already exist): {skipped}   Uploads copied: {synced_total}')
    for line in collisions:
        print(f'[warn] {line}')
    if args.dry_run:
        return 0

    report_path = target / '_setup_report.txt'
    with open(report_path, 'w', encoding='utf-8') as fh:
        fh.write('# Per-user folder report\n')
        fh.write(f'# Users: {len(users)}  Created: {created}  Skipped: {skipped}  Uploads copied: {synced_total}\n')
        fh.write('# Columns: folder  user_id  teacher_id  role  username\n')
        fh.write('\n'.join(report))
        fh.write('\n')
    print(f'Report   : {report_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
