"""Read-only diagnostic script for teacher identity duplication.

Opens the database in read-only mode and produces a report of potential
duplicate teacher records.  This script NEVER writes, updates, deletes,
or creates any database objects.

Usage (from project root):
    python scripts/diagnose_teacher_duplicates.py
    python scripts/diagnose_teacher_duplicates.py --db path/to/database.db
    python scripts/diagnose_teacher_duplicates.py --json   # machine-readable output

Exit codes:
    0  success (report printed)
    1  database not found or unreadable
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# Ensure project root is on sys.path for imports like utils.text
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR = SCRIPT_DIR.parent
DEFAULT_DB = APP_DIR / "database" / "newRopey.db"

# ── FK tables referencing teachers(id) ──────────────────────────────────────

FK_TABLES = [
    ("timetable", "teacher_id"),
    ("faculty_attendance", "teacher_id"),
    ("teacher_taught_courses", "teacher_id"),
    ("teacher_departments", "teacher_id"),
    ("teacher_course_files", "teacher_id"),
    ("syllabus_archive", "teacher_id"),
    ("course_files", "teacher_id"),
    ("course_content_submissions", "teacher_id"),
    ("teacher_messages", "teacher_id"),
    ("teacher_documents", "teacher_id"),
    ("teacher_materials", "teacher_id"),
    ("teacher_requests", "teacher_id"),
    ("classroom_change_requests", "teacher_id"),
    ("faculty_research_activities", "teacher_id"),
    ("faculty_admin_assignments", "teacher_id"),
    ("faculty_leaves", "teacher_id"),
]


def _connect_readonly(db_path: str):
    """Open a SQLite connection in read-only mode."""
    import sqlite3
    uri = f"file:{db_path}?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.OperationalError:
        # Fallback for systems that don't support URI mode
        return sqlite3.connect(db_path, timeout=5)


def _count_fk_refs(conn, teacher_id: int) -> dict[str, int]:
    """Count foreign-key references to a teacher across all FK tables."""
    counts = {}
    for table, col in FK_TABLES:
        try:
            row = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {col} = ?",
                (teacher_id,),
            ).fetchone()
            counts[table] = row[0] if row else 0
        except Exception:
            counts[table] = -1  # table may not exist
    return counts


def _load_teachers(conn) -> list[dict]:
    """Load all teacher records with basic metadata."""
    rows = conn.execute(
        "SELECT id, name, email, academic_number, user_id, "
        "department_id, created_at FROM teachers "
        "WHERE deleted_at IS NULL ORDER BY id"
    ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"] or "",
            "email": r["email"] or "",
            "academic_number": r["academic_number"] or "",
            "user_id": r["user_id"],
            "department_id": r["department_id"],
            "created_at": r["created_at"] or "",
        }
        for r in rows
    ]


def _build_groups(teachers: list[dict]) -> dict[str, list[dict]]:
    """Group teachers by duplicate-detection criteria.

    Returns a dict mapping group_key -> list of teacher dicts.
    Groups are formed by (in priority order):
      1. academic_number (non-empty)  → DEFINITE DUPLICATE
      2. user_id (non-null)           → DEFINITE DUPLICATE
      3. email (non-empty)            → STRONG CANDIDATE
      4. normalized name              → REVIEW REQUIRED
    """
    from utils.text import normalize_academic_number, normalize_arabic_name

    # Phase 1: group by academic_number
    an_groups: dict[str, list[dict]] = defaultdict(list)
    for t in teachers:
        an = normalize_academic_number(t["academic_number"])
        if an:
            an_groups[an].append(t)

    # Phase 2: group remaining by user_id
    assigned_ids = set()
    uid_groups: dict[int, list[dict]] = defaultdict(list)
    for group in an_groups.values():
        for t in group:
            assigned_ids.add(t["id"])
    for t in teachers:
        if t["id"] not in assigned_ids and t["user_id"] is not None:
            uid_groups[t["user_id"]].append(t)
    for group in uid_groups.values():
        for t in group:
            assigned_ids.add(t["id"])

    # Phase 3: group remaining by email
    email_groups: dict[str, list[dict]] = defaultdict(list)
    for t in teachers:
        if t["id"] not in assigned_ids and t["email"]:
            email_groups[t["email"].lower()].append(t)
    for group in email_groups.values():
        for t in group:
            assigned_ids.add(t["id"])

    # Phase 4: group remaining by normalized name
    name_groups: dict[str, list[dict]] = defaultdict(list)
    for t in teachers:
        if t["id"] not in assigned_ids:
            norm = normalize_arabic_name(t["name"])
            if norm:
                name_groups[norm].append(t)

    # Merge all groups, classifying each
    result = {}
    for key, group in an_groups.items():
        if len(group) > 1:
            result[f"academic_number:{key}"] = {
                "classification": "DEFINITE_DUPLICATE",
                "matched_by": "academic_number",
                "members": group,
            }
    for key, group in uid_groups.items():
        if len(group) > 1:
            result[f"user_id:{key}"] = {
                "classification": "DEFINITE_DUPLICATE",
                "matched_by": "user_id",
                "members": group,
            }
    for key, group in email_groups.items():
        if len(group) > 1:
            result[f"email:{key}"] = {
                "classification": "STRONG_CANDIDATE",
                "matched_by": "email",
                "members": group,
            }
    for key, group in name_groups.items():
        if len(group) > 1:
            result[f"name:{key}"] = {
                "classification": "REVIEW_REQUIRED",
                "matched_by": "normalized_name",
                "members": group,
            }
    return result


def _select_canonical(members: list[dict]) -> dict:
    """Select the canonical teacher from a duplicate group.

    Priority: has user_id > most fields populated > lowest id.
    """
    def score(t):
        field_count = sum(1 for v in [
            t["email"], t["academic_number"],
            t["department_id"],
        ] if v)
        has_user = 1 if t["user_id"] else 0
        return (has_user, field_count, -t["id"])
    return max(members, key=score)


def _format_group(group_key: str, group: dict, conn) -> str:
    """Format a single duplicate group for display."""
    lines = []
    cls = group["classification"]
    matched = group["matched_by"]
    members = group["members"]
    canonical = _select_canonical(members)

    border = "=" * 60
    lines.append(f"\n{border}")
    lines.append(f"GROUP: {group_key}")
    lines.append(f"Classification: {cls}")
    lines.append(f"Matched by: {matched}")
    lines.append(f"Members: {len(members)}")
    lines.append(border)

    for t in sorted(members, key=lambda x: x["id"]):
        is_canonical = "  *** CANONICAL ***" if t["id"] == canonical["id"] else ""
        lines.append(f"\n  ID {t['id']}{is_canonical}")
        lines.append(f"    name:             {t['name']!r}")
        lines.append(f"    academic_number:  {t['academic_number'] or '(none)'}")
        lines.append(f"    email:            {t['email'] or '(none)'}")
        lines.append(f"    user_id:          {t['user_id'] or '(none)'}")
        lines.append(f"    department_id:    {t['department_id'] or '(none)'}")
        lines.append(f"    created_at:       {t['created_at'] or '(unknown)'}")

        fk = _count_fk_refs(conn, t["id"])
        total_fk = sum(v for v in fk.values() if v > 0)
        lines.append(f"    total_fk_refs:    {total_fk}")
        for tbl, cnt in fk.items():
            if cnt > 0:
                lines.append(f"      {tbl}: {cnt}")

    # Evidence summary
    lines.append(f"\n  Evidence:")
    lines.append(f"    - Same normalized name:  YES")
    if matched == "academic_number":
        lines.append(f"    - Same academic_number:  YES (definite)")
    else:
        an_vals = {t["academic_number"] for t in members}
        lines.append(f"    - Same academic_number:  N/A ({an_vals})")
    if matched == "user_id":
        lines.append(f"    - Same user_id:          YES (definite)")
    else:
        uid_vals = {t["user_id"] for t in members}
        lines.append(f"    - Same user_id:          {uid_vals}")
    if matched == "email":
        lines.append(f"    - Same email:            YES")
    else:
        lines.append(f"    - Same email:            N/A")

    id_vals = sorted(t["id"] for t in members)
    if len(id_vals) > 1:
        diffs = [id_vals[i+1] - id_vals[i] for i in range(len(id_vals)-1)]
        if len(set(diffs)) == 1 and diffs[0] > 0:
            lines.append(f"    - ID pattern:            +{diffs[0]} increment (consistent with repeated seeding)")

    lines.append(f"\n  Suggested canonical: ID {canonical['id']}")
    if cls == "DEFINITE_DUPLICATE":
        lines.append(f"  Suggested action:   AUTO-MERGE (stable ID match)")
    else:
        lines.append(f"  Suggested action:   MERGE after confirmation")
    lines.append(border)
    return "\n".join(lines)


def run_diagnostic(db_path: str, as_json: bool = False) -> int:
    """Run the diagnostic and print the report. Returns exit code."""
    import os
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = _connect_readonly(db_path)
    conn.row_factory = sqlite3.Row

    try:
        teachers = _load_teachers(conn)
    except Exception as e:
        print(f"ERROR: Cannot read teachers table: {e}", file=sys.stderr)
        conn.close()
        return 1

    if not teachers:
        print("No teachers found in database.")
        conn.close()
        return 0

    groups = _build_groups(teachers)

    if as_json:
        output = _build_json_output(teachers, groups, conn)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        _print_text_report(teachers, groups, conn)

    conn.close()
    return 0


def _build_json_output(teachers: list[dict], groups: dict, conn) -> dict:
    """Build machine-readable JSON output."""
    group_list = []
    for key, group in groups.items():
        canonical = _select_canonical(group["members"])
        members_detail = []
        for t in group["members"]:
            fk = _count_fk_refs(conn, t["id"])
            total_fk = sum(v for v in fk.values() if v > 0)
            members_detail.append({
                "id": t["id"],
                "name": t["name"],
                "academic_number": t["academic_number"] or None,
                "email": t["email"] or None,
                "user_id": t["user_id"],
                "department_id": t["department_id"],
                "created_at": t["created_at"],
                "total_fk_refs": total_fk,
                "fk_breakdown": {k: v for k, v in fk.items() if v > 0},
            })
        group_list.append({
            "group_key": key,
            "classification": group["classification"],
            "matched_by": group["matched_by"],
            "canonical_teacher_id": canonical["id"],
            "member_count": len(group["members"]),
            "members": members_detail,
        })

    return {
        "total_teachers": len(teachers),
        "duplicate_groups": len(group_list),
        "definite_duplicates": sum(1 for g in group_list if g["classification"] == "DEFINITE_DUPLICATE"),
        "strong_candidates": sum(1 for g in group_list if g["classification"] == "STRONG_CANDIDATE"),
        "review_required": sum(1 for g in group_list if g["classification"] == "REVIEW_REQUIRED"),
        "groups": group_list,
    }


def _print_text_report(teachers: list[dict], groups: dict, conn) -> None:
    """Print the human-readable text report."""
    print("=" * 60)
    print("TEACHER DUPLICATION DIAGNOSTIC REPORT")
    print("=" * 60)
    print(f"\nTotal teachers: {len(teachers)}")
    print(f"Duplicate groups found: {len(groups)}")

    definite = sum(1 for g in groups.values() if g["classification"] == "DEFINITE_DUPLICATE")
    strong = sum(1 for g in groups.values() if g["classification"] == "STRONG_CANDIDATE")
    review = sum(1 for g in groups.values() if g["classification"] == "REVIEW_REQUIRED")
    print(f"  DEFINITE DUPLICATE:  {definite}")
    print(f"  STRONG CANDIDATE:    {strong}")
    print(f"  REVIEW REQUIRED:     {review}")

    unique_count = len(teachers) - sum(
        len(g["members"]) - 1 for g in groups.values()
    )
    print(f"  Unique teachers:     {unique_count}")

    for key in sorted(groups.keys()):
        print(_format_group(key, groups[key], conn))

    print("\n" + "=" * 60)
    print("END OF REPORT")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Review each group above")
    print("  2. For REVIEW_REQUIRED groups, confirm whether members are the same person")
    print("  3. Create scripts/approved_teacher_merges.json with approved merges")
    print("  4. Run the deduplication migration")


def main():
    parser = argparse.ArgumentParser(
        description="Read-only diagnostic for teacher identity duplication."
    )
    parser.add_argument(
        "--db", default=str(DEFAULT_DB),
        help=f"Path to the database file (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output machine-readable JSON instead of text",
    )
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    exit_code = run_diagnostic(args.db, as_json=args.json)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
