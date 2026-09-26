"""Deny-by-default and permission-map consistency.

Permanent guard for the class of defect where a route carries a gate the
framework hook cannot see, or declares a permission that no role is ever
granted. Both shipped undetected before this file existed.
"""

import pathlib
import re

import pytest

import app as app_module
from core.constants import ROLE_PERMISSIONS

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module')
def requirements(app_fx):
    """Map every endpoint to the gate its view function declares."""
    out = {}
    for rule in app_fx.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        if any(rule.rule.startswith(p) for p in app_module.PUBLIC_PREFIXES):
            continue
        view = app_fx.view_functions[rule.endpoint]
        out[rule.endpoint] = {
            'permission': getattr(view, '_required_permission', None),
            'roles': getattr(view, '_required_roles', None),
            'any_roles': getattr(view, '_required_any_roles', None),
            'public': rule.endpoint in app_module.PUBLIC_ENDPOINTS,
            'authenticated_only': rule.endpoint in app_module.AUTHENTICATED_ENDPOINTS,
        }
    return out


def test_every_endpoint_declares_a_gate(requirements):
    """No route may reach the deny-by-default hook without a declaration."""
    undeclared = sorted(
        endpoint for endpoint, req in requirements.items()
        if not (req['permission'] or req['roles'] or req['any_roles']
                or req['public'] or req['authenticated_only'])
    )
    assert undeclared == [], (
        'endpoints a logged-in user could reach with no declared gate: '
        f'{undeclared}'
    )


def test_role_gates_declare_a_non_empty_role_tuple(requirements):
    empty = sorted(
        endpoint for endpoint, req in requirements.items()
        if req['roles'] == () or req['any_roles'] == ()
    )
    assert empty == [], f'role gates declared with an empty role tuple: {empty}'


def test_no_endpoint_is_both_public_and_permission_gated(requirements):
    """A public endpoint that also declares a gate means the gate is dead."""
    conflicting = sorted(
        endpoint for endpoint, req in requirements.items()
        if req['public'] and (req['permission'] or req['roles'] or req['any_roles'])
    )
    assert conflicting == [], (
        f'public endpoints whose permission gate never runs: {conflicting}'
    )


def _source_permission_strings(pattern):
    found = set()
    for sub in ('page_routes', 'api_routes', 'core', 'services'):
        for path in (ROOT / sub).rglob('*.py'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            found.update(pattern.findall(text))
    return found


def test_every_required_permission_is_granted_to_some_role():
    """A permission used by a decorator must be held by at least one role."""
    granted = set()
    for perms in ROLE_PERMISSIONS.values():
        granted |= perms
    pattern = re.compile(r"permission_required\(\s*['\"]([a-z_.]+)['\"]\s*\)")
    ungrantable = sorted(_source_permission_strings(pattern) - granted)
    assert ungrantable == [], (
        'permissions required by a route but granted to no role: '
        f'{ungrantable}'
    )


def test_role_required_only_names_known_roles():
    """role_required must only name roles present in the permission model."""
    pattern = re.compile(r"(?:any_)?role_required\(\s*([^)]*)\)")
    used = set()
    for permissions in _source_permission_strings(pattern):
        used.update(re.findall(r"['\"]([a-z_]+)['\"]", permissions))
    unknown = sorted(used - set(ROLE_PERMISSIONS))
    assert unknown == [], f'role_required names unknown roles: {unknown}'


def test_every_declared_public_endpoint_exists(app_fx):
    """Typos in PUBLIC_ENDPOINTS would silently fail open."""
    endpoints = {rule.endpoint for rule in app_fx.url_map.iter_rules()}
    missing = sorted(app_module.PUBLIC_ENDPOINTS - endpoints)
    assert missing == [], f'PUBLIC_ENDPOINTS names unknown endpoints: {missing}'


def test_every_declared_authenticated_endpoint_exists(app_fx):
    endpoints = {rule.endpoint for rule in app_fx.url_map.iter_rules()}
    missing = sorted(app_module.AUTHENTICATED_ENDPOINTS - endpoints)
    assert missing == [], (
        f'AUTHENTICATED_ENDPOINTS names unknown endpoints: {missing}'
    )
