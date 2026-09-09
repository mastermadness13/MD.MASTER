from flask import (Blueprint, session, request, render_template,
                   redirect, url_for, flash)
from utils.redirects import redirect_back

from flask_db import get_db
from database.history import add_history
import sqlite3
from security import csrf_required, login_required, permission_required
from security import current_user
from utils.format import paginate
from services import department_service
from services.search import build_department_search, highlight_text

bp = Blueprint('departments', __name__, url_prefix='/departments')


@bp.route('')
@login_required
@permission_required('departments.view')
def departments_list():
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)

    query, params = build_department_search(search, page)
    rows, total, page, per_page = paginate(query, params, page)

    db = get_db()
    departments = department_service.list_departments(db)

    # Filter by search if applied
    if search and departments:
        departments = [d for d in departments if search.lower() in d['name'].lower()]

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return render_template('departments/list_table.html',
                              departments=departments, total=total, page=page,
                              per_page=per_page, search=search,
                              user=current_user(),
                              highlight=highlight_text)

    return render_template('departments/list.html', departments=departments,
                          total=total, page=page, per_page=per_page,
                          search=search, user=current_user(), form={})


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('departments.manage')
@csrf_required
def departments_create():
    if request.method == 'GET':
        flash('استخدم نموذج إضافة قسم', 'info')
        return redirect(url_for('departments.departments_list'))
    name = request.form.get('name', '').strip()
    semesters = request.form.get('semesters', 1, type=int)
    majors = request.form.get('majors', 7, type=int)
    form = {'name': name, 'semesters': semesters, 'majors': majors}
    if not name:
        db = get_db()
        departments = department_service.list_departments(db)
        return render_template('departments/list.html', departments=departments,
                              total=len(departments), page=1, per_page=20,
                              search='', form=form,
                              user=current_user())
    db = get_db()
    if department_service.department_exists_by_name(db, name):
        departments = department_service.list_departments(db)
        return render_template('departments/list.html', departments=departments,
                              total=len(departments), page=1, per_page=20,
                              search='', form=form,
                              user=current_user())
    else:
        department_service.create_department(db, name, semesters, majors)
        flash('تم إنشاء القسم', 'success')
    return redirect(url_for('departments.departments_list'))


@bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('departments.manage')
@csrf_required
def departments_delete(id):
    db = get_db()
    department_service.department_delete(db, id, lambda db: add_history(
        db, 'soft_delete', 'department', id, session['user_id'], session['username'], f'حذف قسم'))
    flash('تم نقل القسم إلى الأرشيف', 'success')
    return redirect_back('departments.departments_list')


@bp.route('/restore/<int:id>', methods=['POST'])
@login_required
@permission_required('departments.manage')
@csrf_required
def departments_restore(id):
    db = get_db()
    department_service.department_restore(db, id)
    flash('تم استعادة القسم', 'success')
    return redirect_back('departments.departments_list')


@bp.route('/delete-permanent/<int:id>', methods=['POST'])
@login_required
@permission_required('departments.manage')
@csrf_required
def departments_delete_permanent(id):
    db = get_db()
    try:
        department_service.department_hard_delete(db, id)
    except Exception:
        db.rollback()
        flash('لا يمكن حذف القسم نهائياً لأنه مرتبط بسجلات أخرى (مدرسون/أقسام).',
              'error')
        return redirect_back('departments.departments_list')
    flash('تم حذف القسم نهائياً', 'success')
    return redirect_back('departments.departments_list')


@bp.route('/bulk-delete-permanent', methods=['POST'])
@login_required
@permission_required('departments.manage')
@csrf_required
def departments_bulk_permanent_delete():
    ids = [i for part in request.form.getlist('department_ids') for i in part.split(',') if i.strip().isdigit()]
    if not ids:
        flash('لم يتم تحديد أي قسم', 'error')
        return redirect_back('departments.departments_list')
    db = get_db()
    deleted = 0
    for did in ids:
        try:
            department_service.department_hard_delete(db, int(did))
            deleted += 1
        except Exception:
            db.rollback()
    if deleted:
        flash(f'تم حذف {deleted} قسم نهائياً', 'success')
    else:
        flash('لا يمكن حذف الأقسام المحددة لأنها مرتبطة بسجلات أخرى.', 'error')
    return redirect_back('departments.departments_list')

