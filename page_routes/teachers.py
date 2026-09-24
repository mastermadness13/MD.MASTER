from flask import (Blueprint, session, request, render_template,
                   redirect, url_for, flash, jsonify, current_app, abort)
from utils.redirects import redirect_back
from datetime import date
import os
import sqlite3
import uuid

from flask_db import get_db
from core.constants import INITIAL_CODE_EXPIRY_DAYS
from core.exceptions import ProtectedAccountError
from database.history import add_history
from security import csrf_required, login_required, permission_required
from security import current_user
from utils.format import paginate
from services import teacher_service
from services import course_service
from services import hod_resolution
from services.search import build_teacher_search, highlight_text
from services import faculty_performance_service as fps

_PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
_PHOTO_MAX_BYTES = 4 * 1024 * 1024

# Roles an admin may add (via the teacher form, into user_roles) on top of the
# teacher's landing 'teacher' role.  'teacher' is the implicit landing role.
_GRANTABLE_ROLES = ('head_of_department', 'exam', 'faculty_affairs', 'research_development', 'dean')


def _safe_extra_roles(form) -> list:
    """Parse the submitted additional-role checkboxes into a validated list."""
    VALID = set(_GRANTABLE_ROLES)
    return [r for r in form.getlist('extra_roles[]') if r in VALID]


_POSITION_ROLE_MAP = {
    'رئيس قسم': 'head_of_department',
    'رئيس القسم': 'head_of_department',
    'قسم البحث والتطوير': 'research_development',
    'رئيس قسم البحث والتطوير': 'research_development',
    'قسم الإدارة والامتحانات': 'exam',
    'رئيس قسم الامتحانات': 'exam',
    'رئيس قسم الدراسة والامتحانات': 'exam',
    'مكتب إدارة أعضاء هيئة التدريس': 'faculty_affairs',
    'مدير مكتب أعضاء هيئة التدريس': 'faculty_affairs',
    'العميد': 'dean',
}


def _roles_from_position(position: str) -> set:
    """Roles derived from the administrative assignment (نوع التكليف)."""
    role = _POSITION_ROLE_MAP.get((position or '').strip(), '')
    return {role} if role else set()


_DEFAULT_ADMIN_TASKS = [
    'عضو تدريس',
    'رئيس قسم',
    'رئيس قسم البحث والتطوير',
    'مدير مكتب أعضاء هيئة التدريس',
    'مدير مكتب الشؤون العلمية',
    'منسق القاعات',
    'رئيس قسم الدراسة والامتحانات',
    'مكتب إدارة أعضاء هيئة التدريس',
    'عميد الكلية',
    'مدير مكتب الجودة',
    'مدير مكتب الدراسة العالية',
    'رئيس القسم العلمي',
    'رئيس قسم الشؤون الفنية والمعامل',
    'رئيس قسم البحث والتطوير والمناهج',
    'رئيس قسم التدريب الميداني',
    'رئيس قسم الدبلوم المهني',
    'منسق الشعبة العلمية',
    'منسق الجودة بالقسم',
    'منسق الدراسة العالية بالقسم',
    'منسق المواد العامة بالقسم العلمي',
    'منسق تدريب ميداني',
    'عضو تحرير مجلة علمية',
]


def _admin_task_names(db) -> list:
    """Merged administrative assignment-type names for the 'نوع التكليف' select.

    The current types (``admin_assignment_types``) come first, then the legacy
    types from the old system (``_POSITION_ROLE_MAP`` keys) are appended.
    Nothing is replaced or deleted — previous + current are combined and
    duplicates are skipped. Not every type grants a system role (see
    ``_POSITION_ROLE_MAP``); all are recorded and shown in the reports.
    """
    names = list(_DEFAULT_ADMIN_TASKS)
    try:
        names = [t['name'] for t in fps.get_select_data(db)['admin_task_types']]
    except Exception:
        return names
    seen = set(names)
    for legacy in _POSITION_ROLE_MAP:
        if legacy not in seen:
            names.append(legacy)
            seen.add(legacy)
    return names


def _can_hod_view_teacher(db, teacher_id) -> bool:
    """True when the current head_of_department may view the given teacher
    (the teacher is a member of the department the HOD actually heads)."""
    dept_id = session.get('hod_department_id')
    if not dept_id:
        return False
    return bool(db.execute(
        'SELECT 1 FROM teacher_departments '
        'WHERE teacher_id = ? AND department_id = ? LIMIT 1',
        (teacher_id, dept_id),
    ).fetchone())


def _headship_occupant(db, department_id, exclude_teacher_id=None,
                       exclude_user_id=None):
    """The current head of a department, unless it is the member being edited."""
    if not department_id:
        return None                                                                                        
    hod = hod_resolution.get_current_hod(db, department_id)
    if not hod:
        return None
    if exclude_teacher_id is not None and hod.get('teacher_id') == exclude_teacher_id:
        return None
    if exclude_user_id is not None and hod.get('user_id') == exclude_user_id:
        return None
    return hod


def _validate_headship(db, hod_department_id, exclude_teacher_id=None,
                       exclude_user_id=None, confirmed=False):
    """Validate the headed department chosen for a 'رئيس قسم' task.

    Returns ``(error, occupant_name)``.  When the department already has a
    head (other than the current member) and ``confirmed`` is False, an
    actionable message asks for a confirmation instead of hard-blocking.
    """
    if not hod_department_id:
        return 'يرجى اختيار القسم العلمي الذي يرأسه', None
    row = db.execute(
        'SELECT type FROM departments WHERE id = ?', (hod_department_id,)
    ).fetchone()
    if not row or row['type'] != 'academic':
        return 'القسم المرؤوس يجب أن يكون قسماً كلياً', None
    occupant = _headship_occupant(db, hod_department_id,
                                  exclude_teacher_id=exclude_teacher_id,
                                  exclude_user_id=exclude_user_id)
    if occupant:
        if not confirmed:
            return (f'القسم يترأسه حالياً: {occupant["name"]} — '
                    f'فعّل خيار "تأكيد استبدال الرئيس" للمتابعة', occupant['name'])
        return None, occupant['name']
    return None, None


def _clear_previous_head(db, department_id, exclude_teacher_id=None):
    """Release the department from its previous head(s) during a replacement.

    Deliberately leaves the change uncommitted: it is committed together with
    the teacher create/update so a later validation failure never leaves the
    department without a head.
    """
    if exclude_teacher_id is not None:
        db.execute(
            'UPDATE teachers SET hod_department_id = NULL '
            'WHERE hod_department_id = ? AND deleted_at IS NULL AND id != ?',
            (department_id, exclude_teacher_id),
        )
    else:
        db.execute(
            'UPDATE teachers SET hod_department_id = NULL '
            'WHERE hod_department_id = ? AND deleted_at IS NULL',
            (department_id,),
        )


def _store_teacher_photo(teacher_id: int, file_storage) -> str:
    """Persist an uploaded profile photo under ``uploads/photos/``.

    Returns the stored relative path (``photos/<name>``) suitable for
    ``uploads.uploaded_file``.  Raises ``ValueError`` with a user-facing
    message when the file type or size is not acceptable.
    """
    ext = os.path.splitext(file_storage.filename or '')[1].lower()
    if ext not in _PHOTO_EXTENSIONS:
        raise ValueError('صيغة الصورة غير مدعومة (المسموح: JPG، PNG، WEBP)')
    data = file_storage.read()
    if len(data) > _PHOTO_MAX_BYTES:
        raise ValueError('حجم الصورة يتجاوز الحد الأقصى (4 ميجابايت)')
    if not data:
        raise ValueError('الملف المرفوع فارغ')
    photos_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'photos')
    os.makedirs(photos_dir, exist_ok=True)
    name = f'teacher_{teacher_id}_{uuid.uuid4().hex[:8]}{ext}'
    with open(os.path.join(photos_dir, name), 'wb') as fh:
        fh.write(data)
    return f'photos/{name}'


def _delete_teacher_photo(photo_filename: str) -> None:
    """Best-effort removal of a stored profile photo."""
    if not photo_filename:
        return
    path = os.path.join(current_app.config['UPLOAD_FOLDER'],
                        photo_filename.replace('/', os.sep))
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _safe_fk(value):
    if not value:
        return None
    try:
        v = int(value)
        return v
    except (TypeError, ValueError):
        return None


def _ensure_lookup(db, table, name_ar):
    """Return the id of an existing dropdown row by its Arabic name, creating
    one on the spot when the name is new (the English column is mirrored so
    the NOT NULL constraint holds)."""
    name_ar = (name_ar or '').strip()
    if not name_ar:
        return None
    row = db.execute(
        f'SELECT id FROM {table} WHERE name_ar = ?', (name_ar,)
    ).fetchone()
    if row:
        return row['id']
    cur = db.execute(
        f'INSERT INTO {table} (name_ar, name_en) VALUES (?, ?)',
        (name_ar, name_ar),
    )
    return cur.lastrowid


def _ensure_specialization(db, name_ar, department_id):
    """Return a specialization id, creating one under the chosen department."""
    name_ar = (name_ar or '').strip()
    if not name_ar or not department_id:
        return None
    row = db.execute(
        'SELECT id FROM specializations WHERE department_id = ? AND name = ?',
        (department_id, name_ar),
    ).fetchone()
    if row:
        return row['id']
    cur = db.execute(
        'INSERT INTO specializations (department_id, name) VALUES (?, ?)',
        (department_id, name_ar),
    )
    return cur.lastrowid


def _ensure_admin_task(db, name_ar):
    """Register a new administrative-assignment type when a custom one is typed."""
    name_ar = (name_ar or '').strip()
    if not name_ar:
        return None
    row = db.execute(
        'SELECT id FROM admin_assignment_types WHERE name = ?', (name_ar,)
    ).fetchone()
    if row:
        return row['id']
    cur = db.execute(
        'INSERT INTO admin_assignment_types (name, default_hours, is_active, sort_order) '
        'VALUES (?, 0, 1, 0)',
        (name_ar,),
    )
    return cur.lastrowid


def _resolve_custom_lookups(db, form, department_id=None):
    """Apply typed-in custom dropdown values to the lookup tables.

    Each custom field (``custom_<name>``) creates/reuses the matching row in
    the reference table and stores its id in the form, so a free-text value
    behaves exactly like a pre-existing option everywhere else in the system.
    """
    custom_rank = _ensure_lookup(db, 'academic_ranks', form.get('custom_rank_id'))
    if custom_rank:
        form['rank_id'] = custom_rank
    custom_qual = _ensure_lookup(db, 'qualifications', form.get('custom_qualification_id'))
    if custom_qual:
        form['qualification_id'] = custom_qual
    custom_class = _ensure_lookup(db, 'classifications', form.get('custom_classification_id'))
    if custom_class:
        form['classification_id'] = custom_class
    custom_spec = _ensure_specialization(db, form.get('custom_specialization_id'),
                                         department_id)
    if custom_spec:
        form['specialization_id'] = custom_spec
    elif (form.get('custom_specialization_id') or '').strip():
        form['specialization'] = form.get('custom_specialization_id').strip()
        form['specialization_id'] = None
    custom_pos = (form.get('custom_position') or '').strip()
    if custom_pos:
        _ensure_admin_task(db, custom_pos)
        form['position'] = custom_pos


def _parse_whole_hours(value):
    """Parse research/teaching hours as a whole number only (no decimals).

    Returns 0 for empty, non-numeric, or fractional values so half-hours like
    «2.5» are never silently accepted or truncated.
    """
    s = (value or '').strip()
    if not s:
        return 0
    if not s.isdigit():
        return 0
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def _validate_specialization(db, form, department_ids=None):
    """Ensure a chosen specialization belongs to one of the linked departments.

    When no departments are selected, any specialization is allowed (department
    membership is optional for creation).  ``department_ids`` may be a list of
    ints or a list of strings — both are coerced to strings for comparison.
    """
    spec_id = form.get('specialization_id')
    if not spec_id:
        return None
    if not department_ids:
        return None
    row = db.execute(
        'SELECT department_id FROM specializations WHERE id = ?', (spec_id,)
    ).fetchone()
    if row and str(row['department_id']) not in [str(d) for d in department_ids]:
        return 'التخصص المحدد لا ينتمي إلى أي من الأقسام المرتبطة'
    return None


def _reconcile_primary_dept(db, teacher_id):
    """Sync ``teachers.department_id`` with the first linked department.

    ``teacher_departments`` is the source of truth.  ``department_id`` is kept
    as a derived / legacy field for backward compatibility.
    """
    row = db.execute(
        'SELECT department_id FROM teacher_departments '
        'WHERE teacher_id = ? ORDER BY department_id LIMIT 1',
        (teacher_id,),
    ).fetchone()
    primary = row['department_id'] if row else None
    db.execute(
        'UPDATE teachers SET department_id = ? WHERE id = ?',
        (primary, teacher_id),
    )

bp = Blueprint('teachers', __name__, url_prefix='/teachers')


def _full_teacher_list():
    query, params, _dept_filter = build_teacher_search('', '', None, 1)
    db = get_db()
    return [dict(r) for r in db.execute(query, params).fetchall()]


@bp.route('')
@login_required
@permission_required('teachers.view')
def teachers_list():
    role = session.get('role', '')
    user_data = current_user()
    search = request.args.get('search', '').strip()
    dept_filter = request.args.get('department_id', '')
    page = request.args.get('page', 1, type=int)

    user_dept_id = None
    if role == 'head_of_department' and user_data:
        user_dept_id = session.get('hod_department_id')

    query, params, dept_filter = build_teacher_search(
        search, dept_filter, user_dept_id, page)
    rows, total, page, per_page = paginate(query, params, page)

    db = get_db()

    # Many-to-many departments per teacher (primary + memberships),
    # batch-loaded for the current page only.
    page_ids = [r['id'] for r in rows]
    dept_map = {}
    if page_ids:
        ph = ','.join('?' * len(page_ids))
        for r in db.execute(
            'SELECT td.teacher_id AS tid, d.name AS dname '
            'FROM teacher_departments td '
            'JOIN departments d ON td.department_id = d.id '
            f'WHERE td.teacher_id IN ({ph}) '
            "AND d.deleted_at IS NULL ORDER BY d.name",
            page_ids,
        ).fetchall():
            dept_map.setdefault(r['tid'], []).append(r['dname'])
    primary_names = {}
    if page_ids:
        ph = ','.join('?' * len(page_ids))
        for r in db.execute(
            'SELECT t.id AS tid, d.name AS dname '
            'FROM teachers t LEFT JOIN departments d ON t.department_id = d.id '
            f'WHERE t.id IN ({ph})',
            page_ids,
        ).fetchall():
            if r['dname']:
                primary_names[r['tid']] = r['dname']
    for row in rows:
        names = list(dept_map.get(row['id'], []))
        pname = primary_names.get(row['id'])
        if pname and pname not in names:
            names.insert(0, pname)
        elif not names and pname:
            names = [pname]
        row['dept_names'] = names

    departments = [dict(r) for r in db.execute(
        'SELECT * FROM departments WHERE hidden = 0 AND deleted_at IS NULL ORDER BY name'
    ).fetchall()]

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return render_template('teachers/list_table.html',
                              teachers=rows, total=total, page=page,
                              per_page=per_page, search=search,
                              department_id=dept_filter,
                              departments=departments, user=user_data,
                              highlight=highlight_text)

    return render_template('teachers/list.html', teachers=rows, total=total, page=page,
                          per_page=per_page, search=search, department_id=dept_filter,
                          departments=departments,
                          assign_default_dept=session.get('hod_department_id')
                          or session.get('department_id'),
                          user=user_data, print_teachers=_full_teacher_list())


@bp.route('/api/courses')
@login_required
def api_courses():
    db = get_db()
    dept_id = request.args.get('department_id', type=int)
    if not dept_id:
        return jsonify([])
    rows = db.execute('''
        SELECT DISTINCT c.id, c.code, c.name
        FROM courses c
        LEFT JOIN course_departments cd ON c.id = cd.course_id
        WHERE (cd.department_id = ? OR c.department_id = ?)
          AND c.deleted_at IS NULL
        ORDER BY c.name
    ''', (dept_id, dept_id)).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('teachers.manage')
@csrf_required
def teachers_create():
    db = get_db()
    departments, qualifications, ranks, classifications, _courses, specializations = teacher_service.get_form_lookups(db)
    admin_tasks = _admin_task_names(db)
    department_hods = hod_resolution.department_hod_map(db)
    confirmed_replace = request.form.get('confirm_replace_hod') == '1' if request.method == 'POST' else False
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        department_ids = [_safe_fk(v) for v in request.form.getlist('department_ids[]') if _safe_fk(v)]
        department_id = department_ids[0] if department_ids else None
        specialization_id = _safe_fk(request.form.get('specialization_id'))
        extra_roles = _safe_extra_roles(request.form)
        position = request.form.get('position', '').strip()
        hod_department_id = _safe_fk(request.form.get('hod_department_id'))
        effective_roles = set(extra_roles) | _roles_from_position(position)
        if 'head_of_department' not in effective_roles:
            hod_department_id = None
        form = {
            'name': name,
            'username': request.form.get('username', '').strip(),
            'password': request.form.get('password', ''),
            'email': request.form.get('email', '').strip(),
            'phone': request.form.get('phone', '').strip(),
            'department_id': department_id,
            'department_ids': [str(d) for d in department_ids],
            'academic_number': request.form.get('academic_number', '').strip(),
            'qualification_id': _safe_fk(request.form.get('qualification_id')),
            'rank_id': _safe_fk(request.form.get('rank_id')),
            'classification_id': _safe_fk(request.form.get('classification_id')),
            'national_id': request.form.get('national_id', '').strip(),
            'contract_date': request.form.get('contract_date', '').strip(),
            'tasks': request.form.get('tasks', '').strip(),
            'position': position,
            'specialization': request.form.get('specialization', '').strip(),
            'specialization_id': specialization_id,
            'semester': request.form.get('semester', '').strip(),
            'first_lecture_date': request.form.get('first_lecture_date', '').strip(),
            'work_start_date': request.form.get('work_start_date', '').strip(),
            'general_notes': request.form.get('general_notes', '').strip(),
            'extra_roles': extra_roles,
            'hod_department_id': hod_department_id,
        }
        for _ck in ('custom_rank_id', 'custom_qualification_id', 'custom_classification_id',
                    'custom_specialization_id', 'custom_position'):
            form[_ck] = request.form.get(_ck, '').strip()
        _resolve_custom_lookups(db, form, department_id)
        if not name:
            return render_template('teachers/create.html',
                                  departments=departments, qualifications=qualifications,
                                  ranks=ranks, classifications=classifications,
                                  specializations=specializations,
                                  department_hods=department_hods,
                                  confirm_replace=confirmed_replace,
form=form, form_error='الاسم مطلوب',
                                   grantable_roles=_GRANTABLE_ROLES,
                                   admin_tasks=admin_tasks,
                                   user=current_user())
        if not form['username']:
            return render_template('teachers/create.html',
                                  departments=departments, qualifications=qualifications,
                                  ranks=ranks, classifications=classifications,
                                  specializations=specializations,
                                  department_hods=department_hods,
                                  confirm_replace=confirmed_replace, form=form,
                                  form_error='اسم المستخدم مطلوب',
                                  grantable_roles=_GRANTABLE_ROLES,
                                  admin_tasks=admin_tasks, user=current_user())
        if len(form['password']) < 6:
            return render_template('teachers/create.html',
                                  departments=departments, qualifications=qualifications,
                                  ranks=ranks, classifications=classifications,
                                  specializations=specializations,
                                  department_hods=department_hods,
                                  confirm_replace=confirmed_replace, form=form,
                                  form_error='كلمة المرور يجب أن تكون 6 أحرف على الأقل',
                                  grantable_roles=_GRANTABLE_ROLES,
                                  admin_tasks=admin_tasks, user=current_user())
        if 'head_of_department' in effective_roles:
            headship_error, _conflict_name = _validate_headship(
                db, hod_department_id,
                exclude_user_id=session.get('user_id'),
                confirmed=confirmed_replace,
            )
            if headship_error:
                return render_template('teachers/create.html',
                                      departments=departments, qualifications=qualifications,
                                      ranks=ranks, classifications=classifications,
                                      specializations=specializations,
                                      department_hods=department_hods,
                                      confirm_replace=confirmed_replace,
form=form, form_error=headship_error,
                                       grantable_roles=_GRANTABLE_ROLES,
                                       admin_tasks=admin_tasks,
                                       user=current_user())
            if confirmed_replace:
                _clear_previous_head(db, hod_department_id)
        spec_error = _validate_specialization(db, form, department_ids)
        if spec_error:
            return render_template('teachers/create.html',
                                  departments=departments, qualifications=qualifications,
                                  ranks=ranks, classifications=classifications,
                                  specializations=specializations,
                                  department_hods=department_hods,
                                  confirm_replace=confirmed_replace,
form=form, form_error=spec_error,
                                   grantable_roles=_GRANTABLE_ROLES,
                                   admin_tasks=admin_tasks,
                                   user=current_user())
        try:
            creds = teacher_service.create_teacher(db, form, department_ids=department_ids,
                                                   additional_roles=sorted(effective_roles),
                                                   initial_password=form['password'])
        except ValueError as exc:
            message = str(exc)
            if 'academic_number' in message:
                form_error = 'الرقم الكلية مستخدم مسبقاً'
            elif 'too short' in message:
                form_error = 'نيك نيم الدخول قصير جداً — حرفان على الأقل'
            elif 'Username' in message:
                form_error = 'نيك نيم الدخول مستخدم مسبقاً — اختر نيك نيم آخر'
            else:
                form_error = message
            return render_template('teachers/create.html',
                                  departments=departments, qualifications=qualifications,
                                  ranks=ranks, classifications=classifications,
                                  specializations=specializations,
                                  department_hods=department_hods,
                                  confirm_replace=confirmed_replace,
                                  form=form, form_error=form_error,
                                   grantable_roles=_GRANTABLE_ROLES,
                                   admin_tasks=admin_tasks,
                                   user=current_user())
        if form.get('position') == 'مشرف' and request.form.get('supervisor_admin_dept', '').strip():
            db.execute(
                'UPDATE users SET supervisor_admin_dept = ? WHERE id = (SELECT user_id FROM teachers WHERE id = ?)',
                (request.form.get('supervisor_admin_dept').strip(), creds['id']),
            )
            db.commit()
        flash(
            f'تم إضافة عضو هيئة التدريس — نيك نيم: {creds["username"]} — '
            f'رمز الدخول المؤقت: {creds["password"]} (أُرسل أيضاً إلى بريده، صالح {INITIAL_CODE_EXPIRY_DAYS} أيام)',
            'success',
        )
        return redirect(url_for('teachers.teachers_list'))
    return render_template('teachers/create.html',
                          departments=departments, qualifications=qualifications,
                          ranks=ranks, classifications=classifications,
                          specializations=specializations,
                          department_hods=department_hods,
form={}, form_error=None,
                           grantable_roles=_GRANTABLE_ROLES,
                           admin_tasks=admin_tasks,
                           user=current_user())


@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('teachers.manage')
@csrf_required
def teachers_edit(id):
    db = get_db()
    t = teacher_service.get_teacher(db, id)
    if not t:
        flash('عضو هيئة التدريس غير موجود', 'error')
        return redirect(url_for('teachers.teachers_list'))
    departments, qualifications, ranks, classifications, _courses, specializations = teacher_service.get_form_lookups(db)
    admin_tasks = _admin_task_names(db)
    department_hods = hod_resolution.department_hod_map(db)
    confirmed_replace = request.form.get('confirm_replace_hod') == '1' if request.method == 'POST' else False
    teacher_dept_rows = db.execute(
        'SELECT department_id FROM teacher_departments WHERE teacher_id = ?', (id,)
    ).fetchall()
    teacher_dept_ids = [r['department_id'] for r in teacher_dept_rows]
    # الساعات البحثية — الأنواع الستة الثابتة + القيم المحفوظة للفصل الدراسي النشط
    edit_research_types = fps.get_research_types(db)
    edit_research = fps.get_research_activities_for_semester(db, id)
    # التكليف الإداري — تاريخ التكليف من faculty_admin_assignments
    active_sem = fps.get_active_semester(db)
    _admin_repo = fps._repo(db)
    _existing_pos = _admin_repo.get_single_admin_assignment(
        id, t['position'] or '', active_sem['academic_year'], active_sem['semester']) if t['position'] else None
    assignment_date = _existing_pos['assignment_date'] if _existing_pos else ''
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        department_ids = [_safe_fk(v) for v in request.form.getlist('department_ids[]') if _safe_fk(v)]
        department_id = department_ids[0] if department_ids else None
        specialization_id = _safe_fk(request.form.get('specialization_id'))
        extra_roles = _safe_extra_roles(request.form)
        position = request.form.get('position', '').strip()
        hod_department_id = _safe_fk(request.form.get('hod_department_id'))
        effective_roles = set(extra_roles) | _roles_from_position(position)
        if 'head_of_department' not in effective_roles:
            hod_department_id = None
        form = {
            'name': name,
            'email': request.form.get('email', '').strip(),
            'phone': request.form.get('phone', '').strip(),
            'department_id': department_id,
            'academic_number': request.form.get('academic_number', '').strip(),
            'qualification_id': _safe_fk(request.form.get('qualification_id')) or t['qualification_id'],
            'rank_id': _safe_fk(request.form.get('rank_id')) or t['rank_id'],
            'classification_id': _safe_fk(request.form.get('classification_id')) or t['classification_id'],
            'national_id': request.form.get('national_id', '').strip(),
            'contract_date': request.form.get('contract_date', '').strip(),
            'tasks': request.form.get('tasks', '').strip(),
            'specialization': request.form.get('specialization', '').strip(),
            'specialization_id': specialization_id,
            'position': position,
            'first_lecture_date': request.form.get('first_lecture_date', '').strip(),
            'work_start_date': request.form.get('work_start_date', '').strip(),
            'general_notes': request.form.get('general_notes', '').strip(),
            'extra_roles': extra_roles,
            'hod_department_id': hod_department_id,
        }
        for _ck in ('custom_rank_id', 'custom_qualification_id', 'custom_classification_id',
                    'custom_specialization_id', 'custom_position'):
            form[_ck] = request.form.get(_ck, '').strip()
        _resolve_custom_lookups(db, form, department_id)
        # Profile photo: replace / remove while keeping the previous file on
        # validation failures so nothing is lost.
        photo_filename = t['photo_filename']
        photo_error = None
        if request.form.get('remove_photo'):
            _delete_teacher_photo(photo_filename)
            photo_filename = None
        uploaded_photo = request.files.get('photo')
        if uploaded_photo is not None and uploaded_photo.filename:
            try:
                stored = _store_teacher_photo(id, uploaded_photo)
                _delete_teacher_photo(photo_filename)
                photo_filename = stored
            except ValueError as exc:
                photo_error = str(exc)
        form['photo_filename'] = photo_filename
        if photo_error:
            return render_template('teachers/edit.html',
                                  teacher=form,
                                  teacher_id=id,
                                  teacher_dept_ids=[did for did in department_ids if did],
                                  departments=departments, qualifications=qualifications,
                                  ranks=ranks, classifications=classifications,
                                  specializations=specializations,
                                  teacher_course_ids=[],
                                  department_hods=department_hods,
                                  confirm_replace=confirmed_replace,
form_error=photo_error,
                                   grantable_roles=_GRANTABLE_ROLES,
                                   extra_roles=form.get('extra_roles', []),
                                   research_types=edit_research_types,
                                   research=edit_research,
                                   assignment_date=assignment_date,
                                   admin_tasks=admin_tasks,
                                   user=current_user())
        if not name:
            return render_template('teachers/edit.html',
                                  teacher=form,
                                  teacher_id=id,
                                  teacher_dept_ids=[did for did in department_ids if did],
                                  departments=departments, qualifications=qualifications,
                                  ranks=ranks, classifications=classifications,
                                  specializations=specializations,
                                  teacher_course_ids=[],
                                  department_hods=department_hods,
                                  confirm_replace=confirmed_replace,
form_error='الاسم مطلوب',
                                   grantable_roles=_GRANTABLE_ROLES,
                                   extra_roles=form.get('extra_roles', []),
                                   research_types=edit_research_types,
                                   research=edit_research,
                                   assignment_date=assignment_date,
                                   admin_tasks=admin_tasks,
                                   user=current_user())
        if 'head_of_department' in effective_roles:
            headship_error, _conflict_name = _validate_headship(
                db, hod_department_id,
                exclude_teacher_id=id,
                exclude_user_id=session.get('user_id'),
                confirmed=confirmed_replace,
            )
            if headship_error:
                return render_template('teachers/edit.html',
                                      teacher=form,
                                      teacher_id=id,
                                      teacher_dept_ids=[did for did in department_ids if did],
                                      departments=departments, qualifications=qualifications,
                                      ranks=ranks, classifications=classifications,
                                      specializations=specializations,
                                      teacher_course_ids=[],
                                      department_hods=department_hods,
                                      confirm_replace=confirmed_replace,
form_error=headship_error,
                                       grantable_roles=_GRANTABLE_ROLES,
                                       extra_roles=form.get('extra_roles', []),
                                       research_types=edit_research_types,
                                       research=edit_research,
                                       assignment_date=assignment_date,
                                       admin_tasks=admin_tasks,
                                       user=current_user())
            if confirmed_replace:
                _clear_previous_head(db, hod_department_id, exclude_teacher_id=id)
        spec_error = _validate_specialization(db, form, department_ids)
        if spec_error:
            return render_template('teachers/edit.html',
                                  teacher=form,
                                  teacher_id=id,
                                  teacher_dept_ids=[did for did in department_ids if did],
                                  departments=departments, qualifications=qualifications,
                                  ranks=ranks, classifications=classifications,
                                  specializations=specializations,
                                  teacher_course_ids=[],
                                  department_hods=department_hods,
                                  confirm_replace=confirmed_replace,
form_error=spec_error,
                                   grantable_roles=_GRANTABLE_ROLES,
                                   extra_roles=form.get('extra_roles', []),
                                   research_types=edit_research_types,
                                   research=edit_research,
                                   assignment_date=assignment_date,
                                   admin_tasks=admin_tasks,
                                   user=current_user())
        an = form.get('academic_number', '').strip()
        if an:
            dup = db.execute(
                'SELECT id FROM teachers WHERE academic_number = ? AND id != ?',
                (an, id),
            ).fetchone()
            if dup:
                existing_an = t.get('academic_number', '')
                if an != existing_an:
                    return render_template('teachers/edit.html',
                                          teacher=form,
                                          teacher_id=id,
                                          teacher_dept_ids=[did for did in department_ids if did],
                                          departments=departments, qualifications=qualifications,
                                          ranks=ranks, classifications=classifications,
                                          specializations=specializations,
                                          teacher_course_ids=[],
                                          department_hods=department_hods,
                                          confirm_replace=confirmed_replace,
form_error='الرقم الكلية موجود مسبقاً لعضو آخر',
                                           grantable_roles=_GRANTABLE_ROLES,
                                           extra_roles=form.get('extra_roles', []),
                                           research_types=edit_research_types,
                                           research=edit_research,
                                           assignment_date=assignment_date,
                                           admin_tasks=admin_tasks,
                                           user=current_user())
        teacher_service.update_teacher(db, id, form)
        # The credentials update may have just created + linked a login account,
        # so re-read the link for the role/supervisor sync below.
        linked_user_id = t.get('user_id') or (teacher_service.get_teacher(db, id) or {}).get('user_id')

        db.execute('DELETE FROM teacher_departments WHERE teacher_id = ?', (id,))
        if department_ids:
            db.executemany(
                'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) VALUES (?, ?)',
                [(id, did) for did in department_ids],
            )
        _reconcile_primary_dept(db, id)
        db.commit()

        # التكليف الإداري — يُحفظ للفصل الدراسي النشط تلقائيًا (رابعاً: النموذج الوزاري)
        position_val = form.get('position', '').strip()
        assignment_date_val = request.form.get('assignment_date', '').strip()
        if position_val:
            _admin_repo.upsert_single_admin_assignment(
                id, position_val, assignment_date_val,
                active_sem['academic_year'], active_sem['semester'],
            )
        else:
            _admin_repo.delete_single_admin_assignment(
                id, t.get('position') or '', active_sem['academic_year'], active_sem['semester'],
            )
        db.commit()

        # الساعات البحثية — تُحفظ للفصل الدراسي النشط تلقائيًا (ثانياً: النموذج الوزاري)
        research_types = request.form.getlist('research_type[]')
        research_hours = request.form.getlist('research_hours[]')
        activities = []
        for i, atype in enumerate(research_types):
            atype = (atype or '').strip()
            raw = research_hours[i].strip() if i < len(research_hours) else ''
            hours = _parse_whole_hours(raw)
            if atype and hours > 0:
                activities.append({'activity_type': atype, 'hours': hours, 'notes': ''})
        active_sem = fps.get_active_semester(db)
        fps.save_research_data(
            db, id,
            active_sem['academic_year'],
            active_sem['semester'],
            activities,
        )

        if linked_user_id:
            teacher_service.set_teacher_extra_roles(db, id, sorted(effective_roles))
            if linked_user_id == session.get('user_id'):
                # تحديث نطاق رئيس القسم فوراً عندما يعدّل المستخدم بيانات نفسه
                session['hod_department_id'] = hod_department_id
                if 'head_of_department' not in effective_roles:
                    session.pop('hod_department_id', None)
        add_history(db, 'update', 'teacher', id, session['user_id'],
                    session['username'], f'تعديل بيانات عضو هيئة التدريس: {form["name"]}')
        supervisor_admin_dept = request.form.get('supervisor_admin_dept', '').strip()
        if form['position'] == 'مشرف' and supervisor_admin_dept and linked_user_id:
            db.execute(
                'UPDATE users SET supervisor_admin_dept = ? WHERE id = ?',
                (supervisor_admin_dept, linked_user_id),
            )
            db.commit()
        elif form['position'] != 'مشرف' and linked_user_id:
            db.execute(
                'UPDATE users SET supervisor_admin_dept = NULL WHERE id = ?',
                (linked_user_id,),
            )
            db.commit()
        flash('تم تحديث عضو هيئة التدريس', 'success')
        return redirect(url_for('teachers.teachers_list'))
    teacher_course_rows = db.execute(
        'SELECT course_id FROM timetable WHERE teacher_id = ? '
        'AND (version_id IS NULL OR version_id IN '
        '(SELECT id FROM timetable_versions WHERE status = \'active\'))', (id,)
    ).fetchall()
    teacher_course_ids = [r['course_id'] for r in teacher_course_rows]
    current_roles = teacher_service.get_teacher_granted_roles(db, id)
    extra_roles = [r for r in current_roles if r in _GRANTABLE_ROLES]
    return render_template('teachers/edit.html',
                          teacher=dict(t),
                          teacher_dept_ids=teacher_dept_ids,
                          departments=departments, qualifications=qualifications,
                          ranks=ranks, classifications=classifications,
                          specializations=specializations,
                          department_hods=department_hods,
                          confirm_replace=False,
                          teacher_course_ids=teacher_course_ids,
                          grantable_roles=_GRANTABLE_ROLES,
                          extra_roles=extra_roles,
research_types=edit_research_types,
                           research=edit_research,
                           assignment_date=assignment_date,
                           admin_tasks=admin_tasks,
                           user=current_user())


@bp.route('/reset-password/<int:id>', methods=['POST'])
@login_required
@permission_required('teachers.manage')
@csrf_required
def teachers_reset_password(id):
    db = get_db()
    t = teacher_service.get_teacher(db, id)
    if not t:
        flash('عضو هيئة التدريس غير موجود', 'error')
        return redirect(url_for('teachers.teachers_list'))
    new_password = teacher_service.reset_teacher_password(db, id)
    if new_password:
        add_history(db, 'reset_password', 'teacher', id, session['user_id'],
                    session['username'], f'إعادة تعيين كلمة مرور عضو هيئة التدريس: {t["name"]}')
        delivery_note = 'سلّمه للعضو يدوياً الآن؛ لا يُرسل عبر البريد تلقائياً'
        flash(
            f'تم إنشاء رمز دخول جديد لعضو هيئة التدريس: {t["name"]} — '
            f'اسم المستخدم: {t.get("username") or "—"} — رمز الاسترجاع المؤقت: {new_password} '
            f'({delivery_note}، صالح 60 دقيقة، وبحد أقصى 5 محاولات). '
            'لن يظهر الرمز مرة أخرى بعد إغلاق هذه الرسالة.',
            'recovery_code',
        )
    else:
        flash('تعذر توليد كلمة مرور جديدة — لا يوجد حساب مرتبط بهذا العضو', 'error')
    return redirect(url_for('teachers.teachers_edit', id=id))


@bp.route('/register-username/<int:id>', methods=['POST'])
@login_required
@permission_required('teachers.manage')
@csrf_required
def teachers_register_username(id):
    db = get_db()
    try:
        teacher_service.register_teacher_username(
            db, id, request.form.get('username', '')
        )
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('teachers.teachers_edit', id=id))
    except sqlite3.IntegrityError:
        db.rollback()
        flash('نيك نيم الدخول مستخدم مسبقاً', 'error')
        return redirect(url_for('teachers.teachers_edit', id=id))
    flash('تم تسجيل اسم الدخول وتثبيته نهائياً', 'success')
    return redirect(url_for('teachers.teachers_edit', id=id))


@bp.route('/<int:id>/teaching-record/<semester_code>')
@login_required
@permission_required('teachers.view')
def teaching_record_print(id, semester_code):
    """Print-preview page for one academic year of a teacher's teaching record.

    ``?print=1`` auto-triggers the browser print dialog on load.
    """
    db = get_db()
    teacher = teacher_service.get_teacher(db, id)
    if not teacher:
        flash('عضو هيئة التدريس غير موجود', 'error')
        return redirect(url_for('teachers.teachers_list'))

    rec = teacher_service.get_teaching_record(db, id)
    group = next((g for g in rec['years_data']
                  if (g.get('semester_code') or '') == semester_code), None)
    if not group:
        flash('لا توجد بيانات لهذه الفترة التدريسية', 'error')
        return redirect(url_for('teachers.teacher_detail', id=id))

    entries = [e for sem in group['semesters'] for e in sem['entries']]
    return render_template('teachers/teaching_record.html',
                           teacher=teacher, group=group, entries=entries,
                           print_flag=request.args.get('print') == '1',
                           user=current_user())


@bp.route('/<int:id>/teaching-record/<semester_code>/csv')
@login_required
@permission_required('teachers.view')
def teaching_record_csv(id, semester_code):
    """Download a teacher's teaching record for one period as CSV."""
    from io import StringIO
    import csv
    from flask import Response

    db = get_db()
    teacher = teacher_service.get_teacher(db, id)
    if not teacher:
        flash('عضو هيئة التدريس غير موجود', 'error')
        return redirect(url_for('teachers.teachers_list'))

    rec = teacher_service.get_teaching_record(db, id)
    group = next((g for g in rec['years_data']
                  if (g.get('semester_code') or '') == semester_code), None)
    if not group:
        flash('لا توجد بيانات لهذه الفترة التدريسية', 'error')
        return redirect(url_for('teachers.teacher_detail', id=id))

    type_map = {'theory': 'نظري', 'practical': 'عملي'}
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(['المقرر', 'رمز المقرر', 'النوع', 'المرحلة', 'القسم', 'الساعات', 'المحاضرات'])
    for sem in group['semesters']:
        for e in sem['entries']:
            writer.writerow([
                e.get('course_name', ''), e.get('course_code', ''),
                type_map.get(e.get('lecture_type', ''), e.get('lecture_type', '')),
                e.get('semester', ''), e.get('department_name', ''),
                e.get('hours', 0) if not e.get('missing_hours') or e.get('missing_hours') != e.get('entry_count') else '',
                e.get('entry_count', 0),
            ])
    resp = Response(buf.getvalue(), mimetype='text/csv; charset=utf-8')
    resp.headers['Content-Disposition'] = (
        f"attachment; filename=teaching-record-{id}-{semester_code}.csv")
    return resp


@bp.route('/<int:id>/teaching-record/report')
@login_required
@permission_required('teachers.view')
def teaching_record_report(id):
    """A4 report page for one teaching period.

    Target opened by the «عرض» button. Filtered by ``semester_code``
    (primary) and optionally ``semester`` (int). ``?print=1`` auto-prints.
    """
    db = get_db()
    teacher = teacher_service.get_teacher(db, id)
    if not teacher:
        flash('عضو هيئة التدريس غير موجود', 'error')
        return redirect(url_for('teachers.teachers_list'))

    semester_code = request.args.get('semester_code', '')
    semester_filter = request.args.get('semester', type=int)

    rec = teacher_service.get_teaching_record(db, id)
    years_data = rec.get('years_data') or []

    # Pick the requested period, or auto-find it from سجل التدريس if no
    # filter is provided (defaults to the most recent period available).
    group = next((g for g in years_data
                  if (g.get('semester_code') or '') == semester_code), None)

    if group is None and semester_filter and years_data:
        group = next((
            g for g in years_data
            if any((s or {}).get('number') == semester_filter
                   for s in g.get('semesters', []))), None)

    if group is None and not semester_code and not semester_filter and years_data:
        group = years_data[0]

    if group is None:
        flash('لا توجد بيانات لهذه الفترة التدريسية', 'error')
        return redirect(url_for('teachers.teacher_detail', id=id))

    entries = [e for sem in group['semesters'] for e in sem['entries']]
    return render_template('teachers/teaching_record_report.html',
                           teacher=teacher, group=group, entries=entries,
                           print_flag=request.args.get('print') == '1',
                           user=current_user())


@bp.route('/<int:id>')
@login_required
@permission_required('teachers.view')
def teacher_detail(id):
    db = get_db()
    if session.get('role') == 'head_of_department' and not _can_hod_view_teacher(db, id):
        abort(403)
    result = teacher_service.get_teacher_detail(db, id)
    if not result:
        flash('عضو هيئة التدريس غير موجود', 'error')
        return redirect(url_for('teachers.teachers_list'))
    teacher, courses, stats = result
    teaching = teacher_service.get_teaching_record(db, id)
    # حالة نماذج محتوى المقررات المرسلة من هذا المدرّس
    course_service.attach_course_related_data(db, courses, teacher_id=id)
    today_str = date.today().isoformat()

    # Default period for opening نموذج معدل الأداء from this page: the most
    # recent teaching period, else the active academic semester.
    perf_year, perf_semester = '', 1
    yd = teaching.get('years_data') or []
    if yd:
        first = yd[0]
        sems = first.get('semesters') or []
        perf_year = first.get('semester_code') or ''
        if sems and sems[0].get('number'):
            perf_semester = sems[0]['number']
    if not perf_year:
        perf_year = fps.get_active_semester(db)['academic_year']

    # Soft account state + extra roles + linked departments for the detail cards.
    active_row = db.execute(
        'SELECT is_active FROM users WHERE id = ?',
        (teacher['user_id'],),
    ).fetchone() if teacher.get('user_id') else None
    is_active = bool(active_row and active_row['is_active'])

    current_roles = teacher_service.get_teacher_granted_roles(db, id)
    extra_roles = [r for r in current_roles if r in _GRANTABLE_ROLES]

    dept_rows = db.execute(
        'SELECT d.id, d.name FROM teacher_departments td '
        'JOIN departments d ON d.id = td.department_id '
        'WHERE td.teacher_id = ? ORDER BY d.name', (id,)
    ).fetchall()
    teacher_depts = [{'id': r['id'], 'name': r['name']} for r in dept_rows]

    # تاريخ التكليف الإداري المحفوظ في faculty_admin_assignments (رابعاً: النموذج الوزاري)
    assignment_date = ''
    if teacher.get('position'):
        try:
            _active_sem = fps.get_active_semester(db)
        except Exception:
            _active_sem = {'academic_year': perf_year or '', 'semester': perf_semester}
        if not (_active_sem.get('academic_year') and _active_sem.get('semester')):
            _active_sem = {'academic_year': perf_year or '', 'semester': perf_semester}
        _existing_a = fps._repo(db).get_single_admin_assignment(
            id, teacher['position'], _active_sem['academic_year'], _active_sem['semester'])
        if _existing_a:
            assignment_date = _existing_a.get('assignment_date') or ''

    return render_template('teachers/detail.html', teacher=teacher, courses=courses,
                          stats=stats, teaching=teaching, today_str=today_str,
                          is_active=is_active, extra_roles=extra_roles,
                          teacher_depts=teacher_depts,
                          perf_year=perf_year, perf_semester=perf_semester,
                          assignment_date=assignment_date,
                          user=current_user())


# Standalone teaching record (select teacher → view record)
@bp.route('/teaching-record')
@login_required
@permission_required('teachers.view')
def teaching_record_standalone():
    db = get_db()
    teacher_id = request.args.get('teacher_id', type=int)
    period_filter = request.args.get('period', '').strip()

    departments = db.execute(
        'SELECT id, name FROM departments ORDER BY name'
    ).fetchall()

    teachers = []
    teaching = None
    teacher = None
    today_str = date.today().isoformat()

    if teacher_id:
        if session.get('role') == 'head_of_department' and not _can_hod_view_teacher(db, teacher_id):
            abort(403)
        teacher = db.execute(
            'SELECT id, name, academic_number, department_id FROM teachers WHERE id = ? AND deleted_at IS NULL',
            (teacher_id,),
        ).fetchone()
        if teacher:
            teaching = teacher_service.get_teaching_record(db, teacher_id, period_filter, None)
            teaching['period_filter'] = period_filter

    return render_template('teachers/teaching_record_standalone.html',
                          departments=departments,
                          teachers=teachers,
                          teacher=teacher,
                          teaching=teaching,
                          period_filter=period_filter,
                          today_str=today_str,
                          user=current_user())


@bp.route('/api/teachers-by-dept')
@login_required
def api_teachers_by_dept():
    db = get_db()
    dept_id = request.args.get('department_id', type=int)
    if not dept_id:
        return jsonify([])
    rows = db.execute(
        '''SELECT t.id, t.name, t.academic_number FROM teachers t
           WHERE t.deleted_at IS NULL AND EXISTS (
               SELECT 1 FROM teacher_departments td
               WHERE td.teacher_id = t.id AND td.department_id = ?
           )
           ORDER BY t.name''',
        (dept_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('teachers.manage')
@csrf_required
def teachers_delete(id):
    db = get_db()
    try:
        teacher_service.teacher_delete(db, id, lambda db: add_history(
            db, 'soft_delete', 'teacher', id, session['user_id'], session['username'], f'حذف عضو هيئة التدريس'))
    except ProtectedAccountError:
        flash('هذا الحساب محمي ولا يمكن حذفه', 'error')
        return redirect_back('teachers.teachers_list')
    flash('تم الحذف بنجاح', 'success')
    return redirect_back('teachers.teachers_list')


@bp.route('/api/teacher-pool')
@login_required
@permission_required('teachers.assign')
def teacher_pool():
    """Return teachers NOT already in the target department."""
    db = get_db()
    dept_id = (request.args.get('dept_id', type=int)
               or session.get('hod_department_id')
               or session.get('department_id'))
    if not dept_id:
        return jsonify([])
    search = request.args.get('search', '').strip()
    params = [dept_id]
    where = [
        't.deleted_at IS NULL',
        'NOT EXISTS (SELECT 1 FROM teacher_departments tdx '
        'WHERE tdx.teacher_id = t.id AND tdx.department_id = ?)',
    ]
    if search:
        where.append('(t.name LIKE ? OR t.academic_number LIKE ?)')
        params.extend([f'%{search}%', f'%{search}%'])
    where_clause = ' AND '.join(where)
    rows = db.execute(
        f'SELECT t.id, t.name, t.academic_number '
        f'FROM teachers t WHERE {where_clause} ORDER BY t.name',
        params,
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/dept-assign', methods=['POST'])
@login_required
@permission_required('teachers.assign')
@csrf_required
def dept_assign():
    """Add a teacher to the target department."""
    db = get_db()
    dept_id = (request.form.get('department_id', type=int)
               or session.get('hod_department_id')
               or session.get('department_id'))
    if not dept_id:
        flash('لا يمكن التعيين بدون قسم', 'error')
        return redirect_back('teachers.teachers_list')
    teacher_id = request.form.get('teacher_id', type=int)
    if not teacher_id:
        flash('لم يتم تحديد أستاذ', 'error')
        return redirect_back('teachers.teachers_list')
    teacher = db.execute(
        'SELECT id, name FROM teachers WHERE id = ? AND deleted_at IS NULL',
        (teacher_id,),
    ).fetchone()
    if not teacher:
        flash('عضو هيئة التدريس غير موجود', 'error')
        return redirect_back('teachers.teachers_list')
    existing = db.execute(
        'SELECT 1 FROM teacher_departments '
        'WHERE teacher_id = ? AND department_id = ?',
        (teacher_id, dept_id),
    ).fetchone()
    if existing:
        flash(f'{teacher["name"]} عضو بالفعل في هذا القسم', 'error')
        return redirect_back('teachers.teachers_list')
    db.execute(
        'INSERT OR IGNORE INTO teacher_departments (teacher_id, department_id) VALUES (?, ?)',
        (teacher_id, dept_id),
    )
    _reconcile_primary_dept(db, teacher_id)
    db.commit()
    add_history(db, 'update', 'teacher_departments', teacher_id,
                session['user_id'], session['username'],
                f'إضافة الأستاذ {teacher["name"]} إلى القسم')
    flash(f'تمت إضافة {teacher["name"]} إلى القسم بنجاح', 'success')
    return redirect_back('teachers.teachers_list')


@bp.route('/dept-unassign', methods=['POST'])
@login_required
@permission_required('teachers.assign')
@csrf_required
def dept_unassign():
    """Remove a teacher from the target department."""
    db = get_db()
    dept_id = (request.form.get('department_id', type=int)
               or session.get('hod_department_id')
               or session.get('department_id'))
    if not dept_id:
        flash('لا يمكن الإزالة بدون قسم', 'error')
        return redirect_back('teachers.teachers_list')
    teacher_id = request.form.get('teacher_id', type=int)
    if not teacher_id:
        flash('لم يتم تحديد أستاذ', 'error')
        return redirect_back('teachers.teachers_list')
    teacher = db.execute(
        'SELECT id, name FROM teachers WHERE id = ? AND deleted_at IS NULL',
        (teacher_id,),
    ).fetchone()
    if not teacher:
        flash('عضو هيئة التدريس غير موجود', 'error')
        return redirect_back('teachers.teachers_list')
    membership = db.execute(
        'SELECT 1 FROM teacher_departments '
        'WHERE teacher_id = ? AND department_id = ?',
        (teacher_id, dept_id),
    ).fetchone()
    if not membership:
        flash(f'{teacher["name"]} ليس عضواً في هذا القسم', 'error')
        return redirect_back('teachers.teachers_list')
    remaining = db.execute(
        'SELECT COUNT(*) AS cnt FROM teacher_departments '
        'WHERE teacher_id = ? AND department_id != ?',
        (teacher_id, dept_id),
    ).fetchone()
    if remaining and remaining['cnt'] == 0:
        flash(f'لا يمكن إزالة {teacher["name"]} — يجب أن ينتمي لأقل قسم واحد', 'error')
        return redirect_back('teachers.teachers_list')
    db.execute(
        'DELETE FROM teacher_departments '
        'WHERE teacher_id = ? AND department_id = ?',
        (teacher_id, dept_id),
    )
    _reconcile_primary_dept(db, teacher_id)
    db.commit()
    add_history(db, 'update', 'teacher_departments', teacher_id,
                session['user_id'], session['username'],
                f'إزالة الأستاذ {teacher["name"]} من القسم')
    flash(f'تمت إزالة {teacher["name"]} من القسم', 'success')
    return redirect_back('teachers.teachers_list')


@bp.route('/api/bulk-ids')
@login_required
@permission_required('teachers.manage')
def teachers_bulk_ids():
    """Return all teacher ids matching the current search/filter, across pages."""
    search = request.args.get('search', '').strip()
    dept_filter = request.args.get('department_id', '')
    role = session.get('role', '')
    user_dept_id = None
    if role == 'head_of_department':
        user_dept_id = session.get('hod_department_id')
    query, params, _ = build_teacher_search(search, dept_filter, user_dept_id, page=1)
    db = get_db()
    rows = db.execute(query, params).fetchall()
    ids = [r['id'] for r in rows]
    return jsonify({'ids': ids, 'total': len(ids)})


@bp.route('/bulk-delete', methods=['POST'])
@login_required
@permission_required('teachers.manage')
@csrf_required
def teachers_bulk_delete():
    ids = request.form.getlist('teacher_ids')
    ids = [i for i in ids if i.isdigit()]
    if not ids:
        flash('لم يتم تحديد أي أعضاء هيئة تدريس', 'error')
        return redirect(url_for('teachers.teachers_list'))
    db = get_db()
    skipped = 0
    for tid in ids:
        try:
            teacher_service.teacher_delete(db, int(tid), lambda db, tid=tid: add_history(
                db, 'soft_delete', 'teacher', int(tid), session['user_id'], session['username'], 'حذف عضو هيئة التدريس'))
        except ProtectedAccountError:
            skipped += 1
    if skipped:
        flash(f'تم تخطي {skipped} من الحسابات المحمية', 'error')
    flash(f'تم الحذف بنجاح', 'success')
    return redirect_back('teachers.teachers_list')


@bp.route('/restore/<int:id>', methods=['POST'])
@login_required
@permission_required('teachers.manage')
@csrf_required
def teachers_restore(id):
    db = get_db()
    teacher_service.teacher_restore(db, id)
    flash('تم استعادة عضو هيئة التدريس', 'success')
    return redirect_back('teachers.teachers_list')


@bp.route('/delete-permanent/<int:id>', methods=['POST'])
@login_required
@permission_required('teachers.manage')
@csrf_required
def teachers_delete_permanent(id):
    db = get_db()
    try:
        teacher_service.teacher_hard_delete(db, id)
    except ProtectedAccountError:
        flash('هذا الحساب محمي ولا يمكن حذفه', 'error')
        return redirect_back('teachers.teachers_list')
    flash('تم حذف عضو هيئة التدريس نهائياً', 'success')
    return redirect_back('teachers.teachers_list')


@bp.route('/bulk-delete-permanent', methods=['POST'])
@login_required
@permission_required('teachers.manage')
@csrf_required
def teachers_bulk_permanent_delete():
    ids = [i for part in request.form.getlist('teacher_ids') for i in part.split(',') if i.strip().isdigit()]
    if not ids:
        flash('لم يتم تحديد أي عضو هيئة تدريس', 'error')
        return redirect_back('teachers.teachers_list')
    db = get_db()
    skipped = 0
    for tid in ids:
        try:
            teacher_service.teacher_hard_delete(db, int(tid))
        except ProtectedAccountError:
            skipped += 1
    if skipped:
        flash(f'تم تخطي {skipped} من الحسابات المحمية', 'error')
    flash(f'تم حذف {len(ids) - skipped} عضو هيئة تدريس نهائياً', 'success')
    return redirect_back('teachers.teachers_list')
