CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    semesters INTEGER NOT NULL DEFAULT 1,
    majors INTEGER NOT NULL DEFAULT 7,
    hidden INTEGER NOT NULL DEFAULT 0,
    has_sections INTEGER NOT NULL DEFAULT 1,
    type TEXT NOT NULL DEFAULT 'academic',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'teacher',
    label TEXT DEFAULT '',
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    email TEXT,
    phone TEXT,
    password_changed_at TIMESTAMP,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    student_id TEXT NOT NULL UNIQUE,
    email TEXT,
    phone TEXT,
    department TEXT,
    level INTEGER DEFAULT 1,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Multi-role model: one person (a users row) may hold several system roles
-- (e.g. both 'teacher' and 'head_of_department').  users.role in the users
-- table remains the default landing role; this table is the full role set.
CREATE TABLE IF NOT EXISTS user_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, role)
);

CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    department TEXT,
    academic_number TEXT,
    national_id TEXT,
    qualification TEXT,
    academic_rank TEXT,
    classification TEXT,
    contract_date TEXT,
    tasks TEXT,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    hod_department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    qualification_id INTEGER REFERENCES qualifications(id) ON DELETE SET NULL,
    rank_id INTEGER REFERENCES academic_ranks(id) ON DELETE SET NULL,
    classification_id INTEGER REFERENCES classifications(id) ON DELETE SET NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    department TEXT,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    year INTEGER NOT NULL DEFAULT 1,
    semester INTEGER DEFAULT 1,
    theoretical_hours INTEGER NOT NULL DEFAULT 0,
    practical_hours INTEGER NOT NULL DEFAULT 0,
    total_hours INTEGER NOT NULL DEFAULT 0,
    accreditation TEXT,
    vocabulary TEXT,
    syllabus_file TEXT,
    notes TEXT,
    icon TEXT DEFAULT '📖',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT,
    capacity INTEGER DEFAULT 0,
    type TEXT,
    status TEXT,
    location TEXT,
    building TEXT DEFAULT '',
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    room_type_id INTEGER REFERENCES room_types(id) ON DELETE SET NULL,
    status_id INTEGER REFERENCES room_statuses(id) ON DELETE SET NULL,
    floor_id INTEGER REFERENCES floors(id) ON DELETE SET NULL,
    computers INTEGER DEFAULT 0,
    electronic_devices INTEGER DEFAULT 0,
    easels INTEGER DEFAULT 0,
    whiteboards INTEGER DEFAULT 0,
    projectors INTEGER DEFAULT 0,
    lab_type TEXT DEFAULT '',
    has_stage INTEGER DEFAULT 0,
    theater_seats INTEGER DEFAULT 0,
    workstations INTEGER DEFAULT 0,
    bookable INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS period_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS room_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL,
    icon TEXT DEFAULT '',
    css_class TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS room_statuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL,
    css_class TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS floors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS qualifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS academic_ranks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rank_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    qualification_id INTEGER REFERENCES qualifications(id) ON DELETE CASCADE,
    rank_id INTEGER REFERENCES academic_ranks(id) ON DELETE CASCADE,
    UNIQUE(qualification_id, rank_id)
);

CREATE TABLE IF NOT EXISTS timetable (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    semester INTEGER NOT NULL DEFAULT 1,
    course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
    room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
    period TEXT,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    student_section TEXT DEFAULT 'أ',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exam_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    exam_date TEXT DEFAULT '',
    start_time TEXT,
    end_time TEXT,
    room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
    semester INTEGER DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    exam_type TEXT DEFAULT '',
    merged_at TIMESTAMP,
    published_at TIMESTAMP,
    signed_by_hod INTEGER NOT NULL DEFAULT 0,
    signed_at TIMESTAMP,
    signed_by_user_id INTEGER,
    signed_by_username TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exam_marks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_schedule_id INTEGER NOT NULL REFERENCES exam_schedule(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    marks REAL DEFAULT 0,
    grade TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(exam_schedule_id, student_id)
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    actor_user_id INTEGER,
    actor_username TEXT,
    message TEXT,
    old_value TEXT,
    new_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'info',
    related_type TEXT DEFAULT '',
    related_id INTEGER DEFAULT 0,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    status TEXT DEFAULT 'present',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS course_prerequisites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    prerequisite_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(course_id, prerequisite_id)
);

CREATE TABLE IF NOT EXISTS course_departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    semester INTEGER DEFAULT 1,
    UNIQUE(course_id, department_id)
);

CREATE TABLE IF NOT EXISTS faculty_attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    status TEXT DEFAULT 'present',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teacher_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    message_type TEXT DEFAULT 'objection',
    related_lecture_id INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS teacher_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    file_size INTEGER,
    file_type TEXT,
    description TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS message_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES teacher_messages(id) ON DELETE CASCADE,
    sender_id INTEGER REFERENCES users(id),
    reply_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teacher_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    file_type TEXT DEFAULT '',
    is_visible INTEGER NOT NULL DEFAULT 1,
    download_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teacher_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    request_type TEXT NOT NULL DEFAULT 'general',
    subject TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    admin_reply TEXT DEFAULT '',
    reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS department_majors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS department_announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id INTEGER REFERENCES departments(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'normal',
    is_published INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_students_department ON students(department);
CREATE INDEX IF NOT EXISTS idx_teachers_department ON teachers(department);
CREATE INDEX IF NOT EXISTS idx_courses_department_year ON courses(department, year);
CREATE INDEX IF NOT EXISTS idx_courses_code ON courses(code);
CREATE INDEX IF NOT EXISTS idx_timetable_day_semester ON timetable(day, semester);
CREATE INDEX IF NOT EXISTS idx_timetable_course_id ON timetable(course_id);
CREATE INDEX IF NOT EXISTS idx_timetable_teacher_id ON timetable(teacher_id);
CREATE INDEX IF NOT EXISTS idx_timetable_room_id ON timetable(room_id);
CREATE INDEX IF NOT EXISTS idx_timetable_created_at ON timetable(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_attendance_student_date ON attendance(student_id, date);
CREATE INDEX IF NOT EXISTS idx_course_prerequisites_course ON course_prerequisites(course_id);
CREATE INDEX IF NOT EXISTS idx_course_prerequisites_prereq ON course_prerequisites(prerequisite_id);
CREATE INDEX IF NOT EXISTS idx_password_resets_token ON password_resets(token);
CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_faculty_attendance_teacher ON faculty_attendance(teacher_id);
CREATE INDEX IF NOT EXISTS idx_faculty_attendance_date ON faculty_attendance(date);
CREATE INDEX IF NOT EXISTS idx_teacher_messages_teacher ON teacher_messages(teacher_id);
CREATE INDEX IF NOT EXISTS idx_teacher_messages_dept ON teacher_messages(department_id);
CREATE INDEX IF NOT EXISTS idx_teacher_messages_status ON teacher_messages(status);
CREATE INDEX IF NOT EXISTS idx_teacher_documents_teacher ON teacher_documents(teacher_id);
CREATE INDEX IF NOT EXISTS idx_message_replies_message ON message_replies(message_id);
CREATE INDEX IF NOT EXISTS idx_teacher_materials_teacher ON teacher_materials(teacher_id);
CREATE INDEX IF NOT EXISTS idx_teacher_materials_dept ON teacher_materials(department_id);
CREATE INDEX IF NOT EXISTS idx_teacher_materials_course ON teacher_materials(course_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_teacher_requests_teacher ON teacher_requests(teacher_id);
CREATE INDEX IF NOT EXISTS idx_teacher_requests_dept ON teacher_requests(department_id);
CREATE INDEX IF NOT EXISTS idx_teacher_requests_status ON teacher_requests(status);
CREATE INDEX IF NOT EXISTS idx_dept_announcements_dept ON department_announcements(department_id);

CREATE TABLE IF NOT EXISTS student_grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    score REAL NOT NULL DEFAULT 0,
    grade_type TEXT NOT NULL DEFAULT '',
    date_given TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_student_grades_student ON student_grades(student_id);
CREATE INDEX IF NOT EXISTS idx_student_grades_teacher ON student_grades(teacher_id);
CREATE INDEX IF NOT EXISTS idx_student_grades_course ON student_grades(course_id);

CREATE TABLE IF NOT EXISTS course_content_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL,
    course_name TEXT NOT NULL,
    course_code TEXT NOT NULL,
    credits INTEGER DEFAULT 0,
    semester TEXT DEFAULT '',
    theory_hours INTEGER DEFAULT 0,
    practical_hours INTEGER DEFAULT 0,
    tutorial_hours INTEGER DEFAULT 0,
    total_hours INTEGER DEFAULT 0,
    course_objective TEXT DEFAULT '',
    prerequisites TEXT DEFAULT '',
    textbooks TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    practical_content TEXT DEFAULT '',
    practical_content_en TEXT DEFAULT '',
    study_type TEXT DEFAULT '',
    section_id TEXT DEFAULT '',
    teacher_name TEXT DEFAULT '',
    filename TEXT DEFAULT '',
    original_filename TEXT DEFAULT '',
    file_size INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    submitted_to TEXT DEFAULT '',
    submitted_at TIMESTAMP,
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    review_notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS course_content_curriculum (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL REFERENCES course_content_submissions(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    weeks INTEGER DEFAULT 1,
    content TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    section TEXT DEFAULT 'theoretical'
);

CREATE INDEX IF NOT EXISTS idx_course_content_submissions_teacher ON course_content_submissions(teacher_id);
CREATE INDEX IF NOT EXISTS idx_course_content_submissions_dept ON course_content_submissions(department_id);
CREATE INDEX IF NOT EXISTS idx_course_content_submissions_course ON course_content_submissions(course_id);
CREATE INDEX IF NOT EXISTS idx_course_content_submissions_status ON course_content_submissions(status);
CREATE INDEX IF NOT EXISTS idx_course_content_curriculum_submission ON course_content_curriculum(submission_id);

CREATE TABLE IF NOT EXISTS course_content_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL
        REFERENCES course_content_submissions(id) ON DELETE CASCADE,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    action TEXT NOT NULL,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_course_content_transitions_submission ON course_content_transitions(submission_id);

CREATE TABLE IF NOT EXISTS course_vocabulary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL UNIQUE REFERENCES courses(id) ON DELETE CASCADE,
    filename TEXT NOT NULL DEFAULT '',
    original_filename TEXT NOT NULL DEFAULT '',
    file_size INTEGER DEFAULT 0,
    uploaded_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teacher_course_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    filename TEXT NOT NULL DEFAULT '',
    original_filename TEXT NOT NULL DEFAULT '',
    file_size INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(teacher_id, course_id)
);

-- الفصل الدراسي (academic periods) — المحتوى يخص مادة + فصل دراسي
-- Created/migrated by ensure_schema (database/schema.py) on every startup.
-- course_content_submissions.academic_period_id / course_files.academic_period_id
-- reference this table (added via _safe_add_column for existing DBs).
