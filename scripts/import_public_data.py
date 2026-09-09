"""One-time safe data import from the read-only public website into newRopey.

Source (READ-ONLY):  <root>/preview/public/data/*.json
Target:              <root>/newRopey/newRopey/database/data.db

Design (per project decisions):
  * public is never modified.
  * newRopey is the source of truth. The 201 timetable entries are NOT touched.
  * Import is idempotent: re-running it never inserts duplicates nor deletes rows.
  * Nothing is invented: missing source values are left NULL/empty.
  * Conflicts are logged and SKIPPED (never silently overwritten).
  * Obsolete teacher_departments rows (pointing to non-existent department ids) are
    deleted; legitimate teacher records are never deleted.

Usage:
    python database/import_public_data.py             # dry-run: mapping + planned actions only
    python database/import_public_data.py --apply     # creates a backup, then writes
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from utils.text import normalize_arabic_name as _norm

SCRIPT_DIR = Path(__file__).resolve().parent          # .../newRopey/newRopey/database
ROOT = SCRIPT_DIR.parent.parent.parent                # workspace root
PUBLIC_DATA_DIR = ROOT / "preview" / "public" / "data"
DB_PATH = SCRIPT_DIR / "data.db"
BACKUP_DIR = SCRIPT_DIR / "backups"

# Documented department id mapping: public id -> newRopey id
PUBLIC_DEPT_MAP = {1: 4, 2: 38, 3: 1, 4: 39, 5: 40, 6: 41, 9: 43, 10: 44}

EXAM_ACTIVE_STATUSES = ("planned", "scheduled", "published", "completed")
EXAM_STATUS_KEEP = {"published": "published", "planned": "planned",
                    "scheduled": "scheduled", "draft": "draft", "completed": "completed"}

# profile field name (public) -> column name in department_profiles
PROFILE_FIELDS = {
    "about": "about", "vision": "vision", "mission": "mission",
    "objectives": "objectives", "studyFields": "study_fields", "skills": "skills",
    "labs": "labs", "labsNote": "labs_note", "practicalTraining": "practical_training",
    "careers": "careers", "furtherStudy": "further_study", "word": "word",
    "requirements": "requirements",
}

LIST_FIELDS = {"objectives", "study_fields", "skills", "labs", "practical_training",
               "careers", "further_study", "requirements"}



def _jstr(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _load_public(name: str):
    with open(PUBLIC_DATA_DIR / name, encoding="utf-8") as fh:
        data = json.load(fh)
    key = name.split(".")[0]
    return data[key] if isinstance(data, dict) and key in data else data


class Report:
    def __init__(self):
        self.counts = defaultdict(int)
        self.rows = []

    def add(self, category: str, detail: str):
        self.counts[category] += 1
        self.rows.append((category, detail))

    def summary(self):
        order = ["Inserted", "Updated", "Skipped", "Unmatched",
                 "Duplicates detected", "Missing source information", "Conflicts"]
        return "\n".join(f"  {c}: {self.counts.get(c, 0)}" for c in order)

    def dump(self, out):
        for category, detail in self.rows:
            out.write(f"[{category}] {detail}\n")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(departments)").fetchall()}
    for col, ddl in [("icon", "TEXT DEFAULT ''"), ("accent_color", "TEXT DEFAULT ''"),
                     ("description", "TEXT")]:
        if col not in cols:
            conn.execute(f"ALTER TABLE departments ADD COLUMN {col} {ddl}")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "department_profiles" not in tables:
        conn.execute("""
            CREATE TABLE department_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department_id INTEGER NOT NULL UNIQUE REFERENCES departments(id) ON DELETE CASCADE,
                about TEXT, vision TEXT, mission TEXT, objectives TEXT, study_fields TEXT,
                skills TEXT, labs TEXT, labs_note TEXT, practical_training TEXT, careers TEXT,
                further_study TEXT, word TEXT, requirements TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


class Importer:
    def __init__(self, apply: bool):
        self.apply = apply
        self.report = Report()
        self.conn = None

    # ── loading ────────────────────────────────────────────────────────
    def _load_target_maps(self):
        db = self.conn
        self.depts = {r["id"]: dict(r) for r in db.execute(
            "SELECT id, name, hidden, type FROM departments").fetchall()}
        self.valid_dept_ids = set(self.depts)

        # courses
        self.courses = []
        for r in db.execute("SELECT id, name, code, department_id, theoretical_hours, "
                            "practical_hours, total_hours, accreditation, vocabulary, "
                            "notes, icon, year, semester FROM courses").fetchall():
            self.courses.append(dict(r))
        self.course_by_norm = defaultdict(list)
        self.course_by_code = defaultdict(list)
        for c in self.courses:
            self.course_by_norm[_norm(c["name"])].append(c["id"])
            if c["code"]:
                self.course_by_code[c["code"].strip()].append(c["id"])
        self.course_row = {c["id"]: c for c in self.courses}

        # course_departments
        self.course_depts = defaultdict(set)
        for r in db.execute("SELECT course_id, department_id FROM course_departments").fetchall():
            self.course_depts[r["course_id"]].add(r["department_id"])

        # teachers
        self.teacher_by_norm = defaultdict(list)
        self.teacher_row = {}
        for r in db.execute("SELECT id, name, department_id FROM teachers").fetchall():
            self.teacher_row[r["id"]] = dict(r)
            self.teacher_by_norm[_norm(r["name"])].append(r["id"])

        # rooms
        self.room_by_norm = defaultdict(list)
        self.room_row = {}
        for r in db.execute("SELECT id, name, department_id FROM rooms").fetchall():
            self.room_row[r["id"]] = dict(r)
            self.room_by_norm[_norm(r["name"])].append(r["id"])

        # exam_schedule existing
        self.existing_exams = [dict(r) for r in db.execute("SELECT * FROM exam_schedule").fetchall()]

    def _resolve_dept(self, public_dept_id, name) -> tuple:
        """Return (new_dept_id or None, ok)."""
        target = PUBLIC_DEPT_MAP.get(public_dept_id)
        if target is None:
            self.report.add("Unmatched", f"dept id {public_dept_id} has no mapping")
            return None, False
        if target not in self.valid_dept_ids:
            self.report.add("Conflicts", f"dept map {public_dept_id}->{target} points to missing dept")
            return None, False
        if name and _norm(self.depts[target]["name"]) != _norm(name):
            self.report.add("Conflicts",
                            f"dept name mismatch: public '{name}' (id {public_dept_id}) vs new '{self.depts[target]['name']}' (id {target})")
        return target, True

    def _find_course(self, name, code):
        """Return (course_id or None, matched_by or None)."""
        cands = self.course_by_norm.get(_norm(name), [])
        if len(cands) == 1:
            return cands[0], "name"
        if len(cands) > 1:
            if code:
                by_code = self.course_by_code.get(code.strip(), [])
                if len(by_code) == 1:
                    return by_code[0], "code"
            return None, None  # ambiguous -> handled by caller
        if code:
            by_code = self.course_by_code.get(code.strip(), [])
            if len(by_code) == 1:
                return by_code[0], "code"
            if len(by_code) > 1:
                return None, None
        return None, None

    def _find_teacher(self, name):
        cands = self.teacher_by_norm.get(_norm(name), [])
        if len(cands) == 1:
            return cands[0]
        return None

    def _find_room(self, name):
        cands = self.room_by_norm.get(_norm(name), [])
        if len(cands) == 1:
            return cands[0]
        return None

    # ── operations ─────────────────────────────────────────────────────
    def _apply_period_c(self):
        row = self.conn.execute("SELECT id, code, is_enabled FROM period_settings WHERE code='C'").fetchone()
        if not row:
            self.report.add("Missing source information", "period_settings has no row for code 'C'")
            return
        if row["is_enabled"]:
            self.report.add("Skipped", "period C already enabled")
        else:
            if self.apply:
                self.conn.execute("UPDATE period_settings SET is_enabled=1 WHERE id=?", (row["id"],))
            self.report.add("Updated", "period C enabled (A/B untouched)")

    def _apply_departments(self, public_depts):
        for d in public_depts:
            pid = d["id"]
            target, ok = self._resolve_dept(pid, d.get("name"))
            if not ok:
                continue
            target_row = self.depts[target]
            meta = {"icon": d.get("icon"), "accent_color": d.get("accentColor"),
                    "description": d.get("description")}
            profile = d.get("profile") or {}
            updates = {}
            for col, val in meta.items():
                if not val:
                    continue
                if target_row.get(col):
                    if target_row[col] != val:
                        self.report.add("Conflicts", f"dept {target} '{col}' differs (new '{target_row[col]}' vs public '{val}')")
                    continue
                updates[col] = val
            if updates:
                if self.apply:
                    self.conn.execute(
                        "UPDATE departments SET " + ", ".join(f"{c}=?" for c in updates) +
                        " WHERE id=?", (*updates.values(), target))
                self.report.add("Updated", f"dept {target} ({d['name']}) meta {', '.join(updates)}")
            else:
                self.report.add("Skipped", f"dept {target} meta already present/empty source")

            if not profile:
                self.report.add("Skipped", f"dept {target} has no profile content in source")
                continue
            payload = {}
            for pub_key, col in PROFILE_FIELDS.items():
                val = profile.get(pub_key)
                if val is None:
                    continue
                payload[col] = _jstr(val) if col in LIST_FIELDS else str(val)
            existing = self.conn.execute(
                "SELECT id FROM department_profiles WHERE department_id=?", (target,)).fetchone()
            if existing:
                if self.apply:
                    payload["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    sets = ", ".join(f"{c}=?" for c in payload)
                    self.conn.execute(f"UPDATE department_profiles SET {sets} WHERE department_id=?",
                                      (*payload.values(), target))
                self.report.add("Updated", f"dept {target} profile upserted")
            else:
                if self.apply:
                    cols = ["department_id", *payload.keys()]
                    marks = ", ".join("?" for _ in cols)
                    self.conn.execute(
                        f"INSERT INTO department_profiles ({', '.join(cols)}) VALUES ({marks})",
                        (target, *payload.values()))
                self.report.add("Inserted", f"dept {target} profile created ({len(payload)} fields)")

    def _apply_courses(self, public_courses):
        created = []
        for c in public_courses:
            name, code = c.get("name"), c.get("code") or ""
            cid, matched_by = self._find_course(name, code)
            if cid is None:
                created.append(c)
                continue
            row = self.course_row[cid]
            updates = {}
            # department linkage
            if c.get("departmentId"):
                tgt, ok = self._resolve_dept(c["departmentId"], c.get("department"))
                if ok and tgt not in self.course_depts[cid] and row.get("department_id") != tgt:
                    if self.apply:
                        self.conn.execute(
                            "INSERT OR IGNORE INTO course_departments (course_id, department_id) VALUES (?,?)",
                            (cid, tgt))
                    self.report.add("Updated", f"course {cid} linked to dept {tgt}")
            # fill empty fields from source only
            fields = [
                ("code", c.get("code") or None),
                ("theoretical_hours", c.get("theoreticalHours") if c.get("theoreticalHours") else None),
                ("practical_hours", c.get("practicalHours") if c.get("practicalHours") else None),
                ("total_hours", c.get("totalHours") if c.get("totalHours") else None),
                ("accreditation", str(c["accreditation"]) if c.get("accreditation") is not None else None),
                ("vocabulary", c.get("vocabulary") or None),
                ("notes", c.get("notes") or None),
                ("icon", c.get("icon") or None),
            ]
            for col, src_val in fields:
                if src_val is None:
                    continue
                cur = row.get(col)
                if cur is None or cur == "" or cur == 0:
                    updates[col] = src_val
                elif str(cur).strip() != str(src_val).strip():
                    self.report.add("Conflicts",
                                    f"course {cid} '{name}' field '{col}' differs (new '{cur}' vs public '{src_val}')")
            if updates:
                if self.apply:
                    self.conn.execute(
                        "UPDATE courses SET " + ", ".join(f"{c}=?" for c in updates) + " WHERE id=?",
                        (*updates.values(), cid))
                self.report.add("Updated", f"course {cid} '{name}' filled {', '.join(updates)}")
            else:
                self.report.add("Skipped", f"course {cid} '{name}' no fillable empty fields")
        return created

    def _create_courses(self, courses_to_create):
        for c in courses_to_create:
            name = c.get("name") or ""
            code = (c.get("code") or "").strip()
            if not name:
                self.report.add("Missing source information", "public course without name skipped")
                continue
            # safety re-check for duplicates inside the target
            dup = self._find_course(name, code)
            if dup[0] is not None:
                self.report.add("Duplicates detected",
                                f"course '{name}' resolves to existing id {dup[0]} on re-check; not inserted")
                continue
            dept_id = None
            if c.get("departmentId"):
                dept_id, ok = self._resolve_dept(c["departmentId"], c.get("department"))
                if not ok:
                    dept_id = None
            new_id = None
            if self.apply:
                cur = self.conn.execute(
                    "INSERT INTO courses (code, name, department, department_id, year, semester, "
                    "theoretical_hours, practical_hours, total_hours, accreditation, vocabulary, "
                    "syllabus_file, notes, icon) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (code, name, (self.depts[dept_id]["name"] if dept_id else c.get("department") or None),
                     dept_id, c.get("year") or 1, c.get("semester") or 1,
                     c.get("theoreticalHours") or 0, c.get("practicalHours") or 0,
                     c.get("totalHours") or 0,
                     str(c["accreditation"]) if c.get("accreditation") is not None else None,
                     c.get("vocabulary") or None, c.get("syllabusFile") or None,
                     c.get("notes") or None, c.get("icon") or None))
                new_id = cur.lastrowid
                if dept_id:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO course_departments (course_id, department_id) VALUES (?,?)",
                        (new_id, dept_id))
            missing = []
            if not code:
                missing.append("code")
            if not c.get("departmentId"):
                missing.append("department")
            if missing:
                self.report.add("Missing source information",
                                f"course '{name}' created without: {', '.join(missing)}")
            self.report.add("Inserted", f"course '{name}' (code={code or '-'}, dept={dept_id or '-'}, id={new_id or 'dry-run'})")

    def _apply_teachers(self, public_teachers):
        for t in public_teachers:
            name = t.get("name") or ""
            tid = self._find_teacher(name)
            if tid is None:
                self.report.add("Unmatched", f"teacher '{name}' not found in newRopey")
                continue
            row = self.teacher_row[tid]
            if not t.get("departmentId"):
                self.report.add("Missing source information",
                                f"teacher '{name}' has no department in source; left unassigned")
                continue
            tgt, ok = self._resolve_dept(t["departmentId"], t.get("department"))
            if not ok:
                continue
            if row.get("department_id") == tgt:
                self.report.add("Skipped", f"teacher '{name}' already assigned to dept {tgt}")
            elif row.get("department_id") is None:
                if self.apply:
                    self.conn.execute("UPDATE teachers SET department_id=? WHERE id=?", (tgt, tid))
                self.report.add("Updated", f"teacher '{name}' assigned to dept {tgt}")
            else:
                self.report.add("Conflicts",
                                f"teacher '{name}' assigned to dept {row['department_id']} but source says {tgt}; skipped")

    def _apply_rooms(self, public_rooms):
        for r in public_rooms:
            name = r.get("name") or ""
            rid = self._find_room(name)
            if rid is None:
                self.report.add("Unmatched", f"room '{name}' not found in newRopey")
                continue
            row = self.room_row[rid]
            if not r.get("departmentId"):
                self.report.add("Missing source information",
                                f"room '{name}' has no department in source; left unassigned")
                continue
            tgt, ok = self._resolve_dept(r["departmentId"], None)
            if not ok:
                continue
            if row.get("department_id") == tgt:
                self.report.add("Skipped", f"room '{name}' already on dept {tgt}")
            else:
                if self.apply:
                    self.conn.execute("UPDATE rooms SET department_id=? WHERE id=?", (tgt, rid))
                self.report.add("Updated",
                                f"room '{name}' department {row.get('department_id')} -> {tgt}")

    def _apply_exams(self, public_exams):
        seen_keys = set()
        for e in public_exams:
            cid, matched = self._find_course(e.get("courseName"), e.get("courseCode") or "")
            if cid is None:
                self.report.add("Unmatched", f"exam for course '{e.get('courseName')}' has no matching course")
                continue
            dept_id, ok = self._resolve_dept(e.get("departmentId"), None)
            if not ok:
                self.report.add("Unmatched", f"exam for course '{e.get('courseName')}' has no resolvable dept")
                continue
            semester = e.get("semester") or 1
            key = (cid, dept_id, semester)
            if key in seen_keys:
                self.report.add("Duplicates detected",
                                f"exam {e.get('id')} duplicates an earlier public exam for course {cid}/dept {dept_id}/sem {semester}; skipped")
                continue
            seen_keys.add(key)

            room_id = None
            if e.get("roomName"):
                room_id = self._find_room(e["roomName"])
                if room_id is None:
                    self.report.add("Unmatched", f"exam for '{e.get('courseName')}' room '{e['roomName']}' not found")

            status = EXAM_STATUS_KEEP.get(e.get("status"), "planned")
            exam_date = e.get("examDate") or ""
            start_time = e.get("startTime")
            end_time = e.get("endTime")

            existing = [x for x in self.existing_exams
                        if x["course_id"] == cid and x["department_id"] == dept_id
                        and x["semester"] == semester]
            if existing:
                x = existing[0]
                same = (str(x.get("exam_date") or "") == str(exam_date)
                        and str(x.get("start_time") or "") == str(start_time or "")
                        and str(x.get("end_time") or "") == str(end_time or "")
                        and x.get("room_id") == room_id)
                if same:
                    self.report.add("Skipped", f"exam already present for course {cid} (date {exam_date})")
                else:
                    self.report.add("Conflicts",
                                    f"exam for course {cid} dept {dept_id} exists (id {x['id']}, date {x.get('exam_date')}) "
                                    f"but source says {exam_date}; NOT overwritten")
                continue

            if self.apply:
                self.conn.execute(
                    """INSERT INTO exam_schedule
                       (course_id, department_id, exam_date, start_time, end_time, room_id,
                        semester, status, merged_at, published_at, created_by_user_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid, dept_id, exam_date, start_time, end_time, room_id,
                     semester, status, e.get("mergedAt"), e.get("publishedAt"),
                     self.created_by_user_id))
            self.report.add("Inserted",
                            f"exam for course '{e.get('courseName')}' dept {dept_id} date {exam_date} "
                            f"status {status} room {room_id or '-'}")

    def _clean_teacher_departments(self):
        rows = self.conn.execute(
            "SELECT id, teacher_id, department_id FROM teacher_departments").fetchall()
        for r in rows:
            if r["department_id"] not in self.valid_dept_ids:
                if self.apply:
                    self.conn.execute("DELETE FROM teacher_departments WHERE id=?", (r["id"],))
                self.report.add("Updated",
                                f"removed obsolete teacher_departments row id {r['id']} (dept {r['department_id']} no longer exists)")

    # ── main ───────────────────────────────────────────────────────────
    def run(self):
        public_depts = _load_public("departments.json")
        public_courses = _load_public("courses.json")
        public_teachers = _load_public("teachers.json")
        public_rooms = _load_public("rooms.json")
        public_exams = _load_public("exams.json")

        if self.apply:
            BACKUP_DIR.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = BACKUP_DIR / f"data.db-{stamp}.bak"
            shutil.copy2(DB_PATH, backup)
            print(f"[backup] {backup}")

        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        _ensure_schema(self.conn)
        self._load_target_maps()
        self.created_by_user_id = None

        self._apply_period_c()
        self._apply_departments(public_depts)
        to_create = self._apply_courses(public_courses)
        self._create_courses(to_create)
        self._apply_teachers(public_teachers)
        self._apply_rooms(public_rooms)
        self._apply_exams(public_exams)
        self._clean_teacher_departments()

        if self.apply:
            self.conn.commit()
        self.conn.close()

        print("\n=== IMPORT REPORT ===")
        print(self.report.summary())
        print("\n--- details ---")
        self.report.dump(sys.stdout)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="Import public-site data into newRopey (safe/idempotent).")
    parser.add_argument("--apply", action="store_true",
                        help="actually write (creates a backup first). Default is dry-run.")
    args = parser.parse_args()
    print(f"public data dir : {PUBLIC_DATA_DIR}")
    print(f"target db       : {DB_PATH}")
    print(f"mode            : {'APPLY' if args.apply else 'DRY-RUN'}")
    Importer(args.apply).run()


if __name__ == "__main__":
    main()
