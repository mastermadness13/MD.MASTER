# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from app import create_app

app = create_app()
client = app.test_client()
with client.session_transaction() as sess:
    sess['user_id'] = 1
    sess['role'] = 'faculty_affairs'
    sess['username'] = 'office_manager'
    sess['department_id'] = None
    sess['_csrf_token'] = 't'

r = client.get('/teacher/super-admin/course-content')
body = r.get_data(as_text=True)
print('status', r.status_code)
print('overflow-x-visible:', 'overflow-x-visible' in body)
print('overflow-x-auto:', 'overflow-x-auto' in body)
print('min-w-[820px]:', 'min-w-[820px]' in body)
print('search box (ccListSearch):', 'ccListSearch' in body)
print('pdf_state badges in BOOT courses:', body.count('pdf_state'))
