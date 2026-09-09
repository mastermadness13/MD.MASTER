"""Serve the legacy static public website (static/public).

The old college portal is a set of plain HTML pages that read JSON data via
/shared/data-client.js. This blueprint exposes them at the original URLs so
the site keeps working as a static portal inside the Flask app.
"""
import os

from flask import Blueprint, current_app, redirect, send_from_directory

bp = Blueprint('public_site', __name__)

PUBLIC_DIR_NAME = 'public'

# Pages merged into the unified portal (index.html#section).
LEGACY_REDIRECTS = {
    'schugle/timetables.html': '/index.html#timetables',
    'exams.html': '/index.html#exams',
    'library.html': '/index.html#library',
    'courespage/courespage.html': '/index.html#courses',
}


def _public_dir() -> str:
    return os.path.join(current_app.root_path, 'static', PUBLIC_DIR_NAME)


def _dir(*parts: str) -> str:
    return os.path.join(_public_dir(), *parts)


@bp.route('/index.html')
def index_page():
    return send_from_directory(_public_dir(), 'index.html')


@bp.route('/pages/<path:filename>')
def pages(filename):
    target = LEGACY_REDIRECTS.get(filename)
    if target:
        return redirect(target)
    return send_from_directory(_dir('pages'), filename)


@bp.route('/shared/<path:filename>')
def shared(filename):
    return send_from_directory(_dir('shared'), filename)


@bp.route('/data/<path:filename>')
def data_files(filename):
    return send_from_directory(_dir('data'), filename)


@bp.route('/image/<path:filename>')
def images(filename):
    return send_from_directory(_dir('image'), filename)
