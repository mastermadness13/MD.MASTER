from flask import Blueprint, render_template

from security import login_required, permission_required
from security import current_user
bp = Blueprint('html_to_pdf', __name__)


# /     /     >---- صفحة أداة تحويل HTML إلى PDF (تتطلب صلاحية tools.view)
@bp.route('/tools/html-to-pdf')
@login_required
@permission_required('tools.view')
def html_to_pdf():
    return render_template('tools/html_to_pdf.html', user=current_user())