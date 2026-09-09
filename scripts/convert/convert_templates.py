#!/usr/bin/env python
"""Convert standalone HTML templates to use shared Jinja2 layouts."""
import json
import os
import re
import sys

TEMPLATES_DIR = r"C:\Users\MD.MASTER\OneDrive\Desktop\newRopey\templates"
MAP_FILE = r"C:\Users\MD.MASTER\OneDrive\Desktop\newRopey\template_map.json"

# Load mapping
with open(MAP_FILE, 'r', encoding='utf-8') as f:
    template_map = json.load(f)

converted_count = 0
skipped_count = 0

for relative_path, info in template_map.items():
    full_path = os.path.join(TEMPLATES_DIR, relative_path)
    
    if not os.path.exists(full_path):
        print(f"  SKIP {relative_path} (not found)")
        skipped_count += 1
        continue
    
    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Skip if already converted
    if re.match(r'^\s*\{%\s*extends\s', content):
        print(f"  SKIP {relative_path} (already converted)")
        skipped_count += 1
        continue
    
    # Extract content between <main...> and </main>
    main_match = re.search(r'<main[^>]*>(.*?)</main>', content, re.DOTALL)
    if not main_match:
        print(f"  SKIP {relative_path} (no <main> tag)")
        skipped_count += 1
        continue
    
    main_content = main_match.group(1)
    
    # Extract title from <title> tag
    title_match = re.search(r'<title>(.*?)</title>', content)
    page_title = info.get('title', '')
    if title_match:
        t = re.sub(r'\s*\|\s*.*$', '', title_match.group(1)).strip()
        if t:
            page_title = t
    
    layout = info['layout']
    active = info['active']
    
    # Build new template
    new_content = (
        '{% extends "shared/layouts/' + layout + '.html" %}\n'
        '{% set sidebar_active = \'' + active + '\' %}\n'
        '{% set page_title = \'' + page_title + '\' %}\n'
        '{% block content %}\n'
        + main_content + '\n'
        '{% endblock %}'
    )
    
    # Remove any duplicate tailwind_config
    new_content = re.sub(r'\{% include [\'\"]partials/tailwind_config\.html[\'\"] %\}\s*', '', new_content)
    
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    saved = len(content) - len(new_content)
    print(f"  OK  {relative_path} (saved {saved} bytes)")
    converted_count += 1

print(f"\nDone! Converted: {converted_count}, Skipped: {skipped_count}")
