# Database Domains (أقسام قاعدة البيانات)

The database is **one physical SQLite file** (`database/data.db`), but every table
belongs to exactly one **named domain** — the "parts" of the system. This gives
the separation you asked for without breaking the foreign-key relationships
between tables.

- Single source of truth: `database/domains.py`
- Registry persisted in the DB itself: table `schema_domains`
- Print the live mapping: `python scripts/db_domains.py`

```
database/data.db
│
├── identity       (الهوية)
├── academic       (الكلية)
├── scheduling     (الجدولة)
├── examinations   (الامتحانات)
├── communication  (التواصل)
└── auditing       (التدقيق)
```

---

## identity — الهوية

Accounts, authentication and access.

| Table | Purpose |
|-------|---------|
| `users` | System accounts (roles: research_development, faculty_affairs, head_of_department, teacher, exam) |
| `password_resets` | Password reset tokens |

## academic — االكلية 
Departments, faculty, courses and study plans.

| Table | Purpose |
|-------|---------|
| `departments` | College departments (6 academic + administrative) |
| `department_majors` | Majors per department |
| `teachers` | Faculty members (linked to `users`) |
| `teacher_departments` | Teacher ↔ department (many-to-many) |
| `qualifications` | Lookup: دبلوم / بكالوريوس / ماجستير / دكتوراه |
| `academic_ranks` | Lookup: أستاذ / أستاذ مشارك / ... |
| `classifications` | Lookup: قار / متعاون / معيد |
| `rank_rules` | Allowed qualification → rank rules |
| `courses` | Courses with codes, hours, year, semester |
| `course_departments` | Course ↔ department (many-to-many) |
| `course_prerequisites` | Course prerequisite graph |
| `course_content_submissions` | Teacher course-content submissions |
| `course_content_curriculum` | Curriculum items of a submission |
| `faculty_attendance` | Faculty attendance records |

## scheduling — الجدولة

Rooms, time periods, the weekly timetable and room-change requests.

| Table | Purpose |
|-------|---------|
| `rooms` | Rooms / labs / theaters with capacity and equipment |
| `room_types` | Lookup: قاعة / معمل / معمل حاسوب / مرسم / مدرج / آخر |
| `room_statuses` | Lookup: متاحة / مستخدمة / صيانة / مقفلة |
| `floors` | Lookup: الدور الأرضي … الرابع |
| `period_settings` | Daily periods (A 09:00–12:00, B 12:00–15:00, C 15:00–18:00) |
| `timetable` | Weekly lecture schedule |

## examinations — الامتحانات

Exam scheduling, periods and settings.

| Table | Purpose |
|-------|---------|
| `exam_schedule` | Exam sessions with date, time, room, status workflow |
| `exam_settings` | Exam period config (dates, sessions, proctors) |

## communication — التواصل

Notifications, announcements, messages and shared materials.

| Table | Purpose |
|-------|---------|
| `notifications` | In-app notifications |
| `department_announcements` | Department announcements |
| `teacher_messages` | Staff → HOD messages |
| `message_replies` | Replies to messages |
| `teacher_documents` | Teacher document files |
| `teacher_materials` | Teacher uploaded course materials |
| `teacher_requests` | Teacher requests to HOD |

## auditing — التدقيق

System activity and change history.

| Table | Purpose |
|-------|---------|
| `history` | Audit log of every change (actor, entity, old/new values) |

---

## Registry table

`schema_domains` (created/populated automatically by `ensure_schema()` on every
startup) records `(domain, name_ar, table_name, sort_order)` for all 36 business
tables, so the database self-describes its parts.

Query it any time:

```sql
SELECT domain, name_ar, table_name
FROM schema_domains
ORDER BY domain, sort_order;
```

## Adding a table later

1. Add the table to the correct domain's `tables` list in `database/domains.py`.
2. `ensure_schema()` will re-sync `schema_domains` on the next startup.
3. Verify with `python scripts/db_domains.py`.
