"""Download service — course-content files and submission bytes.

Consolidates the byte-serving helpers that used to live in
``routes/public_library.py`` and ``routes/teacher_pages.py`` so every route
just asks for a file and gets a Flask response (or a redirect, for the legacy
``/library/file`` URL).

/     /     >---- خدمة التحميل: إرسال ملفات المحتوى وملفات التسليم للطلاب.
"""

from __future__ import annotations

import os

from flask import abort, current_app, redirect, request, send_from_directory, url_for

from services import public_service


# /     /     >---- إرسال صف ملف من جدول course_files؛ وإلا خطأ 404
def _send_course_file(file_row):
    """Send a course_files row; 404 when the bytes are missing."""
    if not file_row or not file_row.get('filename'):
        abort(404)
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_row['filename'])
    if not os.path.exists(path):
        abort(404)
    # /     /     >---- اسم افتراضي للتحميل حسب نوع الملف إذا ما كان الاسم الأصلي موجود
    default_name = {
        'form': 'course-content.pdf',
        'syllabus': 'course-syllabus.pdf',
        'vocabulary': 'course-vocabulary.pdf',
    }.get(file_row.get('file_type'), 'course-file.pdf')
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'], file_row['filename'],
        as_attachment=request.args.get('download') == '1',
        download_name=file_row.get('original_filename') or default_name,
    )


# /     /     >---- التحميل الأساسي: يبعث ملفات course_files المعتمدة/المنشورة فقط
def serve_course_file(db, file_id, status=('approved', 'published')):
    """Canonical public download for approved or published course files."""
    return _send_course_file(public_service.get_course_file(db, file_id, status=status))


# /     /     >---- الرابط القديم: يوجّه للملف الأساسي أو يبعث المرفوع مباشرة
def serve_submission_file(db, submission_id):
    """Legacy ``/library/file/<id>`` — redirect to the canonical row when
    mirrored, otherwise serve the uploaded bytes directly."""
    row = db.execute(
        'SELECT course_file_id, filename, original_filename, status '
        'FROM course_content_submissions WHERE id = ?',
        (submission_id,)
    ).fetchone()
    if not row:
        abort(404)
    if row['course_file_id']:
        return redirect(url_for('public_library.course_file', file_id=row['course_file_id']))
    if row['status'] not in ('published',) or not row['filename']:
        abort(404)
    return _send_course_file(dict(row))


# /     /     >---- إرسال ملف تسليم أستاذ/بحث وتطوير (الصلاحيات من مسؤولية المسار)
def serve_course_content_file(db, submission_id, download):
    """Send a teacher/R&D course-content submission file.

    Ownership/permission checks are the route's job (as before); this only
    serves the bytes and 404s when the row or file is missing.
    """
    row = db.execute(
        'SELECT filename, original_filename FROM course_content_submissions WHERE id = ?',
        (submission_id,)
    ).fetchone()
    if not row or not row['filename']:
        abort(404)
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], row['filename'])
    if not os.path.exists(path):
        abort(404)
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'], row['filename'],
        as_attachment=download,
        download_name=row['original_filename'] or 'course-content.pdf',
    )