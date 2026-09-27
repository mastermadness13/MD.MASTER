import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('FLASK_ENV', 'testing')

import tempfile
import flask_db
from app import create_app
from database.connection import connect
from database.schema import ensure_schema

tmpdir = tempfile.mkdtemp()
db_path = os.path.join(tmpdir, 'diag.db')
flask_db.DATABASE = db_path
print('flask_db.DATABASE =', flask_db.DATABASE)

conn = connect(db_path)
with open('database/schema.sql', encoding='utf-8') as f:
    conn.executescript(f.read())
ensure_schema(conn)
conn.execute("INSERT OR IGNORE INTO users (username, password, role, label) VALUES ('rnd','x','research_development','RND')")
conn.execute("INSERT OR IGNORE INTO departments (name, semesters, majors, hidden, has_sections, type) VALUES ('Test Dept', 8, 8, 0, 1, 'academic')")
dept_id = conn.execute("SELECT id FROM departments WHERE name='Test Dept'").fetchone()['id']
conn.execute('''INSERT INTO courses (code,name,department_id,year,semester,theoretical_hours,practical_hours,total_hours)
                VALUES ('CS101','Intro',?,1,1,3,1,4)''', (dept_id,))
c1 = conn.execute("SELECT id FROM courses WHERE code='CS101'").fetchone()['id']
conn.commit()
conn.close()

app = create_app()
app.config['TESTING'] = True
c = app.test_client()
with c.session_transaction() as sess:
    sess['user_id'] = 1
    sess['role'] = 'research_development'
    sess['username'] = 'rnd'
    sess['department_id'] = None
    sess['_csrf_token'] = 't'

r = c.get('/teacher/super-admin/course-content/create?course_id=%d' % c1)
print('status', r.status_code)
body = r.get_data(as_text=True)
with open(os.path.join(tmpdir, 'create.html'), 'w', encoding='utf-8') as f:
    f.write(body)
print('len', len(body))
print('has toolbar-actions:', 'cc-create-toolbar-actions' in body)
print('has downloadCourseSheet onclick:', 'onclick="downloadCourseSheet()"' in body)
print('count downloadCourseSheet:', body.count('downloadCourseSheet()'))
print('has form id:', 'id="courseContentForm"' in body)
print('has doc js script:', 'teachers__course_content_doc.js' in body)
print('has page js script:', 'teachers_course_content_page.js' in body)
print('TMP:', tmpdir)

