"""Public course-content library (no login required).

Only course_files rows with ``status`` in ``('approved', 'published')`` are
ever served here. The course owns every file; the uploader (teacher/R&D) is
metadata only.

/     /     >---- المكتبة العامة: تُعرض ملفات معتمدة/منشورة فقط وبدون تسجيل دخول.
"""

from __future__ import annotations

from flask import Blueprint, redirect

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


@bp.route('/teacher-file/<int:tf_id>')
def teacher_file(tf_id):
    return download_service.serve_course_file(get_db(), tf_id, status=('approved',))