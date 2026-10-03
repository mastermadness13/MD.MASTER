"""Safe, authenticated mail-transport checks from the profile settings page."""

import json
import re
import sqlite3

from tests.harness import CSRF_TOKEN, login_as
from page_routes.profile import (
    _email_test_ip_limiter,
    _email_test_user_limiter,
)


def _office_client(app_fx, db_path, seeded, *, ip='198.51.100.10'):
    user_id = seeded['users']['faculty_affairs']
    conn = sqlite3.connect(db_path)
    conn.execute(
        'UPDATE users SET email = ?, label = ? WHERE id = ?',
        ('office@example.edu', 'مدير المكتب', user_id),
    )
    conn.commit()
    conn.close()
    _email_test_ip_limiter.reset_all()
    _email_test_user_limiter.reset_all()
    return login_as(app_fx, db_path, 'faculty_affairs'), ip


def _flashes(response):
    body = response.get_data(as_text=True)
    match = re.search(
        r'window\.BASE_FLASH_BOOT = \{ messages: (\[.*?\]) \};', body
    )
    return [entry[1] for entry in json.loads(match.group(1))] if match else []


def test_test_email_sends_fixed_message_only_to_signed_in_office_email(
    app_fx, db_path, seeded, monkeypatch
):
    client, ip = _office_client(app_fx, db_path, seeded)
    profile_page = client.get('/profile')
    assert profile_page.status_code == 200
    assert 'إرسال رسالة اختبار إلى بريدي' in profile_page.get_data(as_text=True)
    sent = []
    monkeypatch.setattr(
        'page_routes.profile.send_test_email',
        lambda recipient, name: sent.append((recipient, name)) or True,
    )

    response = client.post(
        '/profile/test-email',
        data={
            '_csrf_token': CSRF_TOKEN,
            'recipient': 'attacker@example.com',
            'subject': 'arbitrary subject',
            'body': 'arbitrary message',
        },
        environ_base={'REMOTE_ADDR': ip},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert 'قبل خادم البريد رسالة الاختبار' in ' '.join(_flashes(response))
    assert sent == [('office@example.edu', 'مدير المكتب')]


def test_test_email_refuses_missing_or_invalid_account_email(
    app_fx, db_path, seeded, monkeypatch
):
    client, ip = _office_client(app_fx, db_path, seeded)
    user_id = seeded['users']['faculty_affairs']
    conn = sqlite3.connect(db_path)
    conn.execute(
        'UPDATE users SET email = ? WHERE id = ?', ('not-an-email', user_id)
    )
    conn.commit()
    conn.close()
    sent = []
    monkeypatch.setattr(
        'page_routes.profile.send_test_email',
        lambda *args: sent.append(args) or True,
    )

    response = client.post(
        '/profile/test-email',
        data={'_csrf_token': CSRF_TOKEN},
        environ_base={'REMOTE_ADDR': ip},
    )

    assert response.status_code == 302
    assert sent == []


def test_test_email_reports_delivery_failure(app_fx, db_path, seeded, monkeypatch):
    client, ip = _office_client(app_fx, db_path, seeded)
    monkeypatch.setattr('page_routes.profile.send_test_email', lambda *_: False)

    response = client.post(
        '/profile/test-email',
        data={'_csrf_token': CSRF_TOKEN},
        environ_base={'REMOTE_ADDR': ip},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert 'تعذر إرسال رسالة الاختبار' in ' '.join(_flashes(response))


def test_test_email_is_limited_and_requires_faculty_affairs(
    app_fx, db_path, seeded, monkeypatch
):
    client, ip = _office_client(app_fx, db_path, seeded)
    sent = []
    monkeypatch.setattr(
        'page_routes.profile.send_test_email',
        lambda *args: sent.append(args) or True,
    )
    payload = {'_csrf_token': CSRF_TOKEN}
    for _ in range(2):
        assert client.post(
            '/profile/test-email',
            data=payload,
            environ_base={'REMOTE_ADDR': ip},
        ).status_code == 302
    limited = client.post(
        '/profile/test-email',
        data=payload,
        environ_base={'REMOTE_ADDR': ip},
    )
    assert limited.status_code == 302
    assert len(sent) == 2

    dean = login_as(app_fx, db_path, 'dean')
    dean_page = dean.get('/profile')
    assert dean_page.status_code == 200
    assert 'إرسال رسالة اختبار إلى بريدي' not in dean_page.get_data(as_text=True)
    denied = dean.post(
        '/profile/test-email',
        data=payload,
        environ_base={'REMOTE_ADDR': '198.51.100.11'},
    )
    assert denied.status_code == 302
    assert len(sent) == 2
