from flask import Blueprint, session, abort, send_from_directory, current_app

from flask_db import get_db
from security import login_required, permission_required
from security.authorization import has_permission
bp = Blueprint('uploads', __name__, url_prefix='/uploads')

# Roles that may serve any upload regardless of folder ownership.
# /     /     >---- أدوار تصل لأي ملف مرفوع بغض النظر عن ملكية المجلد
_FULL_ACCESS_ROLES = {'super_admin'}

# Shared, non-private folders readable by any staff member allowed to view
# teachers (e.g. profile photos live in ``photos/``).
# /     /     >---- مجلدات مشتركة يقراها الموظفون (مثل صور الملفات)
_SHARED_FOLDERS = {'photos'}


def _allowed_folder_prefixes():
    """Folders the current user may access: their own folder plus any folder
    of a teacher linked to their account.

    Naming matches the per-user folder convention (``teacher_<id>``).

    /     /     >---- مجلدات المستخدم الحالي: مجلده + أي مجلد أستاذ مربوط بحسابه.
    """
    prefixes = set()
    user_id = session.get('user_id')
    if user_id is not None:
        prefixes.add(f'teacher_{user_id}')
        db = get_db()
        rows = db.execute(
            'SELECT id FROM teachers WHERE user_id = ?', (user_id,)
        ).fetchall()
        prefixes.update(f'teacher_{row["id"]}' for row in rows)
    return prefixes


# /     /     >---- تقديم الملف المرفوع مع التحقق من صلاحية الوصول للمجلد
@bp.route('/<path:filename>')
@login_required
@permission_required('uploads.serve')
def uploaded_file(filename):
    role = session.get('role', '')
    if role not in _FULL_ACCESS_ROLES:
        folder = filename.split('/', 1)[0]
        if folder not in _SHARED_FOLDERS or not has_permission(role, 'teachers.view'):
            if folder not in _allowed_folder_prefixes():
                abort(403)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)