from datetime import date, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash

from flask_db import get_db
from security import login_required, permission_required, csrf_required
from security import current_user

bp = Blueprint('academic_calendar', __name__, url_prefix='/academic-calendar')

SEASON_AR = {'fall': 'خريفي', 'spring': 'ربيعي'}
SEASON_FULL_AR = {'fall': 'خريف', 'spring': 'ربيع'}
SEASON_EN = {'fall': 'Fall', 'spring': 'Spring'}

YEAR_MIN = date.today().year
YEAR_MAX = YEAR_MIN + 30

DEFAULT_SEMESTER_WEEKS = 14
EXAM_WEEKS = 2
SEASON_START = {
    'fall':   (9, 1),
    'spring': (2, 1),
}


def _compute_dates(season, year, semester_weeks=None):
    weeks = semester_weeks or DEFAULT_SEMESTER_WEEKS
    m, d = SEASON_START[season]
    start = date(year, m, d)
    end = start + timedelta(weeks=weeks)
    exam_end = end
    exam_start = end - timedelta(weeks=EXAM_WEEKS)
    return {
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'exam_start_date': exam_start.isoformat(),
        'exam_end_date': exam_end.isoformat(),
    }


def _load_semesters(db):
    today = date.today().isoformat()
    rows = db.execute(
        'SELECT id, code, season, year, name_ar, name_en, is_active, '
        'start_date, end_date, exam_start_date, exam_end_date '
        'FROM semesters WHERE deleted_at IS NULL '
        'ORDER BY year DESC, CASE season WHEN \'fall\' THEN 0 ELSE 1 END'
    ).fetchall()
    count_rows = db.execute(
        'SELECT ttc.semester_code AS code, '
        'COUNT(DISTINCT ttc.course_id) AS courses_count, '
        'COUNT(DISTINCT ttc.teacher_id) AS teachers_count '
        'FROM teacher_taught_courses ttc '
        'WHERE ttc.archived = 0 '
        'GROUP BY ttc.semester_code'
    ).fetchall()
    counts = {r['code']: r for r in count_rows}
    semesters = []
    for r in rows:
        s = dict(r)
        if s['is_active']:
            s['status'] = 'active'
        elif s['end_date'] and s['end_date'] < today:
            s['status'] = 'past'
        else:
            s['status'] = 'upcoming'
        sem_count = counts.get(s['code'])
        s['courses_count'] = sem_count['courses_count'] if sem_count else 0
        s['teachers_count'] = sem_count['teachers_count'] if sem_count else 0
        semesters.append(s)
    return semesters


@bp.route('')
@login_required
@permission_required('academic_calendar.manage')
def index():
    db = get_db()
    semesters = _load_semesters(db)

    active = next((s for s in semesters if s['status'] == 'active'), None)
    past = [s for s in semesters if s['status'] == 'past']
    upcoming = [s for s in semesters if s['status'] == 'upcoming']

    stats = {
        'total': len(semesters),
        'active_semester': active,
        'active': 1 if active else 0,
        'upcoming': len(upcoming),
        'past': len(past),
    }

    return render_template(
        'academic_calendar/index.html',
        semesters=[s for s in semesters if s['status'] != 'past'],
        past_semesters=past,
        stats=stats,
        season_ar=SEASON_AR,
        season_full_ar=SEASON_FULL_AR,
        year_min=YEAR_MIN,
        year_max=YEAR_MAX,
        user=current_user(),
    )


@bp.route('/create', methods=['POST'])
@login_required
@permission_required('academic_calendar.manage')
@csrf_required
def create():
    db = get_db()
    season = request.form.get('season', '').strip()
    year = request.form.get('year', '', type=int)

    if season not in ('fall', 'spring') or not year:
        flash('بيانات غير صحيحة', 'error')
        return redirect(url_for('academic_calendar.index'))

    if year < YEAR_MIN or year > YEAR_MAX:
        flash(f'السنة يجب أن تكون بين {YEAR_MIN} و {YEAR_MAX}', 'error')
        return redirect(url_for('academic_calendar.index'))

    semester_weeks = request.form.get('semester_weeks', DEFAULT_SEMESTER_WEEKS, type=int)
    if semester_weeks not in (12, 14, 16, 18, 20):
        semester_weeks = DEFAULT_SEMESTER_WEEKS

    code = f'{season}_{year}'
    name_ar = f'{SEASON_FULL_AR[season]} {year}'
    name_en = f'{SEASON_EN[season]} {year}'

    exists = db.execute('SELECT id FROM semesters WHERE code = ?', (code,)).fetchone()
    if exists:
        flash('الفصل الدراسي موجود مسبقاً', 'error')
        return redirect(url_for('academic_calendar.index'))

    dates = _compute_dates(season, year, semester_weeks)
    db.execute(
        'INSERT INTO semesters (code, season, year, name_ar, name_en, '
        'start_date, end_date, exam_start_date, exam_end_date) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (code, season, year, name_ar, name_en,
         dates['start_date'], dates['end_date'],
         dates['exam_start_date'], dates['exam_end_date']),
    )
    db.commit()
    flash('تم إنشاء الفصل بنجاح', 'success')
    return redirect(url_for('academic_calendar.index'))


@bp.route('/<int:semester_id>')
@login_required
@permission_required('academic_calendar.manage')
def view(semester_id):
    db = get_db()
    sem = db.execute(
        'SELECT * FROM semesters WHERE id = ? AND deleted_at IS NULL',
        (semester_id,),
    ).fetchone()
    if not sem:
        flash('الفصل غير موجود', 'error')
        return redirect(url_for('academic_calendar.index'))

    semester = dict(sem)
    today = date.today().isoformat()
    if semester['is_active']:
        semester['status'] = 'active'
    elif semester['end_date'] and semester['end_date'] < today:
        semester['status'] = 'past'
    else:
        semester['status'] = 'upcoming'

    courses = db.execute(
        'SELECT DISTINCT c.id, c.code, c.name, c.department '
        'FROM courses c '
        'JOIN teacher_taught_courses ttc ON ttc.course_id = c.id '
        'WHERE ttc.semester_code = ? AND ttc.archived = 0 '
        'ORDER BY c.name',
        (semester['code'],),
    ).fetchall()

    teachers = db.execute(
        'SELECT DISTINCT t.id, t.name '
        'FROM teachers t '
        'JOIN teacher_taught_courses ttc ON ttc.teacher_id = t.id '
        'WHERE ttc.semester_code = ? AND ttc.archived = 0 '
        'ORDER BY t.name',
        (semester['code'],),
    ).fetchall()

    departments = db.execute(
        'SELECT DISTINCT d.id, d.name '
        'FROM departments d '
        'JOIN teacher_taught_courses ttc ON ttc.department_id = d.id '
        'WHERE ttc.semester_code = ? AND ttc.archived = 0 '
        'ORDER BY d.name',
        (semester['code'],),
    ).fetchall()

    return render_template(
        'academic_calendar/view.html',
        semester=semester,
        courses=courses,
        teachers=teachers,
        departments=departments,
        season_ar=SEASON_AR,
        user=current_user(),
    )


@bp.route('/<int:semester_id>/edit', methods=['POST'])
@login_required
@permission_required('academic_calendar.manage')
@csrf_required
def edit(semester_id):
    db = get_db()
    row = db.execute('SELECT id FROM semesters WHERE id = ?', (semester_id,)).fetchone()
    if not row:
        flash('الفصل غير موجود', 'error')
        return redirect(url_for('academic_calendar.index'))

    start_date = request.form.get('start_date', '').strip()
    end_date = request.form.get('end_date', '').strip()
    exam_start = request.form.get('exam_start_date', '').strip()
    exam_end = request.form.get('exam_end_date', '').strip()

    db.execute(
        'UPDATE semesters SET start_date = ?, end_date = ?, '
        'exam_start_date = ?, exam_end_date = ? WHERE id = ?',
        (start_date, end_date, exam_start, exam_end, semester_id),
    )
    db.commit()
    flash('تم تحديث التواريخ بنجاح', 'success')
    return redirect(url_for('academic_calendar.index'))


@bp.route('/<int:semester_id>/activate', methods=['POST'])
@login_required
@permission_required('academic_calendar.manage')
@csrf_required
def activate(semester_id):
    db = get_db()
    row = db.execute('SELECT id FROM semesters WHERE id = ?', (semester_id,)).fetchone()
    if not row:
        flash('الفصل غير موجود', 'error')
        return redirect(url_for('academic_calendar.index'))

    db.execute('UPDATE semesters SET is_active = 0')
    db.execute('UPDATE semesters SET is_active = 1 WHERE id = ?', (semester_id,))
    db.commit()
    flash('تم تفعيل الفصل بنجاح', 'success')
    return redirect(url_for('academic_calendar.index'))


@bp.route('/<int:semester_id>/deactivate', methods=['POST'])
@login_required
@permission_required('academic_calendar.manage')
@csrf_required
def deactivate(semester_id):
    db = get_db()
    db.execute('UPDATE semesters SET is_active = 0 WHERE id = ?', (semester_id,))
    db.commit()
    flash('تم إلغاء تفعيل الفصل', 'success')
    return redirect(url_for('academic_calendar.index'))


@bp.route('/<int:semester_id>/delete', methods=['POST'])
@login_required
@permission_required('academic_calendar.manage')
@csrf_required
def delete(semester_id):
    db = get_db()
    sem = db.execute(
        'SELECT id, is_active FROM semesters WHERE id = ? AND deleted_at IS NULL',
        (semester_id,),
    ).fetchone()
    if not sem:
        flash('الفصل غير موجود', 'error')
        return redirect(url_for('academic_calendar.index'))

    if sem['is_active']:
        flash('لا يمكن حذف الفصل النشط. ألغِ تفعيله أولاً', 'error')
        return redirect(url_for('academic_calendar.index'))

    db.execute(
        "UPDATE semesters SET deleted_at = datetime('now') WHERE id = ?",
        (semester_id,),
    )
    db.commit()
    flash('تم حذف الفصل بنجاح', 'success')
    return redirect(url_for('academic_calendar.index'))
