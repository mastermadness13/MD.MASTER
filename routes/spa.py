"""SPA blueprint — serves the single-page application shell at ``/app``.

The SPA is the primary admin UI: it talks to the REST API (``/api/*``) and
shares the session cookie with the HTML routes.  Everything after login
happens client-side; this route only renders the shell.
"""

from __future__ import annotations

from flask import Blueprint, render_template

from security import login_required

bp = Blueprint('spa', __name__)


@bp.route('/app')
@login_required
def app():
    return render_template('spa.html')
