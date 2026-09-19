"""Check and create all missing faculty performance tables."""
import sys, os, sqlite3
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

db = sqlite3.connect('database/data.db')
db.row_factory = sqlite3.Row
db.execute('PRAGMA foreign_keys = ON')

tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

checks = [
    'faculty_workload_rules', 'faculty_research_activities',
    'faculty_admin_assignments', 'faculty_leaves',
    'research_activity_types', 'admin_assignment_types',
    'academic_ranks',
]
for t in checks:
    print(f'  {t}: {"EXISTS" if t in tables else "MISSING"}')

if 'faculty_research_activities' not in tables:
    print("Creating faculty_research_activities...")
    db.execute("""CREATE TABLE faculty_research_activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
        academic_year TEXT NOT NULL,
        semester INTEGER NOT NULL,
        activity_type TEXT NOT NULL,
        hours INTEGER NOT NULL DEFAULT 0,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMP
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_fra_teacher ON faculty_research_activities(teacher_id)")

if 'faculty_admin_assignments' not in tables:
    print("Creating faculty_admin_assignments...")
    db.execute("""CREATE TABLE faculty_admin_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
        task_name TEXT NOT NULL,
        auto_hours INTEGER,
        manual_hours INTEGER DEFAULT 0,
        start_date TEXT NOT NULL,
        end_date TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMP
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_faa_teacher ON faculty_admin_assignments(teacher_id)")

if 'faculty_leaves' not in tables:
    print("Creating faculty_leaves...")
    db.execute("""CREATE TABLE faculty_leaves (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
        leave_type TEXT NOT NULL,
        decision_number TEXT,
        decision_authority TEXT,
        decision_date TEXT,
        start_date TEXT NOT NULL,
        end_date TEXT,
        hours INTEGER NOT NULL DEFAULT 0,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMP
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_fl_teacher ON faculty_leaves(teacher_id)")

if 'faculty_workload_rules' not in tables:
    print("Creating faculty_workload_rules...")
    db.execute("""CREATE TABLE faculty_workload_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rank_id INTEGER NOT NULL REFERENCES academic_ranks(id),
        category TEXT NOT NULL,
        min_hours INTEGER NOT NULL DEFAULT 0,
        max_hours INTEGER NOT NULL DEFAULT 0,
        academic_year TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMP
    )""")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_fwlr_unique ON faculty_workload_rules(rank_id, category, academic_year)")
    # Seed default rules
    rank_rows = db.execute('SELECT id, name_ar FROM academic_ranks').fetchall()
    categories = [('basic', 4, 10), ('research', 4, 10), ('additional', 1, 6)]
    for rank_row in rank_rows:
        rank_id = rank_row[0]
        for cat, min_h, max_h in categories:
            db.execute(
                'INSERT INTO faculty_workload_rules (rank_id, category, min_hours, max_hours, academic_year) VALUES (?, ?, ?, ?, ?)',
                (rank_id, cat, min_h, max_h, '2025-2026'),
            )
    print("  Created + seeded.")

db.commit()
db.close()
print("Done.")
