"""Fix UTF-8 Arabic text corrupted by cp1252 mojibake.

When a file containing UTF-8 encoded Arabic text is mistakenly decoded
as cp1252/latin-1 and then re-encoded, the Arabic characters become
garbled (mojibaked). This script reverses that corruption by:

1. Reading the file as UTF-8 (which gives us the mojibaked text)
2. Converting each character back to its original byte using an
   explicit cp1252 reverse mapping (handles the special 0x80-0x9F zone
   that differs from latin-1)
3. Decoding the resulting byte array as UTF-8

Usage:
    python scripts/fixes/_fix_mojibake.py [filepath]

Default target: templates/dashboard/super_admin_dashboard.html

This was the 5th and final iteration of mojibake fix scripts.
Earlier attempts (1-4) used simpler approaches that failed on edge
cases like mixed mojibake + correct text or the cp1252 special zone.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('templates/dashboard/super_admin_dashboard.html', 'rb') as f:
    raw = f.read()

# Build cp1252 byte-to-char and char-to-byte mappings
cp1252_chars = {}
cp1252_bytes = {}
# Known cp1252 mappings for 0x80-0x9F range
cp1252_map = {
    0x80: '\u20AC', 0x82: '\u201A', 0x83: '\u0192', 0x84: '\u201E',
    0x85: '\u2026', 0x86: '\u2020', 0x87: '\u2021', 0x88: '\u02C6',
    0x89: '\u2030', 0x8A: '\u0160', 0x8B: '\u2039', 0x8C: '\u0152',
    0x8E: '\u017D', 0x91: '\u2018', 0x92: '\u2019', 0x93: '\u201C',
    0x94: '\u201D', 0x95: '\u2022', 0x96: '\u2013', 0x97: '\u2014',
    0x98: '\u02DC', 0x99: '\u2122', 0x9A: '\u0161', 0x9B: '\u203A',
    0x9C: '\u0153', 0x9E: '\u017E', 0x9F: '\u0178',
}
for b, c in cp1252_map.items():
    cp1252_chars[c] = b

# For bytes 0xA0-0xFF, Latin-1 mapping (U+00A0-U+00FF)
for b in range(0xA0, 0x100):
    c = chr(b)
    cp1252_chars[c] = b

# For bytes 0x00-0x7F, ASCII
for b in range(0x80):
    c = chr(b)
    cp1252_chars[c] = b

# For the undefined cp1252 bytes (0x81, 0x8D, 0x8F, 0x90, 0x9D),
# use Latin-1 mapping (they are C1 control chars)
for b in [0x81, 0x8D, 0x8F, 0x90, 0x9D]:
    cp1252_chars[chr(b)] = b

# Now decode the raw bytes as UTF-8 to get the text
text = raw.decode('utf-8')

# Convert each character to its byte using our custom mapping
# Then decode as UTF-8
out_bytes = bytearray()
for c in text:
    code = ord(c)
    if code in cp1252_chars:
        out_bytes.append(cp1252_chars[code])
    else:
        # Character not in mapping - could be a genuine Unicode char
        # Try to encode as UTF-8 and pass through
        out_bytes.extend(c.encode('utf-8'))

# Decode the resulting bytes as UTF-8
fixed = out_bytes.decode('utf-8', errors='replace')

# Write the fixed version
with open('templates/dashboard/super_admin_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(fixed)

print(f"Fixed file written ({len(fixed)} chars)")

# Verify
with open('templates/dashboard/super_admin_dashboard.html', 'r', encoding='utf-8') as f:
    result = f.read()

checks = [
    ('kulliya', '\u0643\u0644\u064A\u0629'),       # كلية
    ('taqniya', '\u0627\u0644\u062A\u0642\u0646\u064A\u0629'),  # التقنية
    ('handasiya', '\u0627\u0644\u0647\u0646\u062F\u0633\u064A\u0629'),  # الهندسية
    ('zawara', '\u0632\u0648\u0627\u0631\u0629'),    # زوارة
    ('loha', '\u0644\u0648\u062D\u0629'),            # لوحة
    ('tahakum', '\u062A\u062D\u0643\u0645'),          # تحكم
    ('mudeer', '\u0627\u0644\u0645\u062F\u064A\u0631'),  # المدير
    ('aam', '\u0627\u0644\u0639\u0627\u0645'),        # العام
    ('marhaba', '\u0645\u0631\u062D\u0628\u064B\u0627'),  # مرحباً
]
all_ok = True
for name, word in checks:
    if word in result:
        print(f"  PASS: {name}")
    else:
        print(f"  FAIL: {name} missing")
        all_ok = False

if all_ok:
    print("All Arabic text checks passed!")

# Check line count
lines = result.split('\n')
print(f"Total lines: {len(lines)}")

# Strip excessive blank lines (more than 1 consecutive)
import re
cleaned = re.sub(r'\n{3,}', '\n\n', result)
if cleaned != result:
    print(f"Stripped extra blank lines, was {len(result)} -> {len(cleaned)}")
    with open('templates/dashboard/super_admin_dashboard.html', 'w', encoding='utf-8') as f:
        f.write(cleaned)
