import io, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, 'static', 'js', 'exams')
FILES = sorted(f for f in os.listdir(DIR) if f.endswith('.js'))

def strip(s):
    out = []
    i = 0
    n = len(s)
    in_str = None
    prev = ''
    while i < n:
        c = s[i]
        nxt = s[i + 1] if i + 1 < n else ''
        if in_str:
            out.append(' ')
            if c == '\\':
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c == "'" or c == '"' or c == '`':
            in_str = c
            out.append(' ')
            i += 1
            continue
        if c == '/' and nxt == '/':
            while i < n and s[i] != '\n':
                i += 1
            continue
        if c == '/' and nxt == '*':
            i += 2
            while i < n and not (s[i] == '*' and (s[i + 1] if i + 1 < n else s[i] == '*') and s[i] == '*'):
                i += 1
            i += 2
            continue
        if c == '/' and prev in ',(=:[!&|?{};':
            i += 1
            while i < n and s[i] != '/':
                if s[i] == '\\':
                    i += 2
                else:
                    i += 1
            i += 1
            continue
        if c in '{}()[]':
            out.append(c)
        else:
            out.append(' ')
        if not c.isspace():
            prev = c
        i += 1
    return ''.join(out)

fail = 0
for f in FILES:
    path = os.path.join(DIR, f)
    text = io.open(path, encoding='utf-8').read()
    code = strip(text)
    for a, b in [('{', '}'), ('(', ')'), ('[', ']')]:
        if code.count(a) != code.count(b):
            print('FAIL %s: %s=%d %s=%d' % (f, a, code.count(a), b, code.count(b)))
            fail += 1
    depth = 0
    for ch in code:
        if ch in '{([':
            depth += 1
        elif ch in '})]':
            depth -= 1
        if depth < 0:
            print('FAIL %s: negative nesting' % f)
            fail += 1
            break
    if fail == 0:
        print('OK   %s (%d delimiters, final depth %d)' % (f, len(code), depth))
    else:
        print('FAIL %s: unbalanced nesting (final depth %d)' % (f, depth))
print('done, %d issue(s)' % fail)
sys.exit(1 if fail else 0)
