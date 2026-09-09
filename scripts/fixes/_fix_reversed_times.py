"""Fix reversed/start>=end timetable entries by setting them to their period's
default time range (24-hour, stored unchanged) and syncing the matching
teacher_taught_courses record.

Targets the known bad entry generated when a lecture was saved with a start
time later than its end time (start_time >= end_time). It writes a JSON backup
of every touched row before updating.

Usage:
    python scripts/fixes/_fix_reversed_times.py
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, 'database', 'data.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'scripts', 'fixes', 'backups')
os.makedirs(BACKUP_DIR, exist_ok=True)


def minutes(t):
    h, m = t.split(':')
    return int(h) * 60 + int(m)


def main():
    if not os.path.exists(DB_PATH):
        print('DB not found:', DB_PATH)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    backup = []

    # Period defaults map: code -> (start, end)
    periods = {}
    for r in conn.execute('SELECT code, start_time, end_time FROM period_settings'):
        periods[r['code']] = (r['start_time'], r['end_time'])

    # 1) timetable entries with reversed/invalid ranges
    bad_tt = conn.execute(
        'SELECT id, period, start_time, end_time, hours '
        'FROM timetable WHERE start_time >= end_time OR end_time < start_time OR start_time = "" '
    ).fetchall()

    # 2) teacher_taught_courses with reversed/invalid ranges (linked or not)
    bad_ttc = conn.execute(
        'SELECT id, timetable_entry_id, period, start_time, end_time, hours '
        'FROM teacher_taught_courses '
        'WHERE start_time >= end_time OR end_time < start_time OR start_time = "" '
    ).fetchall()

    print('Found reversed/empty timetable rows :', len(bad_tt))
    print('Found reversed/empty taught rows      :', len(bad_ttc))

    with conn:
        for r in bad_tt:
            default = periods.get(r['period'], (None, None))
            new_start, new_end = default
            valid = bool(new_start and new_end and minutes(new_end) > minutes(new_start))
            new_hours = r['hours']
            if valid:
                mins = minutes(new_end) - minutes(new_start)
                new_hours = max(1, round(mins / 60))
            backup.append({
                'table': 'timetable', 'id': r['id'], 'before': dict(r),
                'after': {'start_time': new_start, 'end_time': new_end, 'hours': new_hours},
            })
            if valid:
                conn.execute(
                    'UPDATE timetable SET start_time=?, end_time=?, hours=? WHERE id=?',
                    (new_start, new_end, new_hours, r['id']),
                )
            else:
                print('  !! timetable id=%s period=%s has no valid default; NOT changed' % (
                    r['id'], r['period']))
            print('  timetable id=%s period=%s  %s -> %s (%s-%s)' % (
                r['id'], r['period'], r['start_time'], r['end_time'],
                new_start or 'unchanged', new_end or 'unchanged'))

        for r in bad_ttc:
            default = periods.get(r['period'], (None, None))
            new_start, new_end = default
            valid = bool(new_start and new_end and minutes(new_end) > minutes(new_start))
            new_hours = r['hours']
            if valid:
                mins = minutes(new_end) - minutes(new_start)
                new_hours = max(1, round(mins / 60))
            backup.append({
                'table': 'teacher_taught_courses', 'id': r['id'], 'before': dict(r),
                'after': {'start_time': new_start, 'end_time': new_end, 'hours': new_hours},
            })
            if valid:
                conn.execute(
                    'UPDATE teacher_taught_courses SET start_time=?, end_time=?, hours=? WHERE id=?',
                    (new_start, new_end, new_hours, r['id']),
                )
            else:
                print('  !! taught id=%s has no valid default; NOT changed' % (r['id'],))
            print('  taught id=%s (tt=%s) period=%s  %s -> %s (%s-%s)' % (
                r['id'], r['timetable_entry_id'], r['period'],
                r['start_time'], r['end_time'], new_start or 'unchanged', new_end or 'unchanged'))

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    bfile = os.path.join(BACKUP_DIR, 'reversed_times_%s.json' % stamp)
    with open(bfile, 'w', encoding='utf-8') as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)
    print('Backup written:', bfile)
    print('Done.')


if __name__ == '__main__':
    main()
