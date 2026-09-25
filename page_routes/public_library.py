"""Public course-content library (no login required).

Only course_files rows with ``status`` in ``('approved', 'published')`` are
ever served here. The course owns every file; the uploader (teacher/R&D) is
metadata only.

/     /     >---- المكتبة العامة: تُعرض ملفات معتمدة/منشورة فقط وبدون تسجيل دخول.
"""

from __future__ import annotations

from flask import Blueprint, abort, make_response, redirect, render_template, request

from flask_db import get_db
from services import download_service

bp = Blueprint('public_library', __name__)


# /     /     >---- رابط المكتبة القديم يوجّه للبوابة الموحدة
@bp.route('/library')
def library():
    """Legacy library URL — the unified portal hosts the library section."""
    return redirect('/index.html#library')


# /     /     >---- مسار التحميل الرئيسي لملف مقرر معتمد
@bp.route('/course-file/<int:file_id>')
def course_file(file_id):
    """Canonical download route — serves approved course_files rows."""
    return download_service.serve_course_file(get_db(), file_id)


# /     /     >---- تحميل إيداع من المكتبة
@bp.route('/library/file/<int:submission_id>')
def library_file(submission_id):
    return download_service.serve_submission_file(get_db(), submission_id)


@bp.route('/vocabulary/file/<int:file_id>')
def vocabulary_file(file_id):
    return download_service.serve_course_file(get_db(), file_id, status=('approved',))


@bp.route('/course-content/<int:submission_id>')
def course_content(submission_id):
    """Public view of a published electronic course-description sheet."""
    db = get_db()
    submission = db.execute(
        '''SELECT s.*, c.year AS academic_year,
                  d.name AS dept_name, ap.label AS period_label
           FROM course_content_submissions s
           LEFT JOIN departments d ON d.id = s.department_id
           LEFT JOIN academic_periods ap ON ap.id = s.academic_period_id
           LEFT JOIN courses c ON c.id = s.course_id AND c.deleted_at IS NULL
           WHERE s.id = ? AND s.status = 'published' ''',
        (submission_id,)
    ).fetchone()
    if not submission:
        abort(404)
    curriculum = [dict(row) for row in db.execute(
        '''SELECT topic, weeks, content, topic_en, content_en,
                  COALESCE(section, 'theoretical') AS section
           FROM course_content_curriculum
           WHERE submission_id = ? ORDER BY sort_order''',
        (submission_id,)
    ).fetchall()]
    html = render_template(
        'teachers/course_content_sheet.html',
        user=None,
        hide_sidebar=True,
        public_view=True,
        page_mode='readonly',
        page_title='نموذج توصيف المقرر',
        submission=dict(submission),
        curriculum=curriculum,
        theoretical_curriculum=[r for r in curriculum if r['section'] == 'theoretical'],
        practical_curriculum=[r for r in curriculum if r['section'] == 'practical'],
        doc=dict(submission),
    )
    if request.args.get('download') == '1':
        response = make_response(html)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        response.headers['Content-Disposition'] = (
            'attachment; filename="course-content-%s.html"' % submission_id
        )
        return response
    return html


@bp.route('/teacher-file/<int:tf_id>')
def teacher_file(tf_id):
    return download_service.serve_course_file(get_db(), tf_id, status=('approved',))