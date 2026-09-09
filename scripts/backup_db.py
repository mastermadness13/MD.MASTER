#!/usr/bin/env python3
"""Timestamped SQLite backup — callable by cron or scheduled task.

Creates a hot backup of the live database using SQLite's backup API
(non-blocking, consistent snapshot even during writes).

Usage:
    python scripts/backup_db.py
    python scripts/backup_db.py --backup-dir D:/backups/ropey

Cron example (every 6 hours):
    0 */6 * * * cd /path/to/project && python scripts/backup_db.py

The backup is written to ``database/backups/data-YYYYMMDD-HHMMSS.db``.
Older backups beyond KEEP_MAX are automatically pruned.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import Config

BACKUP_DIR = os.path.join(PROJECT_ROOT, 'database', 'backups')
KEEP_MAX = 10  # Max backups to keep before pruning oldest


def backup_database(backup_dir: str = BACKUP_DIR, keep_max: int = KEEP_MAX) -> str:
    """Create a timestamped backup. Returns the backup file path."""
    db_path = Config.DATABASE
    if not os.path.exists(db_path):
        print(f'ERROR: Database not found at {db_path}')
        sys.exit(1)

    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = os.path.join(backup_dir, f'data-{timestamp}.db')

    # Use SQLite's online backup API for a consistent snapshot
    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(backup_path)
    try:
        source.backup(dest)
        print(f'Backup created: {backup_path}')
    finally:
        dest.close()
        source.close()

    # Prune old backups
    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.endswith('.db')],
        key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)),
    )
    while len(backups) > keep_max:
        oldest = backups.pop(0)
        old_path = os.path.join(backup_dir, oldest)
        os.remove(old_path)
        print(f'Pruned old backup: {oldest}')

    return backup_path


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Backup the Ropey database')
    parser.add_argument('--backup-dir', default=BACKUP_DIR,
                        help='Directory to write backups to')
    parser.add_argument('--keep-max', type=int, default=KEEP_MAX,
                        help='Max backups to keep (oldest pruned)')
    args = parser.parse_args()
    backup_database(args.backup_dir, args.keep_max)
