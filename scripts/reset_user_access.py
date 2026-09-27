#!/usr/bin/env python3
"""Re-issue login access for existing users (recovery codes or new passwords).

Passwords are stored as one-way ``scrypt`` hashes, so the current password of
a user can never be read back. This tool issues *new* access instead, using
the same mechanism the Teachers page already uses:

``code`` (default)
    A 6-digit temporary access code via
    :func:`services.temp_access_code.issue_recovery_code` — valid
    ``CODE_VALID_MINUTES`` (60) with ``MAX_ATTEMPTS`` (5) tries. It does not
    touch the real password, and the next successful login is forced to set
    a new one (``force_password_change``).

``password``
    Overwrites the stored hash via ``user_service.change_user_password``,
    which also rotates ``session_version`` and clears ``force_password_change``.

The database is backed up (SQLite backup API) before anything is written,
unless ``--no-backup`` is passed.

Usage:
    python scripts/reset_user_access.py --list
    python scripts/reset_user_access.py --user admin
    python scripts/reset_user_access.py --all --yes
    python scripts/reset_user_access.py --user admin --mode password --password 'S3cure!Pass'
    python scripts/reset_user_access.py --all --mode password --yes
    python scripts/reset_user_access.py --user admin --db /tmp/other.db --yes

The database defaults to ``Config.DATABASE`` (i.e. the ``DATABASE`` value in
``.env``), so the same command works on the server after ``git pull``.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sqlite3
import string
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import Config
from database.connection import connect
from database.history import add_history
from services import user_service
from services.temp_access_code import (
    CODE_VALID_MINUTES,
    MAX_ATTEMPTS,
    issue_recovery_code,
)
from security import validate_password

BACKUP_DIR = os.path.join(PROJECT_ROOT, 'database', 'backups')
USER_COLUMNS = (
    'id, username, role, label, is_active, force_password_change, '
    'password_changed_at, recovery_code_expires_at'
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backup(db_path: str) -> str:
    """Hot SQLite backup of *db_path* into ``database/backups``."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    target = os.path.join(BACKUP_DIR, f'data-before-access-{stamp}.db')
    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(target)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    return target


def _generate_password() -> str:
    """A random password that satisfies :func:`security.validate_password`."""
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    symbols = '!@#$%^&*-_'
    pool = lower + upper + digits + symbols
    chars = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    chars += [secrets.choice(pool) for _ in range(8)]
    secrets.SystemRandom().shuffle(chars)
    return ''.join(chars)


def _code_state(user) -> str:
    expires = user['recovery_code_expires_at']
    if not expires:
        return '-'
    try:
        moment = datetime.fromisoformat(expires)
    except ValueError:
        return '؟'
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    minutes = int((moment - _now()).total_seconds() // 60)
    if minutes <= 0:
        return 'منتهي'
    return f'فعال (~{minutes} د)'


def _list_users(db) -> None:
    rows = db.execute(
        f'SELECT {USER_COLUMNS} FROM users ORDER BY role, username'
    ).fetchall()
    print(f'{"USERNAME":<16}{"ROLE":<22}{"ACTIVE":<7}{"FORCE":<7}'
          f'{"CHANGED_AT":<21}CODE')
    for row in rows:
        print(
            f'{row["username"]:<16}{row["role"]:<22}'
            f'{"نعم" if row["is_active"] else "لا":<7}'
            f'{"نعم" if row["force_password_change"] else "لا":<7}'
            f'{(row["password_changed_at"] or "-"):<21}{_code_state(row)}'
        )
    print(f'\nالمجموع: {len(rows)} حساب')


def _resolve_targets(db, args) -> list:
    if args.all:
        sql = f'SELECT {USER_COLUMNS} FROM users'
        if not args.include_inactive:
            sql += ' WHERE is_active = 1'
        return db.execute(sql + ' ORDER BY role, username').fetchall()

    wanted = {name.strip().lower() for name in args.user}
    rows = db.execute(f'SELECT {USER_COLUMNS} FROM users').fetchall()
    found = [row for row in rows if row['username'].lower() in wanted]
    missing = wanted - {row['username'].lower() for row in found}
    for name in sorted(missing):
        print(f'[تحذير] لا يوجد مستخدم بهذا الاسم: {name}')
    return found


def _resolve_issuer(db, name: str) -> tuple:
    """Resolve the account recorded as the issuer of the codes.

    ``users.recovery_code_issued_by`` is a foreign key to ``users(id)``, so a
    placeholder like ``0`` is rejected by SQLite — a real row is required.
    """
    if name and name != '0':
        row = db.execute(
            'SELECT id, username FROM users WHERE username = ? COLLATE NOCASE',
            (name,),
        ).fetchone()
        if not row:
            sys.exit(f'لا يوجد مستخدم مُصدِر بهذا الاسم: {name}')
        return row['id'], row['username']

    row = db.execute(
        "SELECT id, username FROM users ORDER BY "
        "CASE WHEN username = 'admin' COLLATE NOCASE THEN 0 "
        "WHEN role = 'head_of_department' THEN 1 ELSE 2 END, id LIMIT 1"
    ).fetchone()
    if not row:
        sys.exit('لا يوجد أي مستخدم يمكن تسجيله كمُصدِر')
    return row['id'], row['username']


def _confirm(prompt: str) -> bool:
    try:
        return input(f'{prompt} [اكتب نعم للمتابعة]: ').strip() in ('نعم', 'yes', 'y')
    except EOFError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description='إصدار رموز دخول مؤقتة أو كلمات مرور جديدة لمستخدمين موجودين',
    )
    parser.add_argument('--list', action='store_true',
                        help='عرض كل الحسابات وحالة الرمز الحالي فقط')
    parser.add_argument('--user', action='append', default=[],
                        help='اسم مستخدم واحد (يمكن تكراره)')
    parser.add_argument('--all', action='store_true',
                        help='كل الحسابات النشطة')
    parser.add_argument('--include-inactive', action='store_true',
                        help='عند --all شمل الحسابات المعطّلة أيضاً')
    parser.add_argument('--mode', choices=('code', 'password'), default='code',
                        help='code = رمز مؤقت 6 أرقام (الافتراضي)، '
                             'password = كلمة مرور جديدة دائمة')
    parser.add_argument('--password', help='كلمة المرور في وضع password '
                                           '(وإلا تُولَّد عشوائية لكل مستخدم)')
    parser.add_argument('--issued-by', default='0',
                        help='اسم مستخدم مُصدِر الرمز للتدقيق (0 = النظام)')
    parser.add_argument('--db', default=None,
                        help='مسار قاعدة البيانات (الافتراضي Config.DATABASE)')
    parser.add_argument('--no-backup', action='store_true',
                        help='تخطّي النسخ الاحتياطي قبل الكتابة')
    parser.add_argument('--yes', action='store_true',
                        help='نفّذ دون طلب تأكيد')
    args = parser.parse_args()

    db_path = args.db or Config.DATABASE
    if not os.path.exists(db_path):
        sys.exit(f'قاعدة البيانات غير موجودة: {db_path}')

    db = connect(db_path)
    try:
        if args.list:
            _list_users(db)
            return

        if not args.all and not args.user:
            parser.error('حدّد --list أو --user أو --all')

        if args.password and args.mode != 'password':
            parser.error('--password يعمل مع --mode password فقط')
        if args.password and len(args.user) > 1:
            parser.error('--password مع مستخدم واحد فقط')
        if args.password:
            error = validate_password(args.password)
            if error:
                sys.exit(f'كلمة المرور ضعيفة: {error}')

        targets = _resolve_targets(db, args)
        if not targets:
            sys.exit('لا يوجد مستخدمون مطابقون')

        issuer_id, issuer_name = _resolve_issuer(db, args.issued_by)

        if not args.yes and not _confirm(f'سيتم تعديل {len(targets)} حساب في {db_path}'):
            sys.exit('أُلغي')

        if not args.no_backup:
            print(f'نسخة احتياطية: {_backup(db_path)}')

        issued = []
        for row in targets:
            username = row['username']
            if args.mode == 'code':
                secret = issue_recovery_code(
                    db, user_id=row['id'], issued_by=issuer_id,
                )
                action, detail = 'issue_recovery_code', 'رمز دخول مؤقت جديد'
            else:
                secret = args.password or _generate_password()
                user_service.change_user_password(db, row['id'], secret)
                action, detail = 'reset_password', 'كلمة مرور جديدة'

            add_history(
                db, action, 'user', row['id'], issuer_id, issuer_name,
                f'{detail}: {username}',
            )
            issued.append((username, row['role'], row['label'] or '', secret))

        db.commit()
    finally:
        db.close()

    title = (
        f'رموز مؤقتة (صالحة {CODE_VALID_MINUTES} د، {MAX_ATTEMPTS} محاولات، '
        f'وجلسة الدخول التالية تفرض كلمة مرور جديدة)'
        if args.mode == 'code'
        else 'كلمات مرور جديدة (تعمل حتى إبطالها، وتُبطل الجلسات الحالية)'
    )
    print(f'\n=== {title} ===')
    for username, role, label, secret in issued:
        print(f'  {username:<16}{role:<22}{label:<34}{secret}')
    print(f'\nالمُصدِر المسجّل: {issuer_name}')
    print('سلّم هذه القيم يدوياً — لن تظهر مرة أخرى.')


if __name__ == '__main__':
    main()
