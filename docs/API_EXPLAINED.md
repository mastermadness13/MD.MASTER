# شرح تفصيلي لمجلد `api/` — REST API لمشروع Ropey

## أولاً: الصورة الكاملة

```
┌─────────────────────────────────────────────────────┐
│                      app.py                         │
│  (يستخدم register_api(app) لتسجيل كل البلوبرنتات)  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              api/__init__.py  (منسق المجلد)          │
│  يستورد كل ملفات api ويجمعها في بلوبرنت واحد        │
└──────────────────────┬──────────────────────────────┘
                       │
       ┌───────────────┼───────────────────────┐
       │               │                       │
       ▼               ▼                       ▼
┌────────────┐ ┌──────────────┐ ┌──────────────────┐
│ helpers.py │ │  auth.py     │ │  dashboard.py    │
│ (أدوات مشتركة)│ (تسجيل دخول) │ (لوحة التحكم)    │
└────────────┘ └──────────────┘ └──────────────────┘
       │
       │  يستخدمه كل الملفات
       ▼
┌─────────────────────────────────────────────────────┐
│ security/ → has_permission, csrf_required            │
│ database/ → history.add_history                      │
│ services/ → كل خدمة متخصصة                           │
└─────────────────────────────────────────────────────┘
```

---

## 1. `api/__init__.py` — منسق جميع بلوبرنتات الـ API

**الملف:** `api/__init__.py` (47 سطر)

**وظيفته:** نقطة الدخول المركزية — يستورد كل ملفات الـ API ويجمعها كـ Blueprint واحد مسجل في `app.py`

**التركيب:**
- `_BLUEPRINTS`: كائن ي جمع كل `bp` من كل ملف (auth, dashboard, departments, teachers, courses, rooms, timetable, exams, history, notifications, course_content, search)
- `register_api(app)`: يمر على كل blueprint ويضيف معالجات الأخطاء عبر `install_error_handlers(bp)` ثم يسجله بـ `app.register_blueprint(bp)`

### المتصل به:
```
app.py (سطر 155) ←── register_api(app) ←── api/__init__.py
    │
    ├── api/helpers.py        (install_error_handlers)
    ├── api/auth.py           (bp)
    ├── api/dashboard.py      (bp)
    ├── api/courses.py        (bp)
    ├── api/departments.py    (bp)
    ├── api/teachers.py       (bp)
    ├── api/rooms.py          (bp)
    ├── api/timetable.py      (bp)
    ├── api/exams.py          (bp)
    ├── api/history.py        (bp)
    ├── api/notifications.py  (bp)
    ├── api/course_content.py (bp)
    └── api/search.py         (bp)
```

---

## 2. `api/helpers.py` — الأدوات المشتركة لكل ملفات الـ API

**الملف:** `api/helpers.py` (125 سطر)

**وظيفته:** المكتبة الأساسية — كل ملف في `api/` يعتمد عليها

### الدوال الرئيسية:

| الدالة | الأسطر | الوظيفة |
|--------|--------|---------|
| `_clean(value)` | 22-30 | يحوّل `sqlite3.Row` و `dict` و `list` لقيم JSON-safe |
| `ok(data, status)` | 33-36 | يرجع `{"ok": true, "data": ...}` |
| `err(message, status)` | 39-43 | يرجع `{"ok": false, "message": ...}` |
| `pagination()` | 46-52 | يقرأ `page`, `per_page`, `search` من query |
| `body()` | 55-58 | يقرأ JSON body (dict فارغ إن لم يوجد) |
| `public_user(user)` | 61-66 | يحذف الحقول الحساسة (password, token) |
| `log_history(db, ...)` | 69-76 | يسجل عملية في سجل العمليات عبر `database/history.py` |
| `install_error_handlers(bp)` | 79-101 | معالجات أخطاء JSON (401, 403, 404, 500) |
| `api_login_required` | 104-110 | ديكوراتور يتحقق من تسجيل الدخول |
| `api_permission_required(p)` | 113-125 | ديكوراتور يتحقق من صلاحية محددة |

### التدفق التفصيلي لـ `_clean(value)` (سطر 22-30):
```
المدخل: أي قيمة Python
    │
    ├── sqlite3.Row → dict
    ├── dict → dict نظيف
    ├── list/tuple → list نظيف
    └── أي شيء آخر → يرجع كما هو
    │
    ▼
المخرج: قيمة JSON-safe
```

### المتصل به:
```
api/helpers.py
    │
    ├── security/__init__.py   ←── has_permission()
    ├── database/history.py    ←── add_history()
    ├── flask/session          ←── للتحقق من user_id
    └── flask/jsonify          ←── لتصدير JSON
```

### الملفات التي تستخدمه:
```
api/auth.py           ←── body, err, ok, public_user
api/dashboard.py      ←── api_login_required, ok
api/courses.py        ←── api_login_required, api_permission_required, body, err, log_history, ok, pagination
api/departments.py    ←── api_permission_required, body, err, log_history, ok
api/teachers.py       ←── api_login_required, api_permission_required, body, err, log_history, ok, pagination
api/rooms.py          ←── api_login_required, api_permission_required, body, err, log_history, ok, pagination
api/timetable.py      ←── api_permission_required, body, err, ok
api/exams.py          ←── api_permission_required, body, err, ok
api/history.py        ←── api_permission_required, err, ok, pagination
api/notifications.py  ←── api_login_required, api_permission_required, ok
api/course_content.py ←── api_permission_required, err, ok
api/search.py         ←── api_permission_required, ok
```

---

## 3. `api/auth.py` — تسجيل الدخول والخروج وبيانات المستخدم

**الملف:** `api/auth.py` (94 سطر)
**Blueprint:** `api_auth` — `url_prefix='/api/auth'`

### الـ Endpoints:
```
POST /api/auth/login   ←── تسجيل الدخول (JSON أو form)
POST /api/auth/logout  ←── تسجيل الخروج
GET  /api/auth/me      ←── جلب بيانات المستخدم الحالي (JSON)
```

### التدفق التفصيلي لـ `/api/auth/login`:
```
الطلب يصل (JSON body: {username, password, remember})
    │
    ▼
csrf_required (التحقق من CSRF token) ←── security/csrf.py
    │
    ▼
body() ←── api/helpers.py يقرأ الـ JSON
    │
    ▼
التحقق من username + password موجودين
    │
    ├── فاضي؟ → err('اسم المستخدم وكلمة المرور مطلوبان', 422)
    │
    ▼
RateLimiter يتحقق ←── core/rate_limiter.py
    │
    ├── 5 محاولات في 60 ثانية → err('تم تجاوز الحد المسموح', 429)
    │
    ▼
user_service.authenticate() ←── services/user_service.py
    │
    ├── فشل؟ → err('اسم المستخدم أو كلمة المرور غير صحيحة', 401)
    │            + سجل المحاولة في RateLimiter
    │
    ▼
_session_payload() ←── يبني بيانات الجلسة
    │
    ├── current_user()            ←── security/__init__.py
    ├── get_nav_items()           ←── security/__init__.py
    ├── get_user_permissions()    ←── security/__init__.py
    ├── ROLE_NAMES                ←── core/constants.py
    └── csrf_token                ←── session
    │
    ▼
ok(_session_payload()) ←── استجابة ناجحة مع كل البيانات
```

### المتصل به:
```
api/auth.py
    │
    ├── api/helpers.py            (body, err, ok, public_user)
    ├── core/constants.py         (ROLE_NAMES)
    ├── core/rate_limiter.py      (RateLimiter)
    ├── flask_db.py               (get_db)
    ├── security/__init__.py      (current_user, get_nav_items, get_user_permissions, get_header_messages_url)
    ├── security/csrf.py          (csrf_required)
    └── services/user_service.py  (authenticate)
```

---

## 4. `api/dashboard.py` — لوحة التحكم حسب الدور

**الملف:** `api/dashboard.py` (37 سطر)
**Blueprint:** `api_dashboard` — `url_prefix='/api'`

### الـ Endpoint:
```
GET /api/dashboard?show=5
```

### التدفق:
```
الطلب يصل (GET)
    │
    ▼
api_login_required ←── التحقق من تسجيل الدخول
    │
    ▼
يقرأ الدور من session: role = session.get('role', '')
    │
    ├── admin / super_admin           → stats فقط
    ├── head_of_department            → stats + hod data
    ├── teacher                       → stats + teacher data
    ├── exam                          → stats + exam dept data
    └── research_development          → stats + rnd data
    │
    ▼
dashboard_service.get_dashboard_stats(role, show)
    │
    ▼
ok(payload)
```

### المتصل به:
```
api/dashboard.py
    │
    ├── api/helpers.py               (api_login_required, ok)
    ├── flask_db.py                  (get_db)
    └── services/dashboard_service.py (get_dashboard_stats, get_hod_dashboard_data,
                                       get_teacher_dashboard_data,
                                       get_exam_dept_dashboard_data,
                                       get_rnd_dept_dashboard_data)
```

---

## 5. `api/courses.py` — إدارة المقررات الدراسية

**الملف:** `api/courses.py` (200 سطر)
**Blueprint:** `api_courses` — `url_prefix='/api/courses'`

### الـ Endpoints:
```
GET    /api/courses                     ←── قائمة المقررات (pagination)
POST   /api/courses                     ←── إنشاء مقرر جديد
GET    /api/courses/<id>                ←── تفاصيل مقرر
PUT    /api/courses/<id>                ←── تعديل مقرر
DELETE /api/courses/<id>                ←── حذف سلبي
POST   /api/courses/<id>/restore        ←── استرجاع مقرر
DELETE /api/courses/<id>/permanent      ←── حذف نهائي
POST   /api/courses/move                ←── نقل مقرر لفصل آخر
POST   /api/courses/sync-from-timetable ←── مزامنة من الجدول
```

### التدفق التفصيلي لـ `POST /api/courses` (إنشاء): 
```
JSON body: {code, name, semester, department_ids, ...}
    │
    ▼
api_permission_required('courses.view') + csrf_required
    │
    ▼
_course_form(data) ←── يجهز البيانات
    │
    ├── يدعم placements (list of {department_id, semester})
    ├── أو department_ids (list)
    ├── يحول prerequisite_id لـ int أو None
    └── يبني dict من الحقول (code, name, hours, year, semester, icon, notes)
    │
    ▼
التحقق من code و name موجودين
    │
    ├── فاضي؟ → err('الكود والاسم مطلوبان', 422)
    │
    ▼
course_service.create_course() ←── services/course_service.py
    │
    ▼
log_history() ←── يسجل العملية في السجل
    │
    ▼
ok({'id': course_id}, status=201)
```

### المتصل به:
```
api/courses.py
    │
    ├── api/helpers.py               (api_login_required, api_permission_required, body,
    │                                 err, log_history, ok, pagination)
    ├── flask_db.py                  (get_db)
    ├── security/__init__.py         (current_user)
    ├── security/csrf.py             (csrf_required)
    └── services/course_service.py   (list_courses, create_course, get_course,
                                      get_course_detail, update_course, course_delete,
                                      course_restore, course_hard_delete,
                                      move_course_to_semester, sync_courses_from_timetable)
```

---

## 6. `api/course_content.py` — البحث السريع لمحتوى المقررات (المُطلّق)

**الملف:** `api/course_content.py` (146 سطر)
**Blueprint:** `api_course_content` — `url_prefix='/api/course-content'`

### الـ Endpoints (للقراءة فقط):
```
GET /api/course-content/teachers        ←── بحث عن أساتذة (بالاسم أو الرقم الأكاديمي)
GET /api/course-content/courses         ←── بحث عن مقررات (بالاسم أو الكود)
GET /api/course-content/teacher-courses ←── مقررات أستاذ معين (من الجدول النشط فقط)
GET /api/course-content/course-teachers ←── أساتذة مقرر معين (من الجدول النشط فقط)
```

### الميزة الرئيسية:
> يستخدم `_active_version_filter()` — يتحقق من `timetable_versions` بأي نسخة نشطة فقط (`status = 'active'`)
> هذا يضمن أن البحث يرجع فقط المقررات والأسـاتذة الموجودة في الجدول الفعلي الحالي

### المتصل به:
```
api/course_content.py
    │
    ├── api/helpers.py   (api_permission_required, err, ok)
    └── flask_db.py      (get_db)
    // SQL مباشرة على المستخدم: teachers, courses, timetable,
    //   timetable_versions, course_files, course_departments, departments
```

---

## 7. `api/departments.py` — إدارة الأقسام

**الملف:** `api/departments.py` (141 سطر)
**Blueprint:** `api_departments` — `url_prefix='/api/departments'`

### الـ Endpoints:
```
GET    /api/departments                         ←── قائمة الأقسام
POST   /api/departments                         ←── إنشاء قسم (name, semesters, majors)
GET    /api/departments/<id>                    ←── تفاصيل قسم + الشعوب
PUT    /api/departments/<id>                    ←── تعديل قسم
DELETE /api/departments/<id>                    ←── حذف سلبي
POST   /api/departments/<id>/restore            ←── استرجاع
DELETE /api/departments/<id>/permanent          ←── حذف نهائي
POST   /api/departments/<id>/majors             ←── إضافة شعبة
DELETE /api/departments/<id>/majors/<major_id>  ←── حذف شعبة
```

### التدفق التفصيلي لـ `POST /api/departments` (إنشاء):
```
JSON body: {name, semesters, majors}
    │
    ▼
api_permission_required('departments.manage')
    │
    ▼
التحقق من القيم (semesters, majors = أرقام)
    │
    ├── ليست أرقام؟ → err('قيم الفصول والأقسام يجب أن تكون أرقاماً', 422)
    │
    ▼
التحقق من الاسم (موجود + طوله ≤ 255)
    │
    ├── فاضي؟ → err('اسم القسم مطلوب', 422)
    │
    ▼
department_exists_by_name() ←── فحص التكرار
    │
    ├── موجود؟ → err('القسم موجود مسبقاً', 409)
    │
    ▼
department_service.create_department()
    │
    ▼
log_history() ←── سجل العمليات
    │
    ▼
ok({'id': dept_id}, status=201)
```

### المتصل به:
```
api/departments.py
    │
    ├── api/helpers.py                               (api_permission_required, body, err, log_history, ok)
    ├── flask_db.py                                  (get_db)
    ├── security/csrf.py                             (csrf_required)
    ├── database/repositories/department_repository.py (DepartmentRepository.get_majors)
    └── services/department_service.py               (list_departments, create_department,
                                                      get_department, update_department,
                                                      department_delete, department_restore,
                                                      department_hard_delete,
                                                      department_exists_by_name,
                                                      add_major, delete_major)
```

---

## 8. `api/teachers.py` — إدارة أعضاء هيئة التدريس

**الملف:** `api/teachers.py` (174 سطر)
**Blueprint:** `api_teachers` — `url_prefix='/api/teachers'`

### الـ Endpoints:
```
GET    /api/teachers                ←── قائمة الأساتذة (pagination)
POST   /api/teachers                ←── إنشاء أستاذ (+ حساب مستخدم تلقائياً)
GET    /api/teachers/<id>           ←── تفاصيل أستاذ
PUT    /api/teachers/<id>           ←── تعديل بيانات + username + password
DELETE /api/teachers/<id>           ←── حذف سلبي
POST   /api/teachers/<id>/restore   ←── استرجاع
DELETE /api/teachers/<id>/permanent ←── حذف نهائي
```

### التدفق التفصيلي لـ `PUT /api/teachers/<id>` (تعديل):
```
JSON body: {name, email, phone, department_ids, username, new_password, ...}
    │
    ▼
api_permission_required('teachers.manage')
    │
    ▼
_teacher_form(data) ←── يجهز كل الحقول
    │
    ├── name, email, phone, department_id
    ├── specialization_id, academic_number, national_id
    ├── qualification_id, rank_id, classification_id
    ├── contract_date, tasks, specialization
    └── department_ids (list)
    │
    ▼
التحقق من الاسم
    │
    ├── فاضي؟ → err('الاسم مطلوب', 422)
    │
    ▼
فحص تكرار username الجديد (لو تغير)
    │
    ├── موجود؟ → err('اسم المستخدم موجود مسبقاً', 409)
    │
    ▼
teacher_service.update_teacher()
    │
    ▼
حذف teacher_departments القديمة + إضافة الجديدة (SQL مباشر)
    │
    ▼
teacher_service.update_teacher_credentials() (لو تغير username أو password)
    │
    ├── فشل؟ → err('تم تحديث البيانات لكن فشل تحديث بيانات الدخول', 200)
    │
    ▼
log_history() ←── سجل التعديل
    │
    ▼
ok(True)
```

### المتصل به:
```
api/teachers.py
    │
    ├── api/helpers.py               (api_login_required, api_permission_required, body,
    │                                 err, log_history, ok, pagination)
    ├── flask_db.py                  (get_db)
    ├── security/__init__.py         (current_user)
    ├── security/csrf.py             (csrf_required)
    └── services/teacher_service.py  (list_teachers, create_teacher, get_teacher,
                                      get_teacher_detail, update_teacher,
                                      update_teacher_credentials, teacher_delete,
                                      teacher_restore, teacher_hard_delete)
```

---

## 9. `api/rooms.py` — إدارة القاعات الدراسية

**الملف:** `api/rooms.py` (152 سطر)
**Blueprint:** `api_rooms` — `url_prefix='/api/rooms'`

### الـ Endpoints:
```
GET    /api/rooms             ←── قائمة القاعات (pagination)
POST   /api/rooms             ←── إنشاء قاعة
GET    /api/rooms/<id>        ←── تفاصيل قاعة
PUT    /api/rooms/<id>        ←── تعديل قاعة
DELETE /api/rooms/<id>        ←── حذف سلبي
POST   /api/rooms/<id>/restore ←── استرجاع
DELETE /api/rooms/<id>/permanent ←── حذف نهائي
```

### `_room_form(data)` (سطر 23-56) — الحقول المدعومة:
```
    │
    ├── name            ←── اسم القاعة (مطلوب)
    ├── code            ←── رمز القاعة
    ├── capacity        ←── السعة (رقم ≥ 1)
    ├── room_type_id    ←── نوع القاعة
    ├── status_id       ←── حالة القاعة
    ├── floor_id        ←── الطابق
    ├── building        ←── المبنى
    ├── department_id   ←── القسم (اختياري)
    └── computers       ←── كمبيوتر (0 أو 1)
```

### المتصل به:
```
api/rooms.py
    │
    ├── api/helpers.py                (api_login_required, api_permission_required,
    │                                  body, err, log_history, ok, pagination)
    ├── flask_db.py                   (get_db)
    ├── security/csrf.py              (csrf_required)
    └── services/classroom_service.py (list_rooms, create_room, get_room,
                                       get_room_detail, update_room, room_delete,
                                       room_restore, room_hard_delete)
```

---

## 10. `api/timetable.py` — الجدول الدراسي الأسبوعي

**الملف:** `api/timetable.py` (307 سطر)
**Blueprint:** `api_timetable` — `url_prefix='/api/timetable'`

### الـ Endpoints:
```
GET    /api/timetable                       ←── الجدول الأسبوعي الكامل
GET    /api/timetable/department             ←── جدول قسم محدد
POST   /api/timetable/entries                ←── إضافة حصة جديدة
PUT    /api/timetable/entries/<id>           ←── تعديل حصة
DELETE /api/timetable/entries/<id>           ←── حذف حصة
GET    /api/timetable/entries/<id>           ←── جلب حصة واحدة
POST   /api/timetable/report-error           ←── إبلاغ خطأ في الجدول
POST   /api/timetable/versions/create-next   ←── إنشاء نسخة للفصل القادم
GET    /api/timetable/available-rooms        ←── القاعات المتاحة (فحص التعارض)
GET    /api/timetable/available-teachers     ←── الأساتذة المتاحين (فحص التعارض)
```

### التدفق التفصيلي لـ `POST /api/timetable/entries` (إضافة حصة):
```
JSON body: {day, semester, period_code, course_id, teacher_id,
            room_id, department_id, start_time, end_time, lecture_type}
    │
    ▼
_entry_fields(body()) ←── يجهز الحقول
    │
    ▼
_entry_required(fields, include_department=True) ←── التحقق من الحقول المطلوبة
    │
    ├── [day, course_id, room_id, period_code, department_id, teacher_id]
    ├── ناقص؟ → err('جميع الحقول المطلوبة يجب ملؤها', 422)
    │
    ▼
_entry_times_valid(fields) ←── التحقق من الأوقات (start < end)
    │
    ├── خطأ؟ → err('وقت النهاية يجب أن يكون بعد وقت البداية', 422)
    │
    ▼
_is_hod()? ←── لرئيس القسم فقط: يتحقق أن القسم هو قسمه
    │
    ├── غير قسمه؟ → err('لا يمكن إنشاء حصص إلا في قسمك', 403)
    │
    ▼
timetable_service.ensure_current_version() ←── يتأكد أن هناك نسخة نشطة
    │
    ▼
timetable_service.create_entry() ←── services/timetable_service.py
    │
    ├── استثناء؟ → err('فشل حفظ الحصة', 400)
    │
    ▼
verify_entry() ←── التحقق من حفظ السجل فعلاً
    │
    ├── غير محفوظ؟ → err('فشل حفظ الحصة', 500)
    │
    ▼
_notify() ←── إشعار للمدرس ←── services/notification_service.py
    │
    ▼
ok({'id': entry_id}, status=201)
```

### المتصل به:
```
api/timetable.py
    │
    ├── api/helpers.py                    (api_permission_required, body, err, ok)
    ├── flask_db.py                       (get_db)
    ├── security/csrf.py                  (csrf_required)
    ├── services/timetable_service.py     (get_timetable_data, get_department_view,
    │                                      ensure_current_version, create_entry,
    │                                      update_entry, delete_entry, get_entry,
    │                                      verify_entry, create_version_for_next_semester,
    │                                      get_available_rooms, get_available_teachers)
    ├── services/notification_service.py  (get_teacher_user_id, create_notification)
    └── utils/format.py                   (semester_display_name)
```

---

## 11. `api/exams.py` — نظام الامتحانات (الأضخم والأكثر تعقيداً)

**الملف:** `api/exams.py` (692 سطر)
**Blueprint:** `api_exams` — `url_prefix='/api/exams'`

### الـ Endpoints (25+ endpoint):
```
GET    /api/exams                                      ←── بيانات الأقسام للامتحانات
GET    /api/exams/schedule                             ←── جدول الامتحانات + إحصائيات
GET    /api/exams/planning                             ←── بيانات التخطيط
GET    /api/exams/department-schedule                  ←── جدول قسم محدد
GET    /api/exams/department-schedule/cell-options      ←── خيارات الخلية (مقررات + قاعات)
POST   /api/exams/department-schedule/cell             ←── حفظ خلية امتحان
PATCH  /api/exams/department-schedule/cell/<id>/room    ←── تغيير القاعة فقط (دور امتحانات)
DELETE /api/exams/department-schedule/cell/<id>         ←── حذف خلية
POST   /api/exams/department-schedule/send              ←── إرسال الجدول للمراجعة
POST   /api/exams/department-schedule/send-exam         ←── إرسال امتحان واحد للمراجعة
POST   /api/exams/department-schedule/assign            ←── تعيين موعد امتحان لمادة
POST   /api/exams/planning/suggest                      ←── اقتراح توزيع تلقائي
POST   /api/exams/planning/apply-suggestions            ←── تطبيق الاقتراحات
POST   /api/exams/planning/assign                       ←── تعيين قاعة + وقت
POST   /api/exams/planning/publish                      ←── نشر الجدول النهائي
GET    /api/exams/settings                              ←── إعدادات الامتحانات
PUT    /api/exams/settings                              ←── حفظ الإعدادات
GET    /api/exams/halls                                 ←── قائمة القاعات
POST   /api/exams/halls                                 ←── إنشاء قاعة
PUT    /api/exams/halls/<id>                            ←── تعديل قاعة
GET    /api/exams/period                                ←── فترة الامتحانات
PUT    /api/exams/period                                ←── حفظ الفترة
POST   /api/exams/period/publish                        ←── نشر الفترة + إشعارات مدمجة
GET    /api/exams/semester-period                       ←── فصل الامتحانات الحالي
PUT    /api/exams/semester-period                       ←── حفظ تواريخ الفصل
POST   /api/exams/schedule/<id>/room                    ←── تحديث قاعة الامتحان
POST   /api/exams/conflicts                             ←── فحص التعارضات
```

### أهم الدوال المساعدة:
| الدالة | الأسطر | الوظيفة |
|--------|--------|---------|
| `_dept_exam_data_for_user(db)` | 27-35 | بيانات الامتحانات حسب دور المستخدم |
| `_notify_all(db, ...)` | 38-46 | إشعار جماعي لكل الأساتذة + رؤساء الأقسام |

### التدفق التفصيلي لـ `POST /api/exams/department-schedule/cell` (حفظ خلية):
```
JSON body: {dept_id, semester, week, day, course_id, room_id,
            start_time, end_time, exam_type, schedule_id}
    │
    ▼
api_permission_required('exams.department_schedule') + csrf_required
    │
    ▼
تعريف fk(key) ←── يحول القيم لـ int بأمان
    │
    ▼
تحقق الحقول الأساسية (dept_id, semester, week, course_id)
    │
    ├── ناقص؟ → err('بيانات غير صالحة', 422)
    │
    ▼
تحقق الأدوار:
    │
    ├── رئيس قسم + قسم غير قسمه؟ → err('لا يمكنك تعديل جدول قسم آخر', 403)
    ├── دور امتحانات؟            → err('حساب الامتحانات يمكنه تغيير القاعة فقط', 403)
    │
    ▼
تحقق القيم (week 1-5، day صحيح، start<end، exam_type صحيح)
    │
    ├── غير صحيحة؟ → err('...') بأكواد مختلفة
    │
    ▼
التحقق من وجود المادة والقاعة في قاعدة البيانات
    │
    ├── غير موجودة؟ → err('...', 404)
    │
    ▼
exam_service.resolve_exam_date(db, week, day)
    │
    ▼
exam_service.check_cell_conflicts(db, ...) ←── فحص التعارضات
    │
    ├── يوجد تعارض؟ → ok({'has_conflicts': True, 'conflicts': [...]})
    │
    ▼
exam_service.save_cell_exam(db, ...) ←── الحفظ الفعلي
    │
    ├── استثناء؟ → err(str(exc), 400)
    │
    ▼
ok({'saved': True, 'exam_date': ..., 'id': schedule_id})
```

### المتصل به:
```
api/exams.py
    │
    ├── api/helpers.py                (api_permission_required, body, err, ok)
    ├── flask_db.py                   (get_db)
    ├── security/__init__.py          (current_user)
    ├── security/csrf.py              (csrf_required)
    ├── services/exam_service.py      (build_dept_exam_data, build_exam_schedule_view,
    │                                  get_planning_data, get_department_courses,
    │                                  get_department_exam_assignments, resolve_exam_date,
    │                                  check_cell_conflicts, save_cell_exam,
    │                                  delete_cell_exam, update_exam_room,
    │                                  get_exam_rooms, suggest_distribution,
    │                                  assign_exam_resources, publish_schedule,
    │                                  get_exam_settings, save_exam_settings,
    │                                  get_exam_halls, hall_name_exists,
    │                                  create_exam_hall, update_exam_hall,
    │                                  get_exam_period, save_exam_period,
    │                                  publish_exam_period, save_exam_assignment,
    │                                  check_exam_conflicts)
    ├── services/notification_service.py (get_all_teacher_user_ids, get_hod_user_ids,
    │                                     get_exam_user_ids, notify_multiple)
    └── utils/format.py               (semester_display_name)
```

---

## 12. `api/history.py` — سجل العمليات

**الملف:** `api/history.py` (35 سطر)
**Blueprint:** `api_history` — `url_prefix='/api/history'`

### الـ Endpoints:
```
GET /api/history          ←── قائمة السجل (pagination)
GET /api/history/<id>     ←── تفاصيل سجل واحد
```

### التدفق:
```
api_permission_required('history.view')
    │
    ▼
pagination() ←── يقرأ page, per_page, search
    │
    ▼
history_service.list_history() ←── services/history_service.py
    │
    ▼
ok({items, total, page, per_page})
```

### المتصل به:
```
api/history.py
    │
    ├── api/helpers.py               (api_permission_required, err, ok, pagination)
    ├── flask_db.py                  (get_db)
    └── services/history_service.py  (list_history, get_history_detail)
```

---

## 13. `api/notifications.py` — الإشعارات

**الملف:** `api/notifications.py` (42 سطر)
**Blueprint:** `api_notifications` — `url_prefix='/api/notifications'`

### الـ Endpoints:
```
GET  /api/notifications              ←── إشعارات المستخدم + عدد غير المقروءة
GET  /api/notifications/unread-count ←── عدد غير المقروءة فقط
POST /api/notifications/read         ←── تعليم الكل كمقروء
```

### المتصل به:
```
api/notifications.py
    │
    ├── api/helpers.py                   (api_login_required, api_permission_required, ok)
    ├── flask_db.py                      (get_db)
    ├── security/csrf.py                 (csrf_required)
    └── services/notification_service.py (get_user_notifications, get_unread_count, mark_all_read)
```

---

## 14. `api/search.py` — البحث السريع (Autocomplete)

**الملف:** `api/search.py` (29 سطر)
**Blueprint:** `api_search` — `url_prefix='/api/search'`

### الـ Endpoint:
```
GET /api/search/courses?q=...&limit=8&dept_id=...
```

### التدفق:
```
query: q, limit, dept_id
    │
    ▼
api_permission_required('courses.view')
    │
    ▼
تحقق دور المستخدم (HOD = يقتصر على قسمه)
    │
    ▼
SearchService().suggest('courses', search, dept_filter, user_dept_id, limit)
    │
    ▼
ok({'items': rows})
```

### المتصل به:
```
api/search.py
    │
    ├── api/helpers.py             (api_permission_required, ok)
    └── services/search_service.py (SearchService.suggest)
```

---

## خريطة الاتصالات الكاملة لـ `api/`

```
                           ┌──────────────┐
                           │   app.py     │
                           │  (register)  │
                           └──────┬───────┘
                                  │
                           ┌──────▼───────┐
                           │ api/__init__ │
                           └──────┬───────┘
                                  │
         ┌────────┬───────┬───────┼───────┬────────┬──────────┐
         ▼        ▼       ▼       ▼       ▼        ▼          ▼
      ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────────┐
      │auth │ │dash │ │course│ │dept │ │teach│ │room │ │timetable│
      └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └────┬────┘
         │       │       │       │       │       │         │
         └───────┴───────┴───────┴───────┴───────┴─────────┘
                                  │
                           ┌──────▼───────┐
                           │  api/helpers │ ←── (كل الملفات تستخدمه)
                           └──────┬───────┘
                                  │
          ┌───────────────────────┼────────────────────────┐
          │                       │                        │
   ┌──────▼──────┐      ┌────────▼────────┐     ┌────────▼────────┐
   │  security/  │      │   services/     │     │  database/      │
   │ has_perm    │      │ user_service    │     │ history.py      │
   │ csrf        │      │ course_service  │     │ repositories/   │
   │ current_user│      │ teacher_service │     │                 │
   └─────────────┘      │ classroom_service│    └─────────────────┘
                        │ department_service│
                        │ timetable_service │
                        │ exam_service      │
                        │ history_service   │
                        │ notification_svc  │
                        │ search_service    │
                        │ dashboard_service │
                        └───────────────────┘
```

---

## قائمة الملفات المتصلة بـ `api/` مرتبة حسب الطبقة:

| الطبقة | الملفات |
|--------|---------|
| **Flask App** | `app.py` |
| **API Layer** | `api/__init__.py` + كل ملفات `api/*.py` |
| **Security** | `security/__init__.py`, `security/csrf.py`, `security/auth.py`, `security/authorization.py` |
| **Core** | `core/constants.py`, `core/rate_limiter.py`, `core/exceptions.py` |
| **Services** | `services/user_service.py`, `services/course_service.py`, `services/teacher_service.py`, `services/classroom_service.py`, `services/department_service.py`, `services/timetable_service.py`, `services/exam_service.py`, `services/history_service.py`, `services/notification_service.py`, `services/search_service.py`, `services/dashboard_service.py` |
| **Database** | `database/history.py`, `database/repositories/*.py` (كل ملفات repository) |
| **Config** | `flask_db.py`, `config.py` |
| **Utils** | `utils/format.py` |