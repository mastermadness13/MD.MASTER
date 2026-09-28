import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(r'C:\Users\MD.MASTER\OneDrive\Desktop\newRopey_final_test')

import flask_db
from app import create_app
from database.connection import connect
from database.schema import ensure_schema

tmpdir = tempfile.mkdtemp()
db_path = os.path.join(tmpdir, 'diag.db')
conn = connect(db_path)
with open('database/schema.sql', encoding='utf-8') as f:
    conn.executescript(f.read())
ensure_schema(conn)
conn.execute("INSERT OR IGNORE INTO users (username,password,role,label) VALUES ('rnd','x','research_development','RND')")
conn.execute("INSERT OR IGNORE INTO departments (name,semesters,majors,hidden,has_sections,type) VALUES ('قسم',8,8,0,1,'academic')")
dept_id = conn.execute("SELECT id FROM departments ORDER BY id DESC LIMIT 1").fetchone()['id']
conn.execute("""INSERT INTO courses (code,name,department_id,year,semester,theoretical_hours,practical_hours,total_hours)
                VALUES ('CS101','تحليل النظم',?,1,1,3,1,4)""", (dept_id,))
c1 = conn.execute("SELECT id FROM courses ORDER BY id DESC LIMIT 1").fetchone()['id']
conn.commit(); conn.close()
flask_db.DATABASE = db_path

app = create_app(); app.config['TESTING'] = True
c = app.test_client()
with c.session_transaction() as s:
    s['user_id'] = 1; s['role'] = 'research_development'; s['username'] = 'rnd'
    s['department_id'] = None; s['_csrf_token'] = 't'
body = c.get('/teacher/super-admin/course-content/create?course_id=%d' % c1).get_data(as_text=True)
assert 'cc-create-toolbar-actions' in body, 'toolbar missing'
out = os.path.join(tmpdir, 'page.html')
open(out, 'w', encoding='utf-8').write(body)
print('HTML_LEN', len(body))
print('OUT', out)
