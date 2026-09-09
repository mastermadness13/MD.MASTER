import os

from flask import Blueprint, session, request, render_template, redirect, url_for, flash, current_app, send_from_directory

from flask_db import get_db
from security import csrf_required, login_required, permission_required
from security import current_user
from services import message_service, notification_service

bp = Blueprint('hod_pages', __name__, url_prefix='/hod')


@bp.route('/messages', methods=['GET', 'POST'])
@login_required
@permission_required('messages.review')
@csrf_required
def hod_messages():
    db = get_db()
    dept_id = session.get('hod_department_id')
    if request.method == 'POST':
        request_id = request.form.get('request_id', type=int)
        reply_text = request.form.get('reply', '').strip()
        if reply_text:
            req = db.execute(
                'SELECT user_id, subject FROM teacher_requests WHERE id = ?', (request_id,)
            ).fetchone()

            message_service.add_message_reply(db, request_id, session['user_id'], reply_text)
            message_service.resolve_message(db, request_id, session['user_id'])
            message_service.update_teacher_request(db, request_id, 'resolved', session['user_id'], reply_text)
            db.commit()

            if req and req['user_id']:
                notification_service.create_notification(
                    db, req['user_id'],
                    'رد رئيس القسم على رسالتك',
                    f'رد رئيس القسم على طلبك "{req["subject"] or ""}"',
                    'info', 'teacher_request', request_id
                )

            flash('تم الرد على الرسالة', 'success')
        return redirect(url_for('hod_pages.hod_messages'))
    requests = message_service.list_teacher_requests(db, dept_id)
    return render_template('departments/messages.html', requests=requests,
                           user=current_user())


@bp.route('/materials')
@login_required
@permission_required('materials.manage')
def hod_materials():
    db = get_db()
    dept_id = session.get('hod_department_id')
    search = request.args.get('search', '').strip()
    file_type = request.args.get('file_type', '').strip()

    query = '''
        SELECT m.id, m.title, m.original_filename, m.file_size, m.file_type,
               m.download_count, m.created_at, m.filename,
               t.name as teacher_name, t.id as teacher_id,
               c.name as course_name, c.code as course_code
        FROM teacher_materials m
        LEFT JOIN teachers t ON m.teacher_id = t.id
        LEFT JOIN courses c ON m.course_id = c.id
        WHERE m.department_id = ?
    '''
    params = [dept_id]

    if search:
        query += ' AND (c.name LIKE ? OR m.title LIKE ? OR m.original_filename LIKE ? OR t.name LIKE ?)'
        like = f'%{search}%'
        params.extend([like, like, like, like])

    if file_type:
        query += ' AND m.file_type = ?'
        params.append(file_type)

    query += ' ORDER BY c.name, m.created_at DESC'
    materials = [dict(r) for r in db.execute(query, params).fetchall()]

    teachers = [dict(r) for r in db.execute(
        'SELECT DISTINCT t.id, t.name FROM teacher_materials m '
        'JOIN teachers t ON m.teacher_id = t.id WHERE m.department_id = ? ORDER BY t.name',
        (dept_id,)
    ).fetchall()]

    return render_template('departments/materials.html', materials=materials, teachers=teachers,
                          search=search, file_type=file_type,
                           user=current_user())


@bp.route('/materials/delete/<int:material_id>', methods=['POST'])
@login_required
@permission_required('materials.manage')
@csrf_required
def hod_material_delete(material_id):
    db = get_db()
    dept_id = session.get('department_id')
    mat = db.execute(
        'SELECT * FROM teacher_materials WHERE id = ? AND department_id = ?',
        (material_id, dept_id)
    ).fetchone()
    if not mat:
        flash('الملف غير موجود', 'error')
        return redirect(url_for('hod_pages.hod_materials'))

    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], mat['filename'])
    if os.path.exists(file_path):
        os.remove(file_path)

    db.execute('DELETE FROM teacher_materials WHERE id = ?', (material_id,))
    db.commit()

    teacher_uid = notification_service.get_teacher_user_id(db, mat['teacher_id'])
    if teacher_uid:
        notification_service.create_notification(
            db, teacher_uid,
            'حذف ملف من قبل رئيس القسم',
            f'قام رئيس القسم بحذف ملفك "{mat["title"]}"',
            'warning', 'teacher_material', material_id
        )

    flash('تم حذف الملف', 'success')
    return redirect(url_for('hod_pages.hod_materials'))


@bp.route('/materials/download/<int:material_id>')
@login_required
@permission_required('materials.manage')
def hod_material_download(material_id):
    db = get_db()
    dept_id = session.get('department_id')
    mat = db.execute(
        'SELECT filename, original_filename FROM teacher_materials WHERE id = ? AND department_id = ?',
        (material_id, dept_id)
    ).fetchone()
    if not mat:
        from flask import abort
        abort(404)

    db.execute('UPDATE teacher_materials SET download_count = download_count + 1 WHERE id = ?', (material_id,))
    db.commit()

    return send_from_directory(current_app.config['UPLOAD_FOLDER'], mat['filename'],
                               as_attachment=True, download_name=mat['original_filename'])
