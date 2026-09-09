from flask import Blueprint, render_template

from security import login_required, permission_required
from security import current_user
bp = Blueprint('misc', __name__)


@bp.route('/lecture-schedule')
@login_required
@permission_required('timetable.view')
def lecture_schedule():
    return render_template('timetable/lecture.html', user=current_user())
