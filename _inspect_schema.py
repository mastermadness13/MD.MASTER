import sqlite3

c = sqlite3.connect("database/data.db")
for name in ("teacher_taught_courses", "timetable"):
    row = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    print("=" * 70)
    print(row[0] if row else f"{name}: MISSING")
print("=" * 70)

print("\n--- indexes ---")
for name in ("teacher_taught_courses", "timetable"):
    for r in c.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?", (name,)
    ):
        print(name, "->", r)

print("\n--- duplicate (teacher,course) pairs in ledger ---")
for r in c.execute(
    """
    SELECT teacher_id, course_id, COUNT(*) n
    FROM teacher_taught_courses
    GROUP BY teacher_id, course_id
    HAVING n > 1
    ORDER BY n DESC LIMIT 10
    """
):
    print(r)

print("\n--- teacher 82 hours as currently computed ---")
print(
    "ledger SUM(hours) =",
    c.execute(
        "SELECT SUM(COALESCE(hours,0)) FROM teacher_taught_courses WHERE teacher_id=82"
    ).fetchone()[0],
)
print(
    "timetable-derived =",
    c.execute(
        """
        SELECT COALESCE(SUM(hours),0) FROM (
          SELECT t.teacher_id, COUNT(*) * (
            SELECT COALESCE(hours,2) FROM courses WHERE id = t.course_id
          ) AS hours
          FROM timetable t WHERE t.teacher_id=82 GROUP BY t.course_id
        )
        """
    ).fetchone()[0],
)

print("\n--- max ledger SUM(hours) across teachers ---")
for r in c.execute(
    """
    SELECT te.name, t.teacher_id, SUM(COALESCE(t.hours,0)) h, COUNT(*) rows
    FROM teacher_taught_courses t JOIN teachers te ON te.id=t.teacher_id
    GROUP BY t.teacher_id HAVING h >= 40 ORDER BY h DESC LIMIT 10
    """
):
    print(r)