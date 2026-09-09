#!/usr/bin/env python
"""Convert remaining standalone templates to use shared Jinja2 layouts."""
import os
import re
import sys

TEMPLATES_DIR = r"C:\Users\MD.MASTER\OneDrive\Desktop\newRopey\templates"

# Mapping of template -> (layout, sidebar_active, page_title)
TEMPLATE_CONFIG = {
    # 'auth/login.html': ('auth', '', 'تسجيل الدخول'),  # skipped - elaborate standalone design
    'dashboard/exam.html': ('exam', 'dashboard', 'لوحة تحكم الامتحانات'),
    'dashboard/hod.html': ('hod', 'dashboard', 'لوحة تحكم رئيس القسم'),
    'dashboard/student.html': ('student', 'dashboard', 'لوحة تحكم الطالب'),
    'dashboard/sub_admin.html': ('sub_admin', 'dashboard', 'لوحة تحكم المشرف الفرعي'),
    'dashboard/super_admin.html': ('super_admin', 'dashboard', 'كلية التقنية الهندسية زوارة'),
    'dashboard/teacher.html': ('teacher', 'dashboard', 'لوحة تحكم المحاضر'),
    'errors/404.html': ('auth', '', '404 - الصفحة غير موجودة'),
    'errors/500.html': ('auth', '', '500 - خطأ داخلي'),
    'profile/settings.html': ('super_admin', 'settings', 'الإعدادات'),
    'profile/user_profile.html': ('super_admin', 'profile', 'الملف الشخصي'),
    'users/change_password.html': ('super_admin', 'change_password', 'تغيير كلمة المرور'),
    'users/edit.html': ('super_admin', 'users', 'تعديل المستخدم'),
    'users/profile.html': ('super_admin', 'profile', 'الملف الشخصي'),
    'users/settings.html': ('super_admin', 'settings', 'الإعدادات'),
    'timetable/print.html': None,  # skip - print special
    'dashboard/print.html': None,  # skip - print special
    'base.html': None,  # skip - old layout
}

def get_main_content(html):
    """Extract content between <main...> and </main> tags."""
    m = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL)
    if m:
        return m.group(1)
    return ''

def get_title(html):
    m = re.search(r'<title>(.*?)</title>', html)
    if m:
        t = re.sub(r'\s*\|\s*.*$', '', m.group(1)).strip()
        return t
    return ''

converted = 0
skipped = 0
for relpath, config in TEMPLATE_CONFIG.items():
    if config is None:
        print(f"  SKIP {relpath} (excluded)")
        skipped += 1
        continue
    
    layout, sidebar_active, page_title = config
    fullpath = os.path.join(TEMPLATES_DIR, relpath)
    
    if not os.path.exists(fullpath):
        print(f"  SKIP {relpath} (not found)")
        skipped += 1
        continue
    
    with open(fullpath, 'r', encoding='utf-8-sig') as f:
        content = f.read()
    
    # Check if already converted
    if re.match(r'^\s*\{%\s*extends\s', content):
        print(f"  SKIP {relpath} (already converted)")
        skipped += 1
        continue
    
    main_content = get_main_content(content)
    if not main_content and relpath != 'auth/login.html':
        # login.html has no <main> tag, handle separately
        print(f"  SKIP {relpath} (no <main> tag)")
        skipped += 1
        continue
    
    # For auth/login.html, find the main content (it has no <main> tag)
    if relpath == 'auth/login.html':
        main_content = content  # convert entire body
    
    title = page_title or get_title(content)
    
    # Strip any remaining inline styles/configs
    main_content = re.sub(
        r'<style>.*?</style>',
        '',
        main_content,
        count=1,
        flags=re.DOTALL
    )
    main_content = re.sub(
        r'<script id="tailwind-config">.*?</script>',
        '',
        main_content,
        flags=re.DOTALL
    )
    
    new_content = (
        '{% extends "shared/layouts/' + layout + '.html" %}\n'
        '{% set sidebar_active = \'' + sidebar_active + '\' %}\n'
        '{% set page_title = \'' + title + '\' %}\n'
        '{% block content %}\n'
        + main_content.strip() + '\n'
        '{% endblock %}'
    )
    
    # Remove any partial includes that the base already handles
    for partial in ['partials/tailwind_config.html', 'partials/header_tailwind.html',
                    'partials/sidebar_tailwind.html', 'partials/footer_tailwind.html',
                    'partials/pagination_tailwind.html', 'partials/breadcrumb_tailwind.html']:
        new_content = re.sub(
            r'\{%\s*(?:include|block)\s+[\'\"]' + re.escape(partial) + r'[\'\"]\s*%\}',
            '',
            new_content
        )
    
    with open(fullpath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    saved = len(content) - len(new_content)
    print(f"  OK  {relpath} (saved {saved} bytes)")
    converted += 1

print(f"\nDone! Converted: {converted}, Skipped: {skipped}")
