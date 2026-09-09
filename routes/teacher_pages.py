import json
import os
import time
import uuid

from flask import Blueprint, session, request, render_template, redirect, url_for, flash, current_app, jsonify, abort, send_from_directory

from flask_db import get_db
from database.history import add_history
from core.constants import PER_PAGE
from core.rate_limiter import RateLimiter
from security import csrf_required, login_required, permission_required, any_role_required
from security import current_user
from services import download_service, message_service, course_service, notification_service, public_service
from utils.format import semester_label
from utils.redirects import redirect_back

bp = Blueprint('teacher_pages', __name__, url_prefix='/teacher')

_messages_limiter = RateLimiter(max_requests=10, window_seconds=3600)


@bp.route('/profile')
@login_required
@any_role_required('teacher')
def teacher_profile():
    db = get_db()
    user = current_user()
    teacher = db.execute(
        '''SELECT t.*, u.username, u.email as user_email, u.label,
                  q.name_ar as qualification_name,
                  r.name_ar as rank_name,
                  cl.name_ar as classification_name,
                  d.name as department_name
           FROM teachers t
           LEFT JOIN users u ON t.user_id = u.id
           LEFT JOIN qualifications q ON t.qualification_id = q.id
           LEFT JOIN academic_ranks r ON t.rank_id = r.id
           LEFT JOIN classifications cl ON t.classification_id = cl.id
           LEFT JOIN departments d ON t.department_id = d.id
           WHERE t.user_id = ?''',
        (session['user_id'],)
    ).fetchone()
    if not teacher:
        flash('لم يتم العثور على بيانات عضو هيئة التدريس.', 'error')
        return redirect_back()

    departments = db.execute(
        '''SELECT DISTINCT d.id, d.name
           FROM timetable t
           LEFT JOIN departments d ON t.department_id = d.id
           WHERE t.teacher_id = ? AND t.deleted_at IS NULL AND d.id IS NOT NULL
           AND (t.version_id IS NULL OR t.version_id IN
               (SELECT id FROM timetable_versions WHERE status = 'active'))
           ORDER BY d.name''',
        (teacher['id'],)
    ).fetchall()

    assignments = db.execute(
        '''SELECT DISTINCT c.id, c.name as course_name, c.code as course_code
           FROM timetable t
           LEFT JOIN courses c ON t.course_id = c.id
           WHERE t.teacher_id = ? AND t.deleted_at IS NULL AND c.id IS NOT NULL
           AND (t.version_id IS NULL OR t.version_id IN
               (SELECT id FROM timetable_versions WHERE status = 'active'))
           ORDER BY c.name''',
        (teacher['id'],)
    ).fetchall()
    assignments = [dict(r) for r in assignments]

    days_order = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']
    weekly = {d: [] for d in days_order}
    rows = db.execute(
        '''SELECT t.id, t.period, t.semester, t.day,
                  c.name as course_name, c.code as course_code,
                  r.name as room_name,
                  t.start_time, t.end_time,
                  d.name as department_name
           FROM timetable t
           LEFT JOIN courses c ON t.course_id = c.id
           LEFT JOIN rooms r ON t.room_id = r.id
           LEFT JOIN departments d ON t.department_id = d.id
           WHERE t.teacher_id = ? 
           AND (t.version_id IS NULL OR t.version_id IN
               (SELECT id FROM timetable_versions WHERE status = 'active'))
           ORDER BY t.day, t.start_time''',
        (teacher['id'],)
    ).fetchall()
    for r in rows:
        if r['day'] in weekly:
            weekly[r['day']].append(dict(r))

    return render_template('teachers/profile.html', user=user,

                           teacher=dict(teacher),
                           departments=[dict(d) for d in departments],
                           assignments=assignments,
                           weekly=weekly, days_order=days_order,
                           total_courses=len(assignments),
                           total_departments=len(departments))


@bp.route('/my-schedule')
@login_required
@any_role_required('teacher')
def teacher_my_schedule():
    db = get_db()
    user = current_user()
    teacher = db.execute('SELECT id, name, department_id FROM teachers WHERE user_id = ?', (session['user_id'],)).fetchone()
    days_order = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']
    dept_colors = {}
    weekly = {d: [] for d in days_order}
    if teacher:
        rows = db.execute(
            '''SELECT t.id, t.period, t.semester, t.day, c.year, t.department_id,
                      t.course_id, t.teacher_id,
                      c.name as course_name, c.code as course_code,
                      r.name as room_name, r.capacity as room_capacity,
                      t.start_time, t.end_time,
                      d.name as department_name
               FROM timetable t
               LEFT JOIN courses c ON t.course_id = c.id
               LEFT JOIN rooms r ON t.room_id = r.id
               LEFT JOIN departments d ON t.department_id = d.id
               WHERE t.teacher_id = ?
               AND (t.version_id IS NULL OR t.version_id IN
                   (SELECT id FROM timetable_versions WHERE status = 'active'))
               ORDER BY t.day, t.start_time''',
            (teacher['id'],)
        ).fetchall()
        for r in rows:
            if r['day'] in weekly:
                weekly[r['day']].append(dict(r))
    all_dept_names = set()
    for day_entries in weekly.values():
        for e in day_entries:
            if e.get('department_name'):
                all_dept_names.add(e['department_name'])
    palette = ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336', '#00BCD4', '#795548', '#607D8B']
    for i, name in enumerate(sorted(all_dept_names)):
        dept_colors[name] = palette[i % len(palette)]

    content_maps = {'syllabus': {}, 'form': {}, 'vocab': {}}
    forms, vocab, syllabi_files = public_service.get_course_content_files(db)
    content_maps['form'] = {
        cid: {'id': item['id'], 'url': url_for('public_library.course_file', file_id=item['id'])}
        for cid, item in forms.items()
    }
    content_maps['vocab'] = {
        cid: {'id': item['id'], 'url': url_for('public_library.course_file', file_id=item['id'])}
        for cid, item in vocab.items()
    }
    syllabi = {}
    for key, item in syllabi_files.items():
        entry = {
            'id': item['id'],
            'url': url_for('public_library.course_file', file_id=item['id']),
            'teacher_id': item.get('teacher_id'),
            'course_id': item['course_id'],
        }
        syllabi[key] = entry
        if item.get('teacher_id') is None:
            syllabi['*:{}'.format(item['course_id'])] = entry
    content_maps['syllabus'] = syllabi

    return render_template('timetable/teacher.html', user=user,

                          teacher=dict(teacher) if teacher else None,
                          weekly_schedule=weekly, days_order=days_order,
                          dept_colors=dept_colors, content_maps=content_maps,
                          current_teacher_id=teacher['id'] if teacher else None)


@bp.route('/upload', methods=['GET', 'POST'])
@login_required
@permission_required('uploads.view')
@csrf_required
def teacher_upload():
    db = get_db()
    user = current_user()
    teacher = db.execute('SELECT id, name, department_id FROM teachers WHERE user_id = ?',
                         (session['user_id'],)).fetchone()
    if not teacher:
        flash('لم يتم العثور على بيانات عضو هيئة التدريس.', 'error')
        return redirect_back()

    courses = db.execute(
        'SELECT id, name, code FROM courses WHERE deleted_at IS NULL ORDER BY name'
    ).fetchall()
    departments = db.execute(
        'SELECT id, name FROM departments WHERE deleted_at IS NULL ORDER BY name'
    ).fetchall()
    upload_courses = [dict(c) for c in courses]
    upload_departments = [dict(d) for d in departments]

    if request.method == 'POST':
        file = request.files.get('file')
        title = request.form.get('title', '').strip()
        file_type = request.form.get('file_type', 'other')
        course_id = request.form.get('course_id') or None
        department_id = request.form.get('department_id') or None
        description = request.form.get('description', '').strip()
        form = {'title': title, 'file_type': file_type, 'course_id': course_id or '', 'department_id': department_id or '', 'description': description}

        if not file or file.filename == '':
            if request.form.get('next') == 'schedule':
                flash('يرجى اختيار ملف', 'error')
                return redirect(url_for('timetable.teachers_schedule'))
            return render_template('teachers/upload.html', form=form,
                                  form_error='يرجى اختيار ملف',
                                  user=user, courses=upload_courses, departments=upload_departments,
                                  materials=[])

        allowed = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.zip', '.ppt', '.pptx', '.txt', '.png', '.jpg', '.jpeg'}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed:
            if request.form.get('next') == 'schedule':
                flash('نوع الملف غير مدعوم', 'error')
                return redirect(url_for('timetable.teachers_schedule'))
            return render_template('teachers/upload.html', form=form,
                                  form_error='نوع الملف غير مدعوم',
                                  user=user, courses=upload_courses, departments=upload_departments,
                                  materials=[])

        unique_name = f"{uuid.uuid4().hex}{ext}"
        upload_folder = current_app.config['UPLOAD_FOLDER']
        teacher_dir = os.path.join(upload_folder, f"teacher_{teacher['id']}")
        os.makedirs(teacher_dir, exist_ok=True)
        save_path = os.path.join(teacher_dir, unique_name)
        file.save(save_path)

        db.execute(
            '''INSERT INTO teacher_materials
               (teacher_id, user_id, department_id, course_id, title, description,
                filename, original_filename, file_size, file_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (teacher['id'], session['user_id'], department_id, course_id,
             title or file.filename, description, f"teacher_{teacher['id']}/{unique_name}",
             file.filename, os.path.getsize(save_path), file_type)
        )
        db.commit()

        if department_id:
            hod_uids = notification_service.get_hod_user_ids(db, department_id)
            if hod_uids:
                notification_service.notify_multiple(
                    db, hod_uids,
                    'رفع ملف جديد',
                    f'عضو هيئة التدريس {teacher["name"]} رفع ملفاً جديداً: "{title or file.filename}"',
                    'files', 'teacher_material', None
                )

        flash('تم رفع الملف بنجاح', 'success')
        if request.form.get('next') == 'schedule':
            return redirect(url_for('timetable.teachers_schedule'))
        return redirect(url_for('teacher_pages.teacher_upload'))

    materials = db.execute(
        '''SELECT m.*, c.name as course_name, d.name as dept_name
           FROM teacher_materials m
           LEFT JOIN courses c ON m.course_id = c.id
           LEFT JOIN departments d ON m.department_id = d.id
           WHERE m.teacher_id = ?
           ORDER BY m.created_at DESC''',
        (teacher['id'],)
    ).fetchall()

    return render_template('teachers/upload.html', user=user,
                           form={},
                           materials=[dict(m) for m in materials],
                           courses=upload_courses,
                           departments=upload_departments)


@bp.route('/upload/delete/<int:material_id>', methods=['POST'])
@login_required
@permission_required('uploads.view')
@csrf_required
def teacher_upload_delete(material_id):
    db = get_db()
    teacher = db.execute('SELECT id FROM teachers WHERE user_id = ?',
                         (session['user_id'],)).fetchone()
    if not teacher:
        flash('خطأ', 'error')
        return redirect_back()

    mat = db.execute(
        'SELECT * FROM teacher_materials WHERE id = ? AND teacher_id = ?',
        (material_id, teacher['id'])
    ).fetchone()
    if not mat:
        flash('الملف غير موجود', 'error')
        return redirect(url_for('teacher_pages.teacher_upload'))

    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], mat['filename'])
    if os.path.exists(file_path):
        os.remove(file_path)

    db.execute('DELETE FROM teacher_materials WHERE id = ?', (material_id,))
    db.commit()
    flash('تم حذف الملف', 'success')
    if request.form.get('next') == 'schedule':
        return redirect(url_for('timetable.teachers_schedule'))
    return redirect(url_for('teacher_pages.teacher_upload'))


def _insert_course_content(db, payload):
    """Insert a course content submission row + its curriculum rows.

    Returns the new ``submission_id``.  ``submitted_at`` is only set for
    non-draft statuses (mirrors the previous behaviour).
    """
    from datetime import datetime

    submitted_at = None
    if payload.get('status') != 'draft':
        submitted_at = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    def _as_int(value):
        try:
            return int(value or 0)
        except (ValueError, TypeError):
            return 0

    theory = _as_int(payload.get('theory_hours'))
    practical = _as_int(payload.get('practical_hours'))
    tutorial = _as_int(payload.get('tutorial_hours'))

    cursor = db.execute('''
        INSERT INTO course_content_submissions
            (teacher_id, user_id, department_id, course_id, course_name, course_code,
             credits, semester, theory_hours, practical_hours, tutorial_hours, total_hours,
             course_objective, prerequisites, textbooks, notes, study_type, section_id,
             filename, original_filename, file_size,
             status, submitted_to, submitted_at,
             course_name_en, course_objective_en, prerequisites_en, textbooks_en, notes_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        payload['teacher_id'], payload['user_id'], payload['department_id'],
        payload.get('course_id'), payload['course_name'], payload['course_code'],
        payload.get('credits', 0), payload.get('semester', ''),
        theory, practical, tutorial, theory + practical + tutorial,
        payload.get('course_objective', ''), payload.get('prerequisites', ''),
        payload.get('textbooks', ''), payload.get('notes', ''),
        payload.get('study_type', ''), payload.get('section_id', ''),
        payload.get('filename', ''), payload.get('original_filename', ''),
        payload.get('file_size', 0),
        payload['status'], payload.get('submitted_to', ''), submitted_at,
        payload.get('course_name_en', ''), payload.get('course_objective_en', ''),
        payload.get('prerequisites_en', ''), payload.get('textbooks_en', ''),
        payload.get('notes_en', ''),
    ))
    submission_id = cursor.lastrowid
    for i, item in enumerate(payload.get('curriculum', [])):
        try:
            weeks = int(item.get('weeks') or 1)
        except (ValueError, TypeError):
            weeks = 1
        db.execute(
            'INSERT INTO course_content_curriculum '
            '(submission_id, topic, weeks, content, sort_order, topic_en, content_en) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (submission_id, item.get('topic', ''), weeks, item.get('content', ''), i,
             item.get('topic_en', ''), item.get('content_en', '')),
        )
    return submission_id


def _sync_form_course_file(db, submission_id, uploaded_by):
    """Mirror a submission's attached PDF into ``course_files`` (form).

    The course owns the file; the submission is the metadata record.  The
    ``course_files`` row's status always tracks the submission status so a
    form only becomes public once approved/published.  Superseded public
    forms are replaced directly in place.
    """
    row = db.execute(
        'SELECT id, course_id, teacher_id, user_id, filename, original_filename, '
        'file_size, status, academic_period_id FROM course_content_submissions '
        'WHERE id = ?',
        (submission_id,)
    ).fetchone()
    if not row:
        return
    cf = db.execute(
        "SELECT * FROM course_files WHERE submission_id = ? AND file_type = 'form'",
        (submission_id,)
    ).fetchone()

    if not row['filename']:
        if cf:
            _remove_uploaded_file(cf['filename'])
            db.execute('DELETE FROM course_files WHERE id = ?', (cf['id'],))
        return

    if cf:
        db.execute('''UPDATE course_files
                      SET filename = ?, original_filename = ?, file_size = ?,
                          status = ?, uploaded_by = ?, teacher_id = ?,
                          academic_period_id = COALESCE(?, academic_period_id),
                          updated_at = CURRENT_TIMESTAMP
                      WHERE id = ?''',
                   (row['filename'], row['original_filename'], row['file_size'],
                    row['status'], uploaded_by, row['teacher_id'],
                    row['academic_period_id'], cf['id']))
    else:
        db.execute('''INSERT INTO course_files
                      (course_id, file_type, filename, original_filename, file_size,
                       uploaded_by, teacher_id, submission_id, status,
                       academic_period_id)
                      VALUES (?, 'form', ?, ?, ?, ?, ?, ?, ?, ?)''',
                   (row['course_id'], row['filename'], row['original_filename'],
                    row['file_size'], uploaded_by, row['teacher_id'],
                    submission_id, row['status'], row['academic_period_id']))

    if row['status'] in ('approved', 'published'):
        others = db.execute(
            "SELECT * FROM course_files WHERE course_id = ? AND file_type = 'form' "
            "AND status IN ('approved', 'published') AND submission_id != ?",
            (row['course_id'], submission_id)
        ).fetchall()
        for old in others:
            db.execute('DELETE FROM course_files WHERE id = ?', (old['id'],))


def _course_context_from_db(db, course_id, teacher_id):
    """Authoritative course/assignment info from the active timetable."""
    if not course_id:
        return None
    row = db.execute('''
        SELECT c.id AS course_id, c.name AS course_name, c.code AS course_code,
               c.theoretical_hours, c.practical_hours, c.total_hours,
               c.accreditation AS credits, c.semester,
               tt.department_id, tt.student_section
        FROM timetable tt
        JOIN courses c ON tt.course_id = c.id
        WHERE tt.teacher_id = ? AND tt.course_id = ?
          AND tt.deleted_at IS NULL AND c.deleted_at IS NULL
          AND (tt.version_id IS NULL OR tt.version_id IN
              (SELECT id FROM timetable_versions WHERE status = 'active'))
        LIMIT 1
    ''', (teacher_id, course_id)).fetchone()
    return dict(row) if row else None


def _course_context_course_only(db, course_id):
    """Authoritative course info straight from the ``courses`` table.

    Course-first workflow: the form (المقرر) belongs to the course, not to a
    (timetable) teacher assignment, so the context is resolved without any
    teacher or timetable row.  Courses absent from the timetable are valid.
    """
    if not course_id:
        return None
    row = db.execute('''
        SELECT c.id AS course_id, c.name AS course_name, c.code AS course_code,
               c.theoretical_hours, c.practical_hours, c.total_hours,
               c.accreditation AS credits, c.semester,
               COALESCE(
                   (SELECT cd.department_id FROM course_departments cd
                    WHERE cd.course_id = c.id LIMIT 1),
                   c.department_id
               ) AS department_id
        FROM courses c
        WHERE c.id = ? AND c.deleted_at IS NULL
    ''', (course_id,)).fetchone()
    return dict(row) if row else None


def _curriculum_from_form(form):
    topics = form.getlist('curriculum_topic[]')
    topics_en = form.getlist('curriculum_topic_en[]')
    weeks = form.getlist('curriculum_weeks[]')
    contents = form.getlist('curriculum_content[]')
    contents_en = form.getlist('curriculum_content_en[]')
    items = []
    for i, (topic, week, content) in enumerate(zip(topics, weeks, contents)):
        if (topic or '').strip():
            try:
                w = int(week) if week else 1
            except (ValueError, TypeError):
                w = 1
            topic_en_val = topics_en[i] if i < len(topics_en) else ''
            content_en_val = contents_en[i] if i < len(contents_en) else ''
            items.append({
                'topic': (topic or '').strip(),
                'weeks': w,
                'content': (content or '').strip(),
                'topic_en': (topic_en_val or '').strip(),
                'content_en': (content_en_val or '').strip(),
            })
    return items


_STUDY_TYPE_EN = {
    'theoretical': 'Theoretical',
    'practical': 'Practical',
    'both': 'Theory & Practical',
}


def _google_translate(text):
    import urllib.parse
    import urllib.request

    url = 'https://translate.googleapis.com/translate_a/single'
    params = urllib.parse.urlencode({
        'client': 'gtx', 'sl': 'ar', 'tl': 'en', 'dt': 't', 'q': text,
    })
    req = urllib.request.Request(
        url + '?' + params,
        headers={'User-Agent': 'Mozilla/5.0'},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode('utf-8'))
    return ''.join(seg[0] for seg in payload[0] if seg and seg[0])


def _safe_translate(text):
    """Best-effort AR→EN translation. Returns '' on any failure."""
    if not text or not str(text).strip():
        return ''
    try:
        return _google_translate(str(text))
    except Exception:
        return ''


def _split_translated(translated, count, fallback):
    """Split a newline-joined translation back into per-row pieces.

    Falls back to ``fallback`` (the Arabic originals) when the split count
    does not match so rows never become misaligned.
    """
    parts = [p for p in (translated or '').split('\n')]
    if len(parts) != count:
        return fallback
    return parts


def _translate_course_content_en(db, submission_id):
    """Auto-generate English values for a course-content submission.

    Best-effort: every call is wrapped so failures never block sending.
    Skips fields that already have English content provided manually.
    Untranslated fields stay empty and templates fall back to the Arabic
    value. Curriculum topics/contents are batch-translated (newline-joined)
    to keep the number of HTTP requests small.
    """
    sub = db.execute(
        'SELECT * FROM course_content_submissions WHERE id = ?', (submission_id,)
    ).fetchone()
    if not sub:
        return

    # Skip if English content was already provided manually
    if sub['course_name_en'] and sub['course_objective_en']:
        return

    rows = [dict(r) for r in db.execute(
        'SELECT id, topic, content, topic_en, content_en FROM course_content_curriculum '
        'WHERE submission_id = ? ORDER BY sort_order',
        (submission_id,),
    ).fetchall()]

    dept_name = ''
    if sub['department_id']:
        d = db.execute(
            'SELECT name FROM departments WHERE id = ?', (sub['department_id'],)
        ).fetchone()
        if d:
            dept_name = d['name']

    def _en_values(fields):
        """Translate each non-empty field, in parallel, via a thread pool."""
        import concurrent.futures
        out = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = {
                pool.submit(_safe_translate, value): key
                for key, value in fields.items() if value
            }
            for fut in concurrent.futures.as_completed(futures):
                out[futures[fut]] = fut.result()
        return out

    fields = {
        'course_name': sub['course_name'],
        'course_objective': sub['course_objective'],
        'prerequisites': sub['prerequisites'],
        'textbooks': sub['textbooks'],
        'notes': sub['notes'],
        'department_name': dept_name,
    }
    translated = _en_values(fields)

    topic_fallback = [r['topic'] or '' for r in rows]
    content_fallback = [r['content'] or '' for r in rows]
    if rows:
        batch = _en_values({
            'topics': '\n'.join(topic_fallback),
            'contents': '\n'.join(content_fallback),
        })
        topics_en = _split_translated(batch.get('topics'), len(rows), topic_fallback)
        contents_en = _split_translated(batch.get('contents'), len(rows), content_fallback)
    else:
        topics_en, contents_en = [], []

    db.execute('''UPDATE course_content_submissions SET
            course_name_en = ?, course_objective_en = ?, prerequisites_en = ?,
            textbooks_en = ?, notes_en = ?, department_name_en = ?,
            study_type_en = ?, translated_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?''', (
        translated.get('course_name', ''),
        translated.get('course_objective', ''),
        translated.get('prerequisites', ''),
        translated.get('textbooks', ''),
        translated.get('notes', ''),
        translated.get('department_name', ''),
        _STUDY_TYPE_EN.get(sub['study_type'], ''),
        submission_id,
    ))

    for row, topic_en, content_en in zip(rows, topics_en, contents_en):
        db.execute(
            'UPDATE course_content_curriculum SET topic_en = ?, content_en = ? WHERE id = ?',
            (topic_en, content_en, row['id']),
        )


def _save_course_file(file, course_id, file_type='form'):
    """Save an uploaded PDF (only) into the course-owned folder.

    Returns ``(filename, original_filename, file_size)`` when no file was
    provided or it saved successfully, or an error message string when the
    file is invalid.
    """
    if file is None or not file.filename:
        return '', '', 0
    ext = os.path.splitext(file.filename)[1].lower()
    if ext != '.pdf':
        return 'ملف المقرر يجب أن يكون بصيغة PDF'
    # الاسم الفعلي للملف تفصيل تقني — المادة هي صاحبة العلاقة
    unique_name = f'{course_id or 0}_{file_type}_{uuid.uuid4().hex[:8]}.pdf'
    upload_folder = current_app.config['UPLOAD_FOLDER']
    course_dir = os.path.join(upload_folder, 'course_files', f'course_{course_id or 0}')
    os.makedirs(course_dir, exist_ok=True)
    save_path = os.path.join(course_dir, unique_name)
    file.save(save_path)
    return f'course_files/course_{course_id or 0}/{unique_name}', file.filename, os.path.getsize(save_path)


def _remove_uploaded_file(filename):
    if not filename:
        return
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    for _ in range(3):
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except OSError:
            time.sleep(0.15)


def _notify_rnd_about_content(db, submission_id, course_name):
    rnd_uids = notification_service.get_rnd_user_ids(db)
    if rnd_uids:
        notification_service.notify_multiple(
            db, rnd_uids,
            'محتوى مقرر للمراجعة',
            f'أرسل عضو هيئة التدريس محتوى مقرر "{course_name}" للمراجعة والاعتماد',
            'files', 'course_content', submission_id
        )


def _render_course_content_page(db, teacher=None, **extra):
    """Render the teacher upload page: assigned courses + per-course PDF state."""
    user = current_user()
    if teacher is None:
        teacher = db.execute(
            'SELECT id, name, department_id FROM teachers WHERE user_id = ?',
            (session['user_id'],)
        ).fetchone()
    course_rows = []
    if teacher:
        assigned = [dict(r) for r in db.execute(
            '''SELECT tt.course_id,
                      MAX(c.name) AS course_name,
                      MAX(c.code) AS course_code,
                      MAX(d.name) AS dept_name,
                      GROUP_CONCAT(DISTINCT tt.semester) AS semester_codes,
                      GROUP_CONCAT(DISTINCT tt.student_section) AS sections
               FROM timetable tt
               JOIN courses c ON tt.course_id = c.id
               LEFT JOIN departments d ON tt.department_id = d.id
               WHERE tt.teacher_id = ? AND tt.deleted_at IS NULL
                 AND c.deleted_at IS NULL
                 AND (tt.version_id IS NULL OR tt.version_id IN
                      (SELECT id FROM timetable_versions WHERE status = 'active'))
               GROUP BY tt.course_id
               ORDER BY c.name''',
            (teacher['id'],)
        ).fetchall()]
        if assigned:
            course_ids = [a['course_id'] for a in assigned]
            placeholders = ','.join('?' for _ in course_ids)
            params = [teacher['id']] + course_ids
            submissions = {r['course_id']: dict(r) for r in db.execute(
                f'''SELECT s.*, d.name AS dept_name
                    FROM course_content_submissions s
                    LEFT JOIN departments d ON s.department_id = d.id
                    WHERE s.teacher_id = ? AND s.course_id IN ({placeholders})
                    ORDER BY s.created_at DESC, s.id DESC''',
                params
            ).fetchall()}
            syllabus_files = {f['course_id']: dict(f) for f in db.execute(
                "SELECT * FROM course_files "
                "WHERE teacher_id = ? AND file_type = 'syllabus'",
                (teacher['id'],)
            ).fetchall()}
            for a in assigned:
                course_rows.append(_build_teacher_upload_row(
                    a, submissions.get(a['course_id']), syllabus_files.get(a['course_id'])))

    ctx = {
        'user': user,
        'teacher': dict(teacher) if teacher else None,
        'course_rows': course_rows,
        'page_mode': 'teacher_list',
    }
    ctx.update(extra)
    return render_template('teachers/course_content_page.html', **ctx)


def _build_teacher_upload_row(course, submission, syllabus_file):
    """Build one row of the teacher upload page.

    ``course`` carries course_id/course_name/course_code/dept_name/semesters.
    ``submission`` is the teacher's latest course_content_submission for the
    course (an R&D-created form when ``course_id`` is set); ``syllabus_file``
    is the teacher's syllabus ``course_files`` row.  The course PDF is
    considered uploaded when either exists.
    """
    cid = course['course_id']
    has_upload = bool(syllabus_file)
    upload_kind = 'syllabus'

    view_pdf_url = None
    if syllabus_file:
        view_pdf_url = url_for('public_library.teacher_file', tf_id=syllabus_file['id'])

    rnd_form_available = bool(submission and submission.get('course_id'))
    rnd_form_url = (url_for('teacher_pages.teacher_course_content_form_view',
                            submission_id=submission['id'])
                    if rnd_form_available else None)

    review_note = ''
    if rnd_form_available:
        if submission.get('status') == 'approved':
            review_note = 'تم اعتماد المقرر ✓'
        else:
            review_note = {
                'pending_rnd': 'قيد مراجعة البحث والتطوير',
                'pending_hod': 'قيد مراجعة رئيس القسم',
                'pending_exam': 'قيد المراجعة النهائية',
                'rejected': 'يحتاج إلى تعديل',
            }.get(submission.get('status', ''), '')

    sem_codes = [int(c) for c in (course.get('semester_codes') or '').split(',') if c]
    sem_display = ' / '.join(dict.fromkeys(semester_label(c) for c in sorted(sem_codes)))

    return {
        'course_id': cid,
        'course_code': course.get('course_code', ''),
        'course_name': course.get('course_name', ''),
        'dept_name': course.get('dept_name', '') or '—',
        'semester_display': sem_display,
        'has_upload': has_upload,
        'upload_kind': upload_kind,
        'submission_id': submission['id'] if submission else None,
        'submission_status': submission.get('status') if submission else '',
        'view_pdf_url': view_pdf_url,
        'rnd_form_available': rnd_form_available,
        'rnd_form_url': rnd_form_url,
        'review_note': review_note,
    }


@bp.route('/course-content', methods=['GET', 'POST'])
@login_required
@permission_required('course_content.edit')
@csrf_required
def teacher_course_content():
    db = get_db()
    teacher = db.execute(
        'SELECT id, name, department_id FROM teachers WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()
    if not teacher:
        flash('لم يتم العثور على بيانات عضو هيئة التدريس', 'error')
        return redirect_back()

    if request.method == 'GET' and request.args.get('new'):
        flash('النماذج تُرسل إليك من قسم البحث والتطوير فقط', 'error')
        return redirect(url_for('teacher_pages.teacher_course_content'))

    if request.method == 'POST':
        action = request.form.get('action', 'save')
        edit_id = request.form.get('submission_id', type=int)
        if not edit_id:
            flash('لا يمكنك إنشاء نموذج جديد — تُرسل النماذج إليك من قسم البحث والتطوير فقط', 'error')
            return redirect(url_for('teacher_pages.teacher_course_content'))
        course_id = request.form.get('course_id', type=int)

        course_context = _course_context_from_db(db, course_id, teacher['id'])
        if course_context:
            department_id = course_context['department_id']
            course_name = course_context['course_name']
            course_code = course_context['course_code']
        else:
            department_id = request.form.get('department_id')
            if not department_id:
                return _render_course_content_page(
                    db, teacher=teacher, form_error='يرجى اختيار القسم', selected_id=edit_id)
            try:
                department_id = int(department_id)
            except (ValueError, TypeError):
                return _render_course_content_page(
                    db, teacher=teacher, form_error='يرجى اختيار القسم', selected_id=edit_id)
            dept_check = db.execute(
                'SELECT id FROM departments WHERE id = ?', (department_id,)
            ).fetchone()
            if not dept_check:
                return _render_course_content_page(
                    db, teacher=teacher, form_error='القسم المحدد غير موجود', selected_id=edit_id)
            course_name = request.form.get('course_name', '')
            course_code = request.form.get('course_code', '')

        if action == 'send_rnd':
            status = 'pending_rnd'
            submitted_to = 'research_development'
        elif action == 'send_hod':
            status = 'pending_hod'
            submitted_to = f'department:{department_id}'
        elif action == 'send_exam':
            status = 'pending_exam'
            submitted_to = 'exam_department'
        else:
            status = 'draft'
            submitted_to = ''

        pdf = _save_course_file(request.files.get('file'), course_id, 'form')
        if isinstance(pdf, str):
            return _render_course_content_page(db, form_error=pdf, selected_id=edit_id)
        filename, original_filename, file_size = pdf
        curriculum = _curriculum_from_form(request.form)

        def _as_int(value):
            try:
                return int(value or 0)
            except (ValueError, TypeError):
                return 0

        theory_hours = _as_int(request.form.get('theory_hours'))
        practical_hours = _as_int(request.form.get('practical_hours'))
        tutorial_hours = _as_int(request.form.get('tutorial_hours'))
        content_rewritten = False

        if edit_id:
            existing = db.execute(
                'SELECT * FROM course_content_submissions WHERE id = ? AND teacher_id = ?',
                (edit_id, teacher['id'])
            ).fetchone()
            if not existing:
                flash('النموذج غير موجود', 'error')
                return redirect(url_for('teacher_pages.teacher_course_content'))
            eff_filename = filename or existing['filename'] or ''
            eff_original = original_filename or existing['original_filename'] or ''
            eff_size = file_size or existing['file_size'] or 0
            if existing['course_id']:
                # نموذج مُعدّ من قِبل البحث والتطوير: الأستاذ يُرفق ملف PDF ويرسل فقط،
                # دون تعديل أي من بيانات النموذج أو منهاجه.
                if status != 'draft' and not eff_filename:
                    return _render_course_content_page(
                        db, teacher=teacher, form_error='يجب رفع ملف PDF قبل الإرسال', selected_id=edit_id)
                db.execute('''UPDATE course_content_submissions SET
                        filename = ?, original_filename = ?, file_size = ?,
                        status = ?, submitted_to = ?,
                        submitted_at = CASE WHEN ? != 'draft'
                                           THEN CURRENT_TIMESTAMP ELSE submitted_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?''', (
                        eff_filename, eff_original, eff_size,
                        status, submitted_to, action, edit_id,
                    ))
            else:
                content_rewritten = True
                db.execute('''UPDATE course_content_submissions SET
                        department_id = ?, course_id = ?, course_name = ?, course_code = ?,
                        credits = ?, semester = ?, theory_hours = ?, practical_hours = ?,
                        tutorial_hours = ?, total_hours = ?, course_objective = ?,
                        prerequisites = ?, textbooks = ?, notes = ?, study_type = ?,
                        section_id = ?, filename = ?, original_filename = ?, file_size = ?,
                        status = ?, submitted_to = ?,
                        course_name_en = ?, course_objective_en = ?, prerequisites_en = ?,
                        textbooks_en = ?, notes_en = ?,
                        submitted_at = CASE WHEN ? != 'draft'
                                           THEN CURRENT_TIMESTAMP ELSE submitted_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?''', (
                        department_id, course_id, course_name, course_code,
                        request.form.get('credits', 0), request.form.get('semester', ''),
                        theory_hours, practical_hours, tutorial_hours,
                        theory_hours + practical_hours + tutorial_hours,
                        request.form.get('course_objective', ''), request.form.get('prerequisites', ''),
                        request.form.get('textbooks', ''), request.form.get('notes', ''),
                        request.form.get('study_type', ''), request.form.get('section_id', ''),
                        eff_filename, eff_original, eff_size,
                        status, submitted_to,
                        request.form.get('course_name_en', ''),
                        request.form.get('course_objective_en', ''),
                        request.form.get('prerequisites_en', ''),
                        request.form.get('textbooks_en', ''),
                        request.form.get('notes_en', ''),
                        action, edit_id,
                    ))
                db.execute(
                    'DELETE FROM course_content_curriculum WHERE submission_id = ?', (edit_id,)
                )
                for i, item in enumerate(curriculum):
                    db.execute(
                        'INSERT INTO course_content_curriculum '
                        '(submission_id, topic, weeks, content, sort_order, topic_en, content_en) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (edit_id, item['topic'], item['weeks'], item['content'], i,
                         item.get('topic_en', ''), item.get('content_en', '')),
                    )
            submission_id = edit_id
        else:
            if status != 'draft' and not filename:
                return _render_course_content_page(
                    db, teacher=teacher, form_error='يجب رفع ملف PDF قبل الإرسال', selected_id=edit_id)
            submission_id = _insert_course_content(db, {
                'teacher_id': teacher['id'],
                'user_id': session['user_id'],
                'department_id': department_id,
                'course_id': course_id,
                'course_name': course_name,
                'course_code': course_code,
                'credits': request.form.get('credits', 0),
                'semester': request.form.get('semester', ''),
                'theory_hours': request.form.get('theory_hours', 0),
                'practical_hours': request.form.get('practical_hours', 0),
                'tutorial_hours': request.form.get('tutorial_hours', 0),
                'total_hours': request.form.get('total_hours', 0),
                'course_objective': request.form.get('course_objective', ''),
                'prerequisites': request.form.get('prerequisites', ''),
                'textbooks': request.form.get('textbooks', ''),
                'notes': request.form.get('notes', ''),
                'study_type': request.form.get('study_type', ''),
                'section_id': request.form.get('section_id', ''),
                'filename': filename,
                'original_filename': original_filename,
                'file_size': file_size,
                'status': status,
                'submitted_to': submitted_to,
                'course_name_en': request.form.get('course_name_en', ''),
                'course_objective_en': request.form.get('course_objective_en', ''),
                'prerequisites_en': request.form.get('prerequisites_en', ''),
                'textbooks_en': request.form.get('textbooks_en', ''),
                'notes_en': request.form.get('notes_en', ''),
                'curriculum': curriculum,
            })
        if submission_id:
            _sync_form_course_file(db, submission_id, session['user_id'])
        if status != 'draft':
            translated = db.execute(
                'SELECT translated_at FROM course_content_submissions WHERE id = ?',
                (submission_id,)
            ).fetchone()
            if content_rewritten or (translated and not translated['translated_at']):
                _translate_course_content_en(db, submission_id)
        db.commit()

        if action == 'save':
            flash(f'تم حفظ نموذج محتوى المقرر "{course_name}" بنجاح', 'success')
        elif action == 'send_rnd':
            _notify_rnd_about_content(db, submission_id, course_name)
            flash(f'تم إرسال محتوى المقرر "{course_name}" للبحث والتطوير للمراجعة والاعتماد', 'success')
        elif action == 'send_hod':
            hod_uids = notification_service.get_hod_user_ids(db, department_id)
            if hod_uids:
                notification_service.notify_multiple(
                    db, hod_uids,
                    'محتوى مقرر للمراجعة',
                    f'أرسل عضو هيئة التدريس محتوى مقرر "{course_name}" للمراجعة',
                    'files', 'course_content', submission_id
                )
            flash(f'تم إرسال نموذج محتوى المقرر "{course_name}" لرئيس القسم للمراجعة', 'success')
        elif action == 'send_exam':
            exam_uids = notification_service.get_admin_user_ids(db)
            if exam_uids:
                notification_service.notify_multiple(
                    db, exam_uids,
                    'محتوى مقرر لقسم الامتحانات',
                    f'أرسل عضو هيئة التدريس محتوى مقرر "{course_name}" لقسم الامتحانات',
                    'files', 'course_content', submission_id
                )
            flash(f'تم إرسال نموذج محتوى المقرر "{course_name}" لقسم الامتحانات', 'success')

        return redirect(url_for('teacher_pages.teacher_course_content'))

    return _render_course_content_page(db, teacher=teacher)


@bp.route('/messages', methods=['GET', 'POST'])
@login_required
@permission_required('messages.view')
@csrf_required
def teacher_messages():
    db = get_db()
    requests = message_service.list_user_requests(db, session['user_id'])
    if request.method == 'POST':
        client_ip = request.remote_addr
        if _messages_limiter.is_limited(client_ip):
            abort(429)
        _messages_limiter.record(client_ip)
        teacher = message_service.get_teacher_by_user_id(db, session['user_id'])
        if not teacher:
            flash('يجب ربط حسابك بعضو هيئة التدريس أولاً', 'error')
            return redirect(url_for('teacher_pages.teacher_messages'))
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        message_type = request.form.get('message_type', 'objection')
        form = {'subject': subject, 'message': message, 'message_type': message_type}
        if not subject or not message:
            return render_template('teachers/messages.html', requests=requests,
                                  form=form, form_error='عنوان الرسالة والنص مطلوبان',
                                  user=current_user())
        department_id = teacher.get('department_id')
        message_service.create_teacher_request(db, teacher['id'], session['user_id'],
                                                department_id, message_type, subject, message)
        add_history(db, 'create', 'teacher_request', None, session['user_id'], session['username'],
                    f'إنشاء طلب: {subject}')

        hod_uids = notification_service.get_hod_user_ids(db, department_id)
        if hod_uids:
            notification_service.notify_multiple(
                db, hod_uids,
                'رسالة جديدة من عضو هيئة تدريس',
                f'{teacher["name"]}: {subject}',
                'info', 'teacher_request', None
            )

        db.commit()
        flash('تم إرسال رسالتك', 'success')
        return redirect(url_for('teacher_pages.teacher_messages'))
    return render_template('teachers/messages.html', requests=requests,
                           form={}, user=current_user())


@bp.route('/courses/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def teacher_course_edit(id):
    db = get_db()
    teacher = db.execute(
        'SELECT id, name, department_id FROM teachers WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()
    if not teacher:
        flash('لم يتم العثور على حساب عضو هيئة التدريس', 'error')
        return redirect_back()
    c = course_service.get_course(db, id)
    if not c:
        flash('المقرر غير موجود', 'error')
        return redirect_back()
    assignment = db.execute(
        'SELECT id FROM timetable WHERE teacher_id = ? AND course_id = ? AND deleted_at IS NULL',
        (teacher['id'], id)
    ).fetchone()
    if not assignment:
        flash('هذا المقرر غير مسند إليك', 'error')
        return redirect_back()
    if request.method == 'POST':
        data = {
            'theoretical_hours': request.form.get('theoretical_hours', c['theoretical_hours'], type=int),
            'practical_hours': request.form.get('practical_hours', c['practical_hours'], type=int),
            'total_hours': request.form.get('total_hours', c['total_hours'], type=int),
            'icon': (request.form.get('icon', c['icon'] or '📖').strip() or '📖'),
            'notes': request.form.get('notes', '').strip(),
        }
        db.execute(
            'UPDATE courses SET theoretical_hours=?, practical_hours=?, total_hours=?, icon=?, notes=? WHERE id=?',
            (data['theoretical_hours'], data['practical_hours'], data['total_hours'], data['icon'], data['notes'], id)
        )
        add_history(db, 'update', 'course', id, session['user_id'], session['username'],
                    f'تحديث بيانات المقرر بواسطة عضو هيئة التدريس: {teacher["name"]}')
        db.commit()
        flash('تم تحديث بيانات المقرر', 'success')
        return redirect(url_for('teacher_pages.teacher_course_edit', id=id))
    return render_template('courses/teacher_edit.html', course=dict(c),
                           user=current_user())


@bp.route('/super-admin/course-content')
@login_required
@permission_required('course_content.view')
def super_admin_course_content_list():
    """Course-centric view: one row per active course with its submissions summary."""
    db = get_db()

    search = request.args.get('search', '').strip().lower()
    dept_filter = request.args.get('department', '').strip()
    sem_filter = request.args.get('semester', '').strip()
    status_filter = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int) or 1

    departments = [dict(r) for r in db.execute(
        'SELECT id, name, semesters FROM departments WHERE deleted_at IS NULL AND hidden = 0 ORDER BY name'
    ).fetchall()]

    # كل فصول الأقسام (من إعداد القسم نفسه)، وليس فقط الفصول الموجودة لدى مواد مسجلة
    max_semesters = db.execute(
        '''SELECT COALESCE(MAX(semesters), 8)
           FROM departments WHERE deleted_at IS NULL AND hidden = 0'''
    ).fetchone()[0] or 8
    semester_values = [
        {'value': str(i), 'label': semester_label(i)}
        for i in range(1, int(max_semesters) + 1)
    ]

    course_rows = [dict(r) for r in db.execute(
        '''SELECT c.id, c.name, c.code, c.semester,
                  c.theoretical_hours, c.practical_hours, c.total_hours,
                  COALESCE(c.accreditation, '') AS credits,
                  COALESCE(d.name, '') AS dept_name
           FROM courses c
           LEFT JOIN departments d ON c.department_id = d.id
           WHERE c.deleted_at IS NULL
           ORDER BY c.name'''
    ).fetchall()]

    course_dept_names = {}
    if course_rows:
        ids = [c['id'] for c in course_rows]
        ph = ','.join('?' * len(ids))
        for r in db.execute(
            'SELECT cd.course_id, d.name AS dept_name '
            'FROM course_departments cd '
            'JOIN departments d ON cd.department_id = d.id '
            f'WHERE cd.course_id IN ({ph})',
            ids,
        ).fetchall():
            course_dept_names.setdefault(r['course_id'], set()).add(r['dept_name'])

    course_prereqs = {}
    if course_rows:
        ids = [c['id'] for c in course_rows]
        ph = ','.join('?' * len(ids))
        for r in db.execute(
            'SELECT cp.course_id, c.code AS prereq_code '
            'FROM course_prerequisites cp '
            'JOIN courses c ON c.id = cp.prerequisite_id '
            f'WHERE cp.course_id IN ({ph})',
            ids,
        ).fetchall():
            course_prereqs.setdefault(r['course_id'], []).append(r['prereq_code'])

    submission_rows = [dict(r) for r in db.execute(
        '''SELECT s.id, s.course_id, s.status, s.teacher_id, s.filename,
                  COALESCE(s.submitted_at, s.created_at) AS sent_at,
                  t.name AS teacher_name
           FROM course_content_submissions s
           LEFT JOIN teachers t ON s.teacher_id = t.id
           ORDER BY sent_at DESC'''
    ).fetchall()]

    submissions_by_course = {}
    for s in submission_rows:
        submissions_by_course.setdefault(s['course_id'], []).append(s)

    courses = []
    pending_review_count = 0
    for c in course_rows:
        subs = submissions_by_course.get(c['id'], [])
        latest_status = subs[0]['status'] if subs else ''
        has_pending = any(s['status'] == 'pending_rnd' for s in subs)
        pending_review_count += sum(1 for s in subs if s['status'] == 'pending_rnd')

        all_dept_names = set(course_dept_names.get(c['id'], set()))
        if c['dept_name']:
            all_dept_names.add(c['dept_name'])

        hay = ' '.join(filter(None, [
            str(c['name'] or ''), str(c['code'] or ''),
            ' '.join(all_dept_names),
            str(semester_label(c['semester']) or ''), str(c['semester'] or ''),
        ])).lower()

        ok_search = not search or search in hay
        ok_dept = not dept_filter or dept_filter in all_dept_names
        ok_sem = not sem_filter or str(c['semester']) == sem_filter
        ok_status = (not status_filter or latest_status == status_filter
                     or (status_filter == 'pending_rnd' and has_pending))
        if not (ok_search and ok_dept and ok_sem and ok_status):
            continue

        latest_with_file = next((s for s in subs if s.get('filename')), None)
        courses.append({
            **c,
            'dept_names': sorted(all_dept_names),
            'prereqs': course_prereqs.get(c['id'], []),
            'submission_count': len(subs),
            'latest_status': latest_status,
            'form_status': latest_status,
            'latest_submission_id': subs[0]['id'] if subs else None,
            'latest_form_submission_id': subs[0]['id'] if subs else None,
            'latest_form_file_id': latest_with_file['id'] if latest_with_file else None,
            'latest_has_form': bool(latest_with_file),
            'latest_teacher': subs[0]['teacher_name'] if subs else '',
            'has_pending': has_pending,
        })

    # المدرّسون المسندون حالياً + حالة نموذج المحتوى لكل مقرر (استعلامان فقط)
    course_service.attach_course_related_data(db, courses)

    vocab_by_course = {}
    for r in db.execute('''
        SELECT v.id, v.course_id, v.original_filename, v.file_size, v.created_at
        FROM course_files v
        WHERE v.file_type = 'vocabulary'
        ORDER BY v.created_at DESC
    ''').fetchall():
        v = dict(r)
        vocab_by_course.setdefault(v['course_id'], v)

    syllabus_by_course = {}
    for r in db.execute('''
        SELECT syl.id, syl.course_id, syl.original_filename, syl.file_size,
               COALESCE(syl.updated_at, syl.created_at) AS file_date
        FROM course_files syl
        WHERE syl.file_type = 'syllabus'
        ORDER BY file_date DESC
    ''').fetchall():
        syl = dict(r)
        syllabus_by_course.setdefault(syl['course_id'], syl)

    total = len(courses)
    total_pages = max(1, -(-total // PER_PAGE))
    page = min(max(1, page), total_pages)
    courses = courses[(page - 1) * PER_PAGE: page * PER_PAGE]

    academic_periods = _get_academic_periods(db)

    return render_template('teachers/course_content_page.html',
                           user=current_user(), page_mode='admin_list',
                           courses=courses, departments=departments,
                           vocab_by_course=vocab_by_course,
                           syllabus_by_course=syllabus_by_course,
                           academic_periods=academic_periods,
                           default_period_id=_current_academic_period_id(academic_periods),
                           pending_review_count=pending_review_count,
                           semester_values=semester_values,
                           search=request.args.get('search', ''),
                           dept_filter=dept_filter,
                           sem_filter=sem_filter,
                           status_filter=status_filter,
                           total=total, page=page,
                           per_page=PER_PAGE, total_pages=total_pages)


@bp.route('/super-admin/course-content/course/<int:course_id>')
@login_required
@permission_required('course_content.view')
def super_admin_course_content_history(course_id):
    """Redundant page — replaced by the course list view."""
    return redirect(url_for('teacher_pages.super_admin_course_content_list'))


@bp.route('/super-admin/course-content/vocabulary/<int:course_id>')
@login_required
@permission_required('course_content.view')
def super_admin_vocabulary_manage(course_id):
    """Upload / replace / download / delete the vocabulary file of one course."""
    db = get_db()
    course = db.execute(
        '''SELECT c.id, c.name, c.code, c.semester,
                  COALESCE(d.name, '') AS dept_name
           FROM courses c
           LEFT JOIN departments d ON c.department_id = d.id
           WHERE c.id = ? AND c.deleted_at IS NULL''',
        (course_id,)
    ).fetchone()
    if not course:
        flash('المقرر غير موجود', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))

    vocab = db.execute(
        '''SELECT * FROM course_files
           WHERE course_id = ? AND file_type = 'vocabulary'
           ORDER BY created_at DESC LIMIT 1''',
        (course_id,)
    ).fetchone()

    return render_template('teachers/super_admin_vocabulary.html',
                           user=current_user(),
                           course=dict(course),
                           vocab=dict(vocab) if vocab else None)


@bp.route('/super-admin/course-content/vocabulary/upload', methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_vocabulary_upload():
    db = get_db()
    course_id = request.form.get('course_id', type=int)
    if not course_id:
        flash('يرجى اختيار المقرر', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))
    course = db.execute(
        'SELECT id, name FROM courses WHERE id = ? AND deleted_at IS NULL', (course_id,)
    ).fetchone()
    if not course:
        flash('المقرر غير موجود', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))
    saved = _save_course_file(request.files.get('file'), course_id, 'vocabulary')
    if isinstance(saved, str):
        flash(saved, 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))
    filename, original_filename, file_size = saved
    if not filename:
        flash('يرجى رفع ملف المفردات بصيغة PDF', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))
    old = db.execute(
        "SELECT * FROM course_files WHERE course_id = ? AND file_type = 'vocabulary'",
        (course_id,)
    ).fetchone()
    if old:
        _remove_uploaded_file(old['filename'])
        db.execute('DELETE FROM course_files WHERE id = ?', (old['id'],))
    db.execute('''INSERT INTO course_files
                  (course_id, file_type, filename, original_filename, file_size,
                   uploaded_by, status)
                  VALUES (?, 'vocabulary', ?, ?, ?, ?, 'approved')''',
               (course_id, filename, original_filename, file_size, session['user_id']))
    db.commit()
    flash(f'تم رفع مفردات المقرر "{course["name"]}"', 'success')
    return redirect(url_for('teacher_pages.super_admin_course_content_list'))


@bp.route('/super-admin/course-content/vocabulary/<int:vocab_id>/delete', methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_vocabulary_delete(vocab_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM course_files WHERE id = ? AND file_type = 'vocabulary'", (vocab_id,)
    ).fetchone()
    if not row:
        flash('المفردات غير موجودة', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))
    _remove_uploaded_file(row['filename'])
    db.execute('DELETE FROM course_files WHERE id = ?', (vocab_id,))
    db.commit()
    flash('تم حذف المفردات', 'success')
    return redirect(url_for('teacher_pages.super_admin_course_content_list'))


@bp.route('/super-admin/course-content/<int:submission_id>')
@login_required
@permission_required('course_content.view')
def super_admin_course_content_detail(submission_id):
    db = get_db()
    submission = db.execute('''
        SELECT s.*, d.name as dept_name,
               t.name as teacher_name, u.username as submitter_username,
               ap.label AS period_label
        FROM course_content_submissions s
        LEFT JOIN departments d ON s.department_id = d.id
        LEFT JOIN teachers t ON s.teacher_id = t.id
        LEFT JOIN users u ON s.user_id = u.id
        LEFT JOIN academic_periods ap ON s.academic_period_id = ap.id
        WHERE s.id = ?
    ''', (submission_id,)).fetchone()

    if not submission:
        flash('النموذج غير موجود', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))

    curriculum = [dict(r) for r in db.execute(
        'SELECT * FROM course_content_curriculum WHERE submission_id = ? ORDER BY sort_order',
        (submission_id,)
    ).fetchall()]

    periods = _get_academic_periods(db)
    rnd = request.args.get('rnd', 'show')
    return render_template('teachers/course_content_page.html',
                          user=current_user(),
                          submission=dict(submission), page_mode='view',
                          curriculum=curriculum,
                          academic_periods=periods,
                          default_period_id=_current_academic_period_id(periods),
                          auto_print=request.args.get('print') == '1',
                          rnd=rnd)


@bp.route('/super-admin/course-content/send', methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_course_content_send():
    db = get_db()
    course_id = request.form.get('course_id', type=int)
    action = request.form.get('action', 'send')
    submission_id = request.form.get('submission_id', type=int)

    if not course_id:
        flash('يرجى اختيار المقرر', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))

    course = db.execute(
        'SELECT id, name, code FROM courses WHERE id = ? AND deleted_at IS NULL',
        (course_id,)
    ).fetchone()
    context = _course_context_course_only(db, course_id)
    if not course or not context:
        flash('المقرر غير موجود', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))

    department_id = context.get('department_id')
    if not department_id:
        try:
            department_id = int(request.form.get('department_id') or 0) or None
        except (ValueError, TypeError):
            department_id = None
    if not department_id:
        flash('المقرر ليس له قسم — يرجى ربط المقرر بقسم أولاً', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))

    if action == 'save':
        status = 'draft'
    else:
        status = 'published'

    submitted_to = ''
    curriculum = _curriculum_from_form(request.form)

    def _as_int(value):
        try:
            return int(value or 0)
        except (ValueError, TypeError):
            return 0

    theory = _as_int(request.form.get('theory_hours'))
    practical = _as_int(request.form.get('practical_hours'))
    tutorial = _as_int(request.form.get('tutorial_hours'))

    if submission_id:
        existing = db.execute(
            'SELECT id FROM course_content_submissions WHERE id = ?',
            (submission_id,)
        ).fetchone()
        if not existing:
            flash('النموذج غير موجود', 'error')
            return redirect(url_for('teacher_pages.super_admin_course_content_list'))

        db.execute('''UPDATE course_content_submissions SET
                department_id = ?, course_id = ?, course_name = ?, course_code = ?,
                credits = ?, semester = ?, theory_hours = ?, practical_hours = ?,
                tutorial_hours = ?, total_hours = ?, course_objective = ?,
                prerequisites = ?, textbooks = ?, notes = ?, study_type = ?,
                section_id = ?, status = ?, submitted_to = ?,
                course_name_en = ?, course_objective_en = ?,
                prerequisites_en = ?, textbooks_en = ?, notes_en = ?,
                submitted_at = CASE WHEN ? != 'draft'
                                   THEN CURRENT_TIMESTAMP ELSE submitted_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?''', (
            department_id, course_id, course['name'], course['code'],
            request.form.get('credits', 0),
            context.get('semester') or request.form.get('semester', ''),
            theory, practical, tutorial, theory + practical + tutorial,
            request.form.get('course_objective', ''),
            request.form.get('prerequisites', ''),
            request.form.get('textbooks', ''), request.form.get('notes', ''),
            request.form.get('study_type', ''), request.form.get('section_id', ''),
            status, submitted_to,
            request.form.get('course_name_en', ''),
            request.form.get('course_objective_en', ''),
            request.form.get('prerequisites_en', ''),
            request.form.get('textbooks_en', ''),
            request.form.get('notes_en', ''),
            status, submission_id,
        ))
        db.execute('DELETE FROM course_content_curriculum WHERE submission_id = ?',
                   (submission_id,))
        for i, item in enumerate(curriculum):
            try:
                weeks = int(item.get('weeks') or 1)
            except (ValueError, TypeError):
                weeks = 1
            db.execute(
                'INSERT INTO course_content_curriculum '
                '(submission_id, topic, weeks, content, sort_order, topic_en, content_en) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (submission_id, item.get('topic', ''), weeks,
                 item.get('content', ''), i,
                 item.get('topic_en', ''), item.get('content_en', '')),
            )
    else:
        submission_id = _insert_course_content(db, {
            'teacher_id': None,
            'user_id': session['user_id'],
            'department_id': department_id,
            'course_id': course_id,
            'course_name': course['name'],
            'course_code': course['code'],
            'credits': request.form.get('credits', 0),
            'semester': context.get('semester') or request.form.get('semester', ''),
            'theory_hours': theory,
            'practical_hours': practical,
            'tutorial_hours': tutorial,
            'total_hours': theory + practical + tutorial,
            'course_objective': request.form.get('course_objective', ''),
            'prerequisites': request.form.get('prerequisites', ''),
            'textbooks': request.form.get('textbooks', ''),
            'notes': request.form.get('notes', ''),
            'study_type': request.form.get('study_type', ''),
            'section_id': request.form.get('section_id', ''),
            'status': status,
            'submitted_to': submitted_to,
            'course_name_en': request.form.get('course_name_en', ''),
            'course_objective_en': request.form.get('course_objective_en', ''),
            'prerequisites_en': request.form.get('prerequisites_en', ''),
            'textbooks_en': request.form.get('textbooks_en', ''),
            'notes_en': request.form.get('notes_en', ''),
            'curriculum': curriculum,
        })

    form_file = request.files.get('form_file')
    if form_file and form_file.filename:
        saved = _save_course_file(form_file, course_id, 'form')
        if isinstance(saved, str):
            flash(saved, 'error')
        elif saved[0]:
            f_name, f_orig, f_size = saved
            db.execute('''UPDATE course_content_submissions
                          SET filename = ?, original_filename = ?, file_size = ?
                          WHERE id = ?''',
                       (f_name, f_orig, f_size, submission_id))

    period_id = request.form.get('academic_period_id', type=int) or None
    if period_id and db.execute(
            'SELECT 1 FROM academic_periods WHERE id = ?', (period_id,)).fetchone():
        db.execute('''UPDATE course_content_submissions
                      SET academic_period_id = ? WHERE id = ?''',
                   (period_id, submission_id))
    _sync_form_course_file(db, submission_id, session['user_id'])
    if status == 'published':
        db.execute('''UPDATE course_content_submissions
                      SET reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP,
                          updated_at = CURRENT_TIMESTAMP
                      WHERE id = ?''',
                   (session['user_id'], submission_id))
        _translate_course_content_en(db, submission_id)
    db.commit()

    if status == 'published':
        flash(f'تم نشر نموذج مقرر "{course["name"]}" وسيظهر للمستخدمين', 'success')
    else:
        flash(f'تم حفظ نموذج مقرر "{course["name"]}" كمسودة', 'success')

    return redirect(url_for('teacher_pages.super_admin_course_content_list'))


@bp.route('/super-admin/course-content/create')
@login_required
@permission_required('course_content.view')
def super_admin_course_content_create():
    db = get_db()
    course_id = request.form.get('course_id', type=int) if request.method == 'POST' else request.args.get('course_id', type=int)
    submission_id = request.form.get('submission_id', type=int) if request.method == 'POST' else request.args.get('submission_id', type=int)

    if submission_id:
        sub = db.execute(
            '''SELECT s.*, COALESCE(d.name, '') AS department_name
               FROM course_content_submissions s
               LEFT JOIN departments d ON s.department_id = d.id
               WHERE s.id = ?''',
            (submission_id,)
        ).fetchone()
        if not sub:
            flash('النموذج غير موجود', 'error')
            return redirect(url_for('teacher_pages.super_admin_course_content_list'))
        doc = {
            'course_id': sub['course_id'],
            'course_name': sub['course_name'],
            'course_code': sub['course_code'],
            'credits': sub['credits'],
            'semester': sub['semester'],
            'theory_hours': sub['theory_hours'],
            'practical_hours': sub['practical_hours'],
            'tutorial_hours': sub['tutorial_hours'],
            'total_hours': sub['total_hours'],
            'study_type': sub['study_type'],
            'section_id': sub['section_id'],
            'department_name': sub['department_name'],
            'course_objective': sub['course_objective'],
            'prerequisites': sub['prerequisites'],
            'textbooks': sub['textbooks'],
            'notes': sub['notes'],
            'course_name_en': sub['course_name_en'] or '',
            'course_objective_en': sub['course_objective_en'] or '',
            'prerequisites_en': sub['prerequisites_en'] or '',
            'textbooks_en': sub['textbooks_en'] or '',
            'notes_en': sub['notes_en'] or '',
        }
        curriculum = [dict(r) for r in db.execute(
            'SELECT topic, weeks, content, topic_en, content_en '
            'FROM course_content_curriculum WHERE submission_id = ? '
            'ORDER BY sort_order',
            (submission_id,)
        ).fetchall()]
        courses = []
    elif course_id:
        context = _course_context_course_only(db, course_id)
        if not context:
            flash('المقرر غير موجود', 'error')
            return redirect(url_for('teacher_pages.super_admin_course_content_list'))

        dept = db.execute(
            'SELECT name FROM departments WHERE id = ?', (context['department_id'],)
        ).fetchone()
        doc = {
            'course_id': context['course_id'],
            'course_name': context['course_name'],
            'course_code': context['course_code'],
            'credits': context['credits'],
            'semester': context['semester'],
            'theory_hours': context['theoretical_hours'],
            'practical_hours': context['practical_hours'],
            'tutorial_hours': 0,
            'total_hours': context['total_hours'],
            'study_type': '',
            'section_id': '',
            'department_name': dept['name'] if dept else '',
            'course_objective': '',
            'prerequisites': '',
            'textbooks': '',
            'notes': '',
            'course_name_en': '',
            'course_objective_en': '',
            'prerequisites_en': '',
            'textbooks_en': '',
            'notes_en': '',
        }
        curriculum = []
        courses = []
    else:
        doc = {
            'course_id': '',
            'course_name': '',
            'course_code': '',
            'credits': '',
            'semester': '',
            'theory_hours': '',
            'practical_hours': '',
            'tutorial_hours': 0,
            'total_hours': '',
            'study_type': '',
            'section_id': '',
            'department_name': '',
            'course_objective': '',
            'prerequisites': '',
            'textbooks': '',
            'notes': '',
        }
        curriculum = []
        courses = [dict(r) for r in db.execute(
            '''SELECT c.id, c.name, c.code, c.semester,
                      c.theoretical_hours, c.practical_hours, c.total_hours,
                      c.accreditation AS credits,
                      COALESCE(d.name, '') AS department_name
               FROM courses c
               LEFT JOIN course_departments cd ON cd.course_id = c.id
               LEFT JOIN departments d ON cd.department_id = d.id
               WHERE c.deleted_at IS NULL
               GROUP BY c.id
               ORDER BY c.name'''
        ).fetchall()]

    academic_periods = _get_academic_periods(db)
    return render_template('teachers/course_content_page.html',
                           user=current_user(), doc=doc, courses=courses,
                           curriculum=curriculum,
                           page_mode='edit' if submission_id else 'create',
                           edit_submission_id=submission_id,
                           auto_print=request.args.get('print') == '1',
                           academic_periods=academic_periods,
                           default_period_id=_current_academic_period_id(
                               academic_periods))


@bp.route('/super-admin/course-content/<int:submission_id>/review', methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_course_content_review(submission_id):
    db = get_db()
    submission = db.execute(
        'SELECT * FROM course_content_submissions WHERE id = ?', (submission_id,)
    ).fetchone()
    if not submission:
        flash('النموذج غير موجود', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))
    if submission['status'] != 'pending_rnd':
        flash('هذا النموذج غير قابل للمراجعة حالياً', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_detail', submission_id=submission_id))

    action = request.form.get('action', '')
    review_notes = request.form.get('review_notes', '').strip()
    detail_url = url_for('teacher_pages.super_admin_course_content_detail', submission_id=submission_id)

    if action == 'approve':
        status = 'approved'
        message = f'تم اعتماد محتوى المقرر "{submission["course_name"]}"'
        notes = review_notes
    elif action == 'reject':
        if not review_notes:
            flash('سبب الرفض مطلوب', 'error')
            return redirect(detail_url)
        status = 'rejected'
        message = f'تم رفض محتوى المقرر "{submission["course_name"]}"'
        notes = review_notes
    else:
        flash('إجراء غير صحيح', 'error')
        return redirect(detail_url)

    db.execute('''UPDATE course_content_submissions
                  SET status = ?, submitted_to = ?,
                      reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP,
                      review_notes = ?, updated_at = CURRENT_TIMESTAMP
                  WHERE id = ?''',
               (status, status, session['user_id'], notes, submission_id))
    _sync_form_course_file(db, submission_id, session['user_id'])
    db.commit()

    teacher_uid = notification_service.get_teacher_user_id(db, submission['teacher_id'])
    if teacher_uid:
        note_suffix = f' — السبب: {notes}' if status == 'rejected' else ''
        notification_service.create_notification(
            db, teacher_uid,
            'محتوى المقرر',
            message + note_suffix,
            'files', 'course_content', submission_id
        )

    flash(message, 'success')
    return redirect(detail_url)


@bp.route('/super-admin/course-content/update-form', methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_course_content_update_form():
    db = get_db()
    submission_id = request.form.get('submission_id', type=int)
    if not submission_id:
        flash('يرجى تحديد النموذج', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))
    submission = db.execute(
        'SELECT * FROM course_content_submissions WHERE id = ?', (submission_id,)
    ).fetchone()
    if not submission:
        flash('النموذج غير موجود', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))
    detail_url = url_for('teacher_pages.super_admin_course_content_detail', submission_id=submission_id)

    saved = _save_course_file(request.files.get('file'), submission['course_id'], 'form')
    if isinstance(saved, str):
        flash(saved, 'error')
        return redirect(detail_url)
    filename, original_filename, file_size = saved
    if not filename:
        flash('يرجى رفع ملف النموذج بصيغة PDF', 'error')
        return redirect(detail_url)

    period_id = request.form.get('academic_period_id', type=int) or None
    if period_id and not db.execute(
            'SELECT 1 FROM academic_periods WHERE id = ?', (period_id,)).fetchone():
        flash('الفصل الدراسي غير صحيح', 'error')
        return redirect(detail_url)

    db.execute('''UPDATE course_content_submissions
                  SET filename = ?, original_filename = ?, file_size = ?,
                      academic_period_id = COALESCE(?, academic_period_id),
                      updated_at = CURRENT_TIMESTAMP
                  WHERE id = ?''',
               (filename, original_filename, file_size, period_id, submission_id))
    _sync_form_course_file(db, submission_id, session['user_id'])
    db.commit()
    flash(f'تم تحديث ملف النموذج لمقرر "{submission["course_name"]}" '
          'تم تحديث الملف بنجاح', 'success')
    return redirect(detail_url)


def _latest_syllabus_rows(db, course_id):
    """All current syllabus rows of a course, newest first."""
    return db.execute(
        "SELECT * FROM course_files "
        "WHERE course_id = ? AND file_type = 'syllabus' "
        "ORDER BY COALESCE(updated_at, created_at) DESC",
        (course_id,)
    ).fetchall()


def _get_academic_periods(db):
    """الفصول الدراسية (الأحدث أولاً): خريف ثم ربيع داخل كل سنة."""
    return [dict(r) for r in db.execute(
        '''SELECT id, year, term, label FROM academic_periods
           ORDER BY year DESC, CASE term WHEN 'خريف' THEN 0 ELSE 1 END'''
    ).fetchall()]


def _current_academic_period_id(periods):
    """تقدير الفصل الحالي: خريف من تموز فصاعداً، وربيع قبله."""
    import datetime as _dt
    today = _dt.date.today()
    term = 'خريف' if today.month >= 7 else 'ربيع'
    year = today.year if term == 'خريف' else (
        today.year if today.month >= 1 else today.year - 1)
    for p in periods:
        if p['term'] == term and p['year'] == year:
            return p['id']
    return periods[0]['id'] if periods else None


@bp.route('/super-admin/course-content/course/<int:course_id>/syllabus-file')
@login_required
@permission_required('course_content.view')
def super_admin_course_syllabus_file(course_id):
    """Serve the course's current syllabus PDF (inline or as attachment)."""
    db = get_db()
    rows = _latest_syllabus_rows(db, course_id)
    if not rows or not rows[0]['filename']:
        abort(404)
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], rows[0]['filename'])
    if not os.path.exists(path):
        abort(404)
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'], rows[0]['filename'],
        as_attachment=request.args.get('download') == '1',
        download_name=rows[0]['original_filename'] or 'course-syllabus.pdf',
    )


@bp.route('/super-admin/course-content/course-file/<int:file_id>')
@login_required
@permission_required('course_content.view')
def super_admin_course_file_serve(file_id):
    """Serve one specific course_files row."""
    row = get_db().execute(
        'SELECT * FROM course_files WHERE id = ?', (file_id,)
    ).fetchone()
    if not row or not row['filename']:
        abort(404)
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], row['filename'])
    if not os.path.exists(path):
        abort(404)
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'], row['filename'],
        as_attachment=request.args.get('download') == '1',
        download_name=row['original_filename'] or 'course-file.pdf',
    )


@bp.route('/super-admin/course-content/course/<int:course_id>/syllabus/upload', methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_course_syllabus_upload(course_id):
    """Upload (or replace) المقرر PDF scoped to course + academic period.

    Replaces only the copy of the same period; other periods keep their own
    copies.
    """
    db = get_db()
    course = db.execute(
        'SELECT id, name FROM courses WHERE id = ? AND deleted_at IS NULL', (course_id,)
    ).fetchone()
    if not course:
        flash('المقرر غير موجود', 'error')
        return redirect_back()
    period_id = request.form.get('academic_period_id', type=int) or None
    if period_id and not db.execute(
            'SELECT 1 FROM academic_periods WHERE id = ?', (period_id,)).fetchone():
        flash('الفصل الدراسي غير صحيح', 'error')
        return redirect_back()
    saved = _save_course_file(request.files.get('file'), course_id, 'syllabus')
    if isinstance(saved, str):
        flash(saved, 'error')
        return redirect_back()
    filename, original_filename, file_size = saved
    if not filename:
        flash('يرجى رفع ملف المقرر بصيغة PDF', 'error')
        return redirect_back()
    for old in db.execute(
            '''SELECT * FROM course_files
               WHERE course_id = ? AND file_type = 'syllabus'
                 AND academic_period_id IS ?''',
            (course_id, period_id)).fetchall():
        db.execute('DELETE FROM course_files WHERE id = ?', (old['id'],))
    db.execute('''INSERT INTO course_files
                  (course_id, file_type, filename, original_filename, file_size,
                   uploaded_by, teacher_id, status, academic_period_id)
                  VALUES (?, 'syllabus', ?, ?, ?, ?, NULL, 'approved', ?)''',
               (course_id, filename, original_filename, file_size,
                session['user_id'], period_id))
    add_history(db, 'upload', 'course_syllabus', course_id, session['user_id'],
                session['username'],
                f"رفع/تحديث ملف مقرر بواسطة المشرف: {course['name']}")
    db.commit()
    flash(f'تم رفع ملف المقرر لمادة "{course["name"]}"', 'success')
    return redirect_back()


@bp.route('/super-admin/course-content/course/<int:course_id>/form/upload', methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_course_content_form_upload(course_id):
    """Attach/replace the course's form PDF, scoped to the course itself.

    Targets the latest existing submission; creates a minimal approved one
    when the course has no submission yet.
    """
    db = get_db()
    course = db.execute(
        '''SELECT id, name, code, semester, theoretical_hours, practical_hours,
                  total_hours, accreditation, department_id
           FROM courses WHERE id = ? AND deleted_at IS NULL''',
        (course_id,)
    ).fetchone()
    if not course:
        flash('المقرر غير موجود', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))
    # department is NOT NULL on submissions — resolve it (course → رابط القسم)
    ctx = _course_context_course_only(db, course_id)
    department_id = (ctx or {}).get('department_id') or course['department_id']
    history_url = url_for('teacher_pages.super_admin_course_content_list')
    if not department_id:
        flash(f'مادة "{course["name"]}" غير مرتبطة بأي قسم — '
              'اربطها بقسم أولاً ثم أعد رفع النموذج', 'error')
        return redirect(history_url)
    period_id = request.form.get('academic_period_id', type=int) or None
    if period_id and not db.execute(
            'SELECT 1 FROM academic_periods WHERE id = ?', (period_id,)).fetchone():
        flash('الفصل الدراسي غير صحيح', 'error')
        return redirect(history_url)
    saved = _save_course_file(request.files.get('file'), course_id, 'form')
    if isinstance(saved, str):
        flash(saved, 'error')
        return redirect(history_url)
    filename, original_filename, file_size = saved
    if not filename:
        flash('يرجى رفع ملف النموذج بصيغة PDF', 'error')
        return redirect(history_url)

    submission = db.execute(
        '''SELECT * FROM course_content_submissions WHERE course_id = ?
           ORDER BY COALESCE(submitted_at, created_at) DESC, id DESC LIMIT 1''',
        (course_id,)
    ).fetchone()

    if submission:
        submission_id = submission['id']
        db.execute('''UPDATE course_content_submissions
                      SET filename = ?, original_filename = ?, file_size = ?,
                          academic_period_id = COALESCE(?, academic_period_id),
                          updated_at = CURRENT_TIMESTAMP
                      WHERE id = ?''',
                   (filename, original_filename, file_size, period_id, submission_id))
    else:
        submission_id = _insert_course_content(db, {
            'teacher_id': None,
            'user_id': session['user_id'],
            'department_id': department_id,
            'course_id': course_id,
            'course_name': course['name'],
            'course_code': course['code'],
            'credits': course['accreditation'] or 0,
            'semester': str(course['semester'] or ''),
            'theory_hours': course['theoretical_hours'] or 0,
            'practical_hours': course['practical_hours'] or 0,
            'tutorial_hours': 0,
            'total_hours': course['total_hours'] or 0,
            'course_objective': '',
            'prerequisites': '',
            'textbooks': '',
            'notes': '',
            'study_type': '',
            'section_id': '',
            'status': 'approved',
            'submitted_to': '',
            'course_name_en': '',
            'course_objective_en': '',
            'prerequisites_en': '',
            'textbooks_en': '',
            'notes_en': '',
            'curriculum': [],
        })
        db.execute('''UPDATE course_content_submissions
                      SET filename = ?, original_filename = ?, file_size = ?,
                          academic_period_id = ?,
                          submitted_at = CURRENT_TIMESTAMP,
                          reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
                      WHERE id = ?''',
                   (filename, original_filename, file_size, period_id,
                    session['user_id'], submission_id))

    _sync_form_course_file(db, submission_id, session['user_id'])
    add_history(db, 'upload', 'course_content', submission_id,
                session['user_id'], session['username'],
                f"رفع/تحديث ملف نموذج المقرر بواسطة المشرف: {course['name']}")
    db.commit()
    flash(f'تم رفع ملف النموذج لمقرر "{course["name"]}"', 'success')
    if session.get('role') == 'research_development':
        return redirect(url_for('dashboard.dashboard'))
    return redirect(history_url)


@bp.route('/super-admin/course-content/course/<int:course_id>/syllabus/delete', methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_course_syllabus_delete(course_id):
    """Remove the current syllabus copy from active files."""
    db = get_db()
    course = db.execute(
        'SELECT id, name FROM courses WHERE id = ?', (course_id,)
    ).fetchone()
    if not course:
        flash('المقرر غير موجود', 'error')
        return redirect_back()
    rows = _latest_syllabus_rows(db, course_id)
    if not rows:
        flash('لا يوجد ملف منهاج لهذا المقرر', 'error')
        return redirect_back()
    for old in rows:
        db.execute('DELETE FROM course_files WHERE id = ?', (old['id'],))
    add_history(db, 'delete', 'course_syllabus', course_id, session['user_id'],
                session['username'],
                f"حذف ملف منهاج المقرر بواسطة المشرف: {course['name']}")
    db.commit()
    flash(f'تم حذف ملف المنهاج لمقرر "{course["name"]}"', 'success')
    return redirect_back()


@bp.route('/super-admin/course-content/course-file/<int:file_id>/delete', methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_course_file_delete(file_id):
    """حذف نسخة مقرر محددة (مادة + فصل دراسي) — المادة تبقى."""
    db = get_db()
    row = db.execute(
        '''SELECT * FROM course_files WHERE id = ? AND file_type = 'syllabus' ''',
        (file_id,)
    ).fetchone()
    if not row:
        flash('ملف المقرر غير موجود', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))
    course = db.execute('SELECT name FROM courses WHERE id = ?', (row['course_id'],)).fetchone()
    db.execute('DELETE FROM course_files WHERE id = ?', (file_id,))
    add_history(db, 'delete', 'course_syllabus', row['course_id'],
                session['user_id'], session['username'],
                f"حذف ملف مقرر فصل دراسي بواسطة المشرف: {course['name'] if course else row['course_id']}")
    db.commit()
    flash('تم حذف ملف المقرر ', 'success')
    return redirect(url_for('teacher_pages.super_admin_course_content_list'))


@bp.route('/super-admin/course-content/course/<int:course_id>/period/<int:period_id>/delete',
          methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_course_period_purge(course_id, period_id):
    """حذف محتوى فصل دراسي كامل (المقرر + النماذج) — المادة نفسها تبقى.

    تُحذف كل ملفات وسجلات ذلك الفصل الدراسي فقط — المادة نفسها تبقى.
    """
    db = get_db()
    course = db.execute(
        'SELECT id, name FROM courses WHERE id = ?', (course_id,)
    ).fetchone()
    period = db.execute(
        'SELECT label FROM academic_periods WHERE id = ?', (period_id,)
    ).fetchone()
    if not course or not period:
        flash('المقرر أو الفصل الدراسي غير موجود', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))

    removed_files = 0
    for old in db.execute(
            '''SELECT * FROM course_files
               WHERE course_id = ? AND file_type = 'syllabus'
                 AND academic_period_id = ?''',
            (course_id, period_id)).fetchall():
        db.execute('DELETE FROM course_files WHERE id = ?', (old['id'],))
        removed_files += 1

    removed_forms = 0
    sub_ids = [r['id'] for r in db.execute(
        '''SELECT id FROM course_content_submissions
           WHERE course_id = ? AND academic_period_id = ?''',
        (course_id, period_id)).fetchall()]
    for sid in sub_ids:
        sub = db.execute(
            'SELECT * FROM course_content_submissions WHERE id = ?', (sid,)
        ).fetchone()
        if sub and sub['filename']:
            db.execute(
                "DELETE FROM course_files WHERE submission_id = ? AND file_type = 'form'",
                (sid,)
            )
            removed_forms += 1
        db.execute('DELETE FROM course_content_submissions WHERE id = ?', (sid,))

    add_history(db, 'delete', 'course_syllabus', course_id, session['user_id'],
                session['username'],
                f"حذف محتوى الفصل الدراسي ({period['label']}) لمادة "
                f"{course['name']} بواسطة المشرف")
    db.commit()

    parts = []
    if removed_files:
        parts.append(f'{removed_files} ملف مقرر')
    if removed_forms:
        parts.append(f'{removed_forms} نموذج')
    summary = ' و'.join(parts) if parts else 'لا يوجد محتوى'
    flash(f'تم حذف محتوى "{period["label"]}" لمادة "{course["name"]}" '
          f'({summary}) بنجاح', 'success')
    return redirect(url_for('teacher_pages.super_admin_course_content_list'))


@bp.route('/super-admin/course-content/course/<int:course_id>/bulk-delete', methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_course_content_bulk_delete(course_id):
    """حذف العناصر المحددة من لوحة «إدارة» فصل دراسي (إزالة نهائية).

    file_ids: نسخ مقرر محددة.  submission_ids: تُفرَد من ملف PDF المرفق
    """
    db = get_db()
    course = db.execute(
        'SELECT id, name FROM courses WHERE id = ?', (course_id,)
    ).fetchone()
    if not course:
        flash('المقرر غير موجود', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))

    removed_files = removed_pdfs = 0
    for fid in request.form.getlist('file_ids'):
        try:
            fid = int(fid)
        except (TypeError, ValueError):
            continue
        row = db.execute(
            '''SELECT * FROM course_files
               WHERE id = ? AND course_id = ? AND file_type = 'syllabus' ''',
            (fid, course_id)).fetchone()
        if not row:
            continue
        db.execute('DELETE FROM course_files WHERE id = ?', (fid,))
        removed_files += 1

    for sid in request.form.getlist('submission_ids'):
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            continue
        sub = db.execute(
            '''SELECT * FROM course_content_submissions
               WHERE id = ? AND course_id = ?''',
            (sid, course_id)).fetchone()
        if not sub or not sub['filename']:
            continue
        db.execute('''UPDATE course_content_submissions
                      SET filename = '', original_filename = '', file_size = 0,
                          updated_at = CURRENT_TIMESTAMP WHERE id = ?''', (sid,))
        db.execute(
            "DELETE FROM course_files WHERE submission_id = ? AND file_type = 'form'",
            (sid,)
        )
        removed_pdfs += 1

    if not removed_files and not removed_pdfs:
        flash('لم يتم تحديد أي عنصر للحذف', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))

    add_history(db, 'delete', 'course_syllabus', course_id, session['user_id'],
                session['username'],
                f"حذف عناصر محددة من محتوى مادة {course['name']} بواسطة المشرف")
    db.commit()
    parts = []
    if removed_files:
        parts.append(f'{removed_files} ملف مقرر')
    if removed_pdfs:
        parts.append(f'{removed_pdfs} نموذج')
    flash(f"تم حذف {' و'.join(parts)} بنجاح", 'success')
    return redirect(url_for('teacher_pages.super_admin_course_content_list'))


@bp.route('/super-admin/course-content/<int:submission_id>/form/delete', methods=['POST'])
@login_required
@permission_required('course_content.view')
@csrf_required
def super_admin_course_content_form_delete(submission_id):
    """Detach the submitted form PDF from a submission."""
    db = get_db()
    submission = db.execute(
        'SELECT * FROM course_content_submissions WHERE id = ?', (submission_id,)
    ).fetchone()
    if not submission:
        flash('النموذج غير موجود', 'error')
        return redirect(url_for('teacher_pages.super_admin_course_content_list'))
    if submission['filename']:
        db.execute('''UPDATE course_content_submissions
                      SET filename = '', original_filename = '', file_size = 0,
                          updated_at = CURRENT_TIMESTAMP
                      WHERE id = ?''', (submission_id,))
        db.execute(
            "DELETE FROM course_files WHERE submission_id = ? AND file_type = 'form'",
            (submission_id,)
        )
        add_history(db, 'delete', 'course_content', submission_id,
                    session['user_id'], session['username'],
                    f"حذف ملف النموذج بواسطة المشرف — النموذج رقم {submission_id}")
        db.commit()
        flash('تم حذف ملف النموذج ', 'success')
    else:
        flash('لا يوجد ملف مرفق بهذا النموذج', 'error')
    return redirect(url_for('teacher_pages.super_admin_course_content_list'))


@bp.route('/super-admin/course-content/<int:submission_id>/file')
@login_required
@permission_required('course_content.view')
def super_admin_course_content_file(submission_id):
    return download_service.serve_course_content_file(get_db(), submission_id, download=request.args.get('download') == '1')


@bp.route('/course-content/<int:submission_id>/file')
@login_required
@permission_required('course_content.edit')
def teacher_course_content_file(submission_id):
    db = get_db()
    teacher = db.execute(
        'SELECT id FROM teachers WHERE user_id = ?', (session['user_id'],)
    ).fetchone()
    if not teacher:
        abort(404)
    row = db.execute(
        'SELECT id FROM course_content_submissions WHERE id = ? AND teacher_id = ?',
        (submission_id, teacher['id'])
    ).fetchone()
    if not row:
        abort(404)
    return download_service.serve_course_content_file(db, submission_id, download=request.args.get('download') == '1')


@bp.route('/course-content/<int:submission_id>/form')
@login_required
@permission_required('course_content.edit')
def teacher_course_content_form_view(submission_id):
    """Read-only view of the R&D-created course form for the assigned teacher."""
    db = get_db()
    teacher = db.execute(
        'SELECT id, name FROM teachers WHERE user_id = ?', (session['user_id'],)
    ).fetchone()
    if not teacher:
        abort(404)
    row = db.execute(
        'SELECT * FROM course_content_submissions WHERE id = ? AND teacher_id = ?',
        (submission_id, teacher['id'])
    ).fetchone()
    if not row or not row['course_id']:
        abort(404)
    curriculum = [dict(r) for r in db.execute(
        'SELECT * FROM course_content_curriculum WHERE submission_id = ? ORDER BY sort_order',
        (submission_id,)
    ).fetchall()]
    return render_template(
        'teachers/course_content_page.html',
        user=current_user(),
        submission=dict(row),
        page_mode='readonly',
        curriculum=curriculum,
        teacher_name=teacher['name'],
        page_title='نموذج المقرر',
        sidebar_active='course_content',
    )


@bp.route('/course-content/syllabus/upload', methods=['POST'])
@login_required
@permission_required('course_content.edit')
@csrf_required
def teacher_syllabus_upload():
    db = get_db()
    teacher = db.execute(
        'SELECT id, name FROM teachers WHERE user_id = ?', (session['user_id'],)
    ).fetchone()
    if not teacher:
        flash('لم يتم العثور على بيانات عضو هيئة التدريس', 'error')
        return redirect_back()

    course_id = request.form.get('course_id', type=int)
    if not course_id:
        flash('يرجى اختيار المقرر', 'error')
        return redirect_back()

    assigned = db.execute('''
        SELECT tt.course_id FROM timetable tt
        WHERE tt.teacher_id = ? AND tt.course_id = ? AND tt.deleted_at IS NULL
          AND (tt.version_id IS NULL OR tt.version_id IN
               (SELECT id FROM timetable_versions WHERE status = 'active'))
        LIMIT 1
    ''', (teacher['id'], course_id)).fetchone()
    if not assigned:
        flash('المقرر غير مسند إليك', 'error')
        return redirect_back()

    saved = _save_course_file(request.files.get('file'), course_id, 'syllabus')
    if isinstance(saved, str):
        flash(saved, 'error')
        return redirect_back()
    filename, original_filename, file_size = saved
    if not filename:
        flash('يرجى رفع ملف المنهج بصيغة PDF', 'error')
        return redirect_back()

    existing = db.execute(
        "SELECT * FROM course_files WHERE course_id = ? "
        "AND file_type = 'syllabus' ORDER BY id DESC LIMIT 1",
        (course_id,)
    ).fetchone()
    if existing:
        db.execute('''UPDATE course_files
                      SET filename = ?, original_filename = ?, file_size = ?,
                          status = 'approved', uploaded_by = ?,
                          updated_at = CURRENT_TIMESTAMP
                      WHERE id = ?''',
                   (filename, original_filename, file_size, session['user_id'],
                    existing['id']))
    else:
        db.execute('''INSERT INTO course_files
                      (course_id, file_type, filename, original_filename, file_size,
                       uploaded_by, teacher_id, status)
                      VALUES (?, 'syllabus', ?, ?, ?, ?, ?, 'approved')''',
                   (course_id, filename, original_filename, file_size,
                    session['user_id'], teacher['id']))
    db.commit()
    flash(f'تم رفع/استبدال ملف المنهج لمقرر "{course_id}" وسيظهر في الجدول مباشرة', 'success')
    return redirect_back()


@bp.route('/course-content/syllabus/<int:tf_id>/delete', methods=['POST'])
@login_required
@permission_required('course_content.edit')
@csrf_required
def teacher_syllabus_delete(tf_id):
    db = get_db()
    teacher = db.execute(
        'SELECT id FROM teachers WHERE user_id = ?', (session['user_id'],)
    ).fetchone()
    if not teacher:
        abort(404)
    row = db.execute(
        "SELECT * FROM course_files WHERE id = ? AND teacher_id = ? "
        "AND file_type = 'syllabus'",
        (tf_id, teacher['id'])
    ).fetchone()
    if not row:
        flash('الملف غير موجود', 'error')
        return redirect_back()
    _remove_uploaded_file(row['filename'])
    db.execute('DELETE FROM course_files WHERE id = ?', (tf_id,))
    db.commit()
    flash('تم حذف الملف', 'success')
    return redirect_back()
