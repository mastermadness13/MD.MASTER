import sqlite3, glob, os
P = 'database/data.db'
if not os.path.exists(P):
    for G in glob.glob('**/data.db', recursive=True):
        P = G
        break
print('using:', P)
D = sqlite3.connect(P)
D.row_factory = sqlite3.Row
print('rows:', [dict(r) for r in D.execute("SELECT id,name,code FROM courses WHERE id IN (57,142,90)").fetchall()])
print('distinct form types:')
for r in D.execute("SELECT DISTINCT file_type FROM course_files WHERE COURSE_ID IN (57,142,90)").fetchall():
    print('  ', dict(r))
</filePath>
