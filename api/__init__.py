"""REST API package.

JSON endpoints consumed by the SPA frontend.  Each sub-module owns one domain
blueprint; :func:`register_api` registers them all with the app.

Session auth is shared with the HTML routes (``api/helpers.py`` decorators
return JSON 401/403 instead of redirects).
"""

from __future__ import annotations

from api.helpers import install_error_handlers
from api import (
    auth_api,
    course_content,
    courses,
    dashboard,
    departments,
    exams,
    history,
    notifications,
    rooms,
    search,
    teachers,
    timetable,
)

_BLUEPRINTS = (
    auth_api.bp,
    dashboard.bp,
    departments.bp,
    teachers.bp,
    courses.bp,
    rooms.bp,
    timetable.bp,
    exams.bp,
    history.bp,
    notifications.bp,
    course_content.bp,
    search.bp,
)


def register_api(app) -> None:
    for bp in _BLUEPRINTS:
        install_error_handlers(bp)
        app.register_blueprint(bp)
