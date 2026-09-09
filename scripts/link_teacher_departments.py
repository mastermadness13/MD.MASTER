"""Link teachers to their departments from the public source data.

One-time (safe, idempotent) fix that populates ``teachers.department_id`` from
``preview/public/data/teachers.json`` using the documented public→newRopey
department id mapping.  Only NULL department assignments are touched; existing
assignments are never overwritten.

Usage (from ``newRopey/newRopey``):
    python scripts/link_teacher_departments.py     # dry-run report
    python scripts/link_teacher_departments.py --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from utils.text import normalize_arabic_name as _norm

SCRIPT_DIR = Path(__file__).resolve().parent          # .../newRopey/newRopey/scripts
APP_DIR = SCRIPT_DIR.parent                            # .../newRopey/newRopey
ROOT = APP_DIR.parent.parent                           # workspace root
PUBLIC_DATA_DIR = ROOT / "preview" / "public" / "data"
DB_PATH = APP_DIR / "database" / "data.db"
BACKUP_DIR = APP_DIR / "database" / "backups"

# Documented department id mapping: public id -> newRopey id
PUBLIC_DEPT_MAP = {1: 4, 2: 38, 3: 1, 4: 39, 5: 40, 6: 41, 9: 43, 10: 44}

# Manual overrides for source/db name mismatches: teacher_id -> newRopey dept id.
# «أ . حافض نانيس» (source, dept 4=المدني) appears in the db as «أ . حافظ نانيس».
TEACHER_MANUAL_OVERRIDES = {97: 39}



def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="Link teachers to departments (idempotent).")
    parser.add_argument("--apply", action="store_true",
                        help="actually write (creates a backup first). Default is dry-run.")
    args = parser.parse_args()

    with open(PUBLIC_DATA_DIR / "teachers.json", encoding="utf-8") as f:
        public_teachers = json.load(f)["teachers"]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    dept_names = {r["id"]: r["name"]
                  for r in conn.execute("SELECT id, name FROM departments").fetchall()}
    db_rows = conn.execute(
        "SELECT id, name, department_id, deleted_at FROM teachers").fetchall()
    by_norm: dict[str, sqlite3.Row] = {}
    for r in db_rows:
        by_norm.setdefault(_norm(r["name"]), r)

    planned: list[tuple[int, str, int]] = []
    skipped: list[str] = []
    conflicts: list[str] = []
    unmatched: list[str] = []

    def _assign(tid: int, name: str, tgt: int, cur) -> None:
        if cur == tgt:
            skipped.append(f"{name} (already dept {tgt})")
        elif cur is None:
            planned.append((tid, name, tgt))
        else:
            conflicts.append(f"{name} (db dept {cur}, source {tgt})")

    for t in public_teachers:
        name = t.get("name") or ""
        if not t.get("departmentId"):
            continue
        tgt = PUBLIC_DEPT_MAP.get(t["departmentId"])
        if tgt is None:
            unmatched.append(f"{name} (public dept {t['departmentId']} has no map)")
            continue
        hit = by_norm.get(_norm(name))
        if hit is None:
            unmatched.append(name)
            continue
        if hit["deleted_at"] is not None:
            unmatched.append(f"{name} (archived)")
            continue
        _assign(hit["id"], name, tgt, hit["department_id"])

    for tid, tgt in TEACHER_MANUAL_OVERRIDES.items():
        r = conn.execute("SELECT id, name, department_id, deleted_at FROM teachers WHERE id = ?",
                         (tid,)).fetchone()
        if r is None:
            unmatched.append(f"override teacher id {tid} not found")
            continue
        if r["deleted_at"] is not None:
            unmatched.append(f"{r['name']} (archived)")
            continue
        _assign(tid, r["name"], tgt, r["department_id"])

    print(f"db            : {DB_PATH}")
    print(f"mode          : {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"to assign     : {len(planned)}")
    print(f"already done  : {len(skipped)}")
    print(f"conflicts     : {len(conflicts)}")
    print(f"unmatched     : {len(unmatched)}")

    for tid, name, tgt in planned:
        print(f"  assign {tid}  {name}  ->  {dept_names.get(tgt, tgt)}")

    if args.apply and planned:
        BACKUP_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = BACKUP_DIR / f"data.db-link-{stamp}.bak"
        shutil.copy2(DB_PATH, backup)
        print(f"[backup] {backup}")

    if args.apply:
        for tid, name, tgt in planned:
            conn.execute("UPDATE teachers SET department_id = ? WHERE id = ?", (tgt, tid))
            conn.execute(
                "INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) "
                "VALUES (?, ?)", (tid, tgt))
        conn.commit()
    conn.close()

    if conflicts:
        print("\n--- conflicts (skipped, never overwritten) ---")
        for c in conflicts:
            print("  ", c)
    if unmatched:
        print("\n--- unmatched ---")
        for u in unmatched:
            print("  ", u)


if __name__ == "__main__":
    main()
