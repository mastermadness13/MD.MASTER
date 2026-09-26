# newRopey

A Flask-based college management system with Arabic RTL support, role-based dashboards, timetable management, exam scheduling, course content and course plans, teacher messaging, faculty attendance, notifications, and basic audit/history features.

This README consolidates the most important information from the earlier project documentation into a single source of truth.

## Project Overview

newRopey is a web application for managing core academic and administrative operations at the College of Engineering Technology in Zuwara (كلية التقنية الهندسية زوارة). The system is built around a single Flask application and a SQLite database, with a mix of Bootstrap-based and Tailwind-based templates.

### Main Goals
- Manage users, departments, teachers, rooms, and courses
- Support timetable and exam scheduling workflows
- Manage course content and course plans per teacher
- Provide staff messaging workflows
- Track faculty attendance
- Provide role-based access for six staff roles

## Technology Stack

- Python 3.x
- Flask 3.x
- SQLite 3
- Jinja2 templates
- HTML/CSS/JavaScript
- Bootstrap 4.6 and Tailwind CDN
- Werkzeug security for password hashing

## Project Structure

- app.py: application factory, blueprint registration, database init
- config.py: runtime configuration
- navigation.py: role permissions and navigation items
- database/schema.sql: initial database schema definition
- database/schema.py + database/connection.py: database initialization, migrations, and helpers
- decorators.py: login, permission, and CSRF decorators
- helpers.py: shared helpers (current_user, pagination, stats)
- core/: constants, exceptions, base repository, rate limiter, validators
- repositories/: data access layer (one class per domain)
- services/: business logic layer (class-based services with repository injection)
- routes/: Flask blueprints (one per domain)
- templates/: HTML templates and reusable partials
- static/: CSS, JavaScript, and images
- uploads/: uploaded files (syllabi, materials, documents)
- docs/: historical documentation

## Core Features

### Implemented or Working
- User authentication and session-based login
- Password reset flow
- Role-based dashboards and access control
- User, department, teacher, room, and course management
- Weekly timetable display and scheduling workflows
- Exam scheduling, planning, hall distribution, and merging
- Course content submissions and review
- Course plan creation and management
- Teacher messaging (staff to head of department)
- Faculty attendance (managed by head of department)
- Notifications and history/audit logging
- Search, pagination, and basic reports
- HTML-to-PDF export tools

### Partially Implemented or Needs Improvement
- Teacher messaging workflows still need refinement
- Some exam workflow actions are still limited
- Frontend design is still mixed between Bootstrap and Tailwind patterns
- Automated test coverage: 70 pytest tests, all passing (pytest tests/ -q)

## Supported Roles

The system has five roles:

| Role | Arabic Label | Purpose |
|------|--------------|---------|
| research_development | قسم البحث والتطوير | View teachers, courses, timetable, and course content; publish course forms |
| faculty_affairs | مكتب هيئة التدريس | Manage teachers and faculty reports; office-manager account is the bootstrap user |
| head_of_department | رئيس القسم | Manage department timetable, messages |
| teacher | عضو هيئة تدريس | View own timetable, edit course content, manage course plans, uploads, messages |
| exam | الامتحانات | Manage exam scheduling, planning, halls, proctors, and department schedules |

(Note: the former `support_admin` and `super_admin` roles no longer exist; the
application implements the five roles above.)

## Database

The application uses SQLite and stores data in tables such as:

- users
- departments
- teachers
- rooms
- courses
- timetable
- exam_schedule
- exam_settings
- course_content_submissions
- teacher_messages
- teacher_materials
- teacher_documents
- teacher_requests
- faculty_attendance
- notifications
- history
- password_resets

The schema is defined in database/schema.sql and maintained at runtime through database/schema.py and database/connection.py.

## Installation

1. Open the project folder.
2. Create and activate a Python virtual environment.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the application:

```bash
python app.py
```

## Configuration Notes

- Set a strong secret key before production deployment.
- Review upload directory permissions for production.
- Change any default or seed credentials before exposing the app publicly.

## Security Notes

- Passwords are hashed using Werkzeug.
- Session-based authentication is used.
- Permission checks are enforced on protected routes.
- All POST forms require a CSRF token.
- Production deployments should add stronger password policy, secret management, and access review.

## Current Status Summary

The project is functionally usable for a college management workflow, focused on timetable, exams, course content, course plans, and staff workflows. The main priorities are:

- Refine messaging and exam workflows
- Improve testing coverage
- Consolidate the UI framework and reduce template duplication
- Refactor larger areas of the application for maintainability

## Recommended Next Steps

1. Harden authentication and authorization.
2. Improve data validation and error handling.
3. Add automated tests for critical flows.
4. Refactor the app into smaller modules as the project grows.

## Notes

This project was previously documented across many Markdown files. Those documents have been consolidated into this single README for easier maintenance.

---

## الدليل الشامل لاستخدام النظام (Complete User Guide)

### 1. نظرة عامة عن النظام

النظام هو تطبيق ويب متكامل لإدارة الكلية (كلية التقنية الهندسية زوارة) يشمل إدارة المستخدمين، الأقسام، أعضاء هيئة التدريس، المواد الدراسية، القاعات، الجداول الدراسية، الامتحانات، محتوى المواد، الخطط الدراسية، المراسلات. النظام مبني بلغة Python مع إطار Flask ويستخدم SQLite كقاعدة بيانات مع واجهة باللغة العربية (RTL).

### 2. الأدوار والصلاحيات (Roles & Permissions)

النظام يدعم 5 أدوار رئيسية:

| الدور | الوصف |
|---|---|
| **research_development** | قسم البحث والتطوير - عرض المحاضرين والمواد والجداول ومحتوى المواد ونشر نماذج المقررات |
| **faculty_affairs** | مكتب هيئة التدريس - إدارة شؤون المحاضرين والمواد وتقارير الأعضاء والإجازات (وهو الحساب الأساسي في النظام) |
| **head_of_department** | رئيس القسم - إدارة جدول القسم والمراسلات |
| **teacher** | عضو هيئة تدريس - الاطلاع على جدوله، تحرير محتوى المادة، إدارة الخطط الدراسية، رفع الملفات، المراسلات |
| **exam** | لجنة الامتحانات - إدارة جداول الامتحانات والتخطيط والقاعات والمراقبين |

كل صلاحية تحدد الصفحات التي يمكن للمستخدم الوصول إليها والبيانات التي يراها. خريطة الصلاحيات الكاملة موجودة في `navigation.py` (`ROLE_PERMISSIONS`).

### 3. شاشة الدخول (Login)

- المسار: `/login`
- المستخدم الافتراضي: `office_manager` / كلمة السر: `admin123` (قابلة للتغيير عبر متغير البيئة `ADMIN_PASSWORD` وحساب `admin` لرئيس القسم العام)
- حسابات المحاضرين المزروعة افتراضياً: `123456`
- عند الدخول يتم التحقق من صلاحية المستخدم وتوجيهه إلى لوحة التحكم الخاصة بدوره
- يوجد خيار "نسيت كلمة السر" لإعادة تعيين كلمة المرور

### 4. لوحات التحكم (Dashboards)

كل دور له لوحة تحكم خاصة تعرض إحصائيات مناسبة له:

- **faculty_affairs**: إحصائيات شاملة (الأقسام، المحاضرين، المواد، القاعات، المستخدمين، جداول الامتحانات)
- **research_development**: إحصائيات خاصة بقسم البحث والتطوير
- **head_of_department**: إحصائيات خاصة بقسمه فقط
- **teacher**: جدول محاضراته وإشعاراته
- **exam**: إحصائيات الامتحانات

### 5. إدارة الأقسام (Departments)

- المسار: `/departments`
- متاح لـ: exam (إدارة) — research_development (عرض)
- **القائمة**: جدول يعرض جميع الأقسام مع إمكانية البحث
- **إنشاء قسم**: إدخال اسم القسم، عدد الفصول الدراسية، عدد الشعب، دعم الشعب
- **تعديل قسم**: تغيير بيانات القسم
- **حذف نهائي**: إزالة القسم نهائياً
- **إدارة الشعب (المياجر)**: إضافة وحذف الشعب لكل قسم
الأقسام الافتراضية: القسم العام، قسم الاتصالات، قسم الحاسوب، قسم المدني، قسم المعماري، قسم النفط

### 6. إدارة المحاضرين (Teachers)

- المسار: `/teachers`
- متاح لـ: faculty_affairs (إدارة) — research_development, head_of_department (عرض)
- **القائمة**: جدول يعرض المحاضرين مع البحث بالاسم أو الرقم الكلية أو البريد، وتصفية حسب القسم، وترقيم الصفحات
- **إنشاء محاضر**: الاسم، البريد الإلكتروني، الهاتف، القسم، الرقم الكلية، الرقم الوطني، المؤهل العلمي، الرتبة الكلية، التصنيف، تاريخ التعاقد، المهام الموكلة
- **عرض التفاصيل**: صفحة تعرض معلومات المحاضر والمواد التي يدرسها
- **تعديل محاضر**: تغيير أي من المعلومات
- **حذف نهائي**: إزالة السجل نهائياً
- **إعادة تعيين كلمة السر** لحساب المحاضر

### 7. إدارة المواد الدراسية (Courses)

- المسار: `/courses`
- متاح لـ: research_development, faculty_affairs (إدارة) — teacher (عرض)
- **القائمة**: جدول يعرض المواد مع الكود، الاسم، القسم، السنة، الفصل الدراسي، والساعات النظرية والعملية والإجمالية
- **إنشاء مادة**: الكود، الاسم، القسم، السنة، الفصل الدراسي، الساعات، الاعتماد الكلية، المفردات، رفع ملف المنهج (syllabus)، المتطلبات السابقة (prerequisites)، الأيقونة
- **عرض التفاصيل**: معلومات المادة مع المتطلبات السابقة والمواد التابعة
- **تعديل مادة**: تغيير البيانات
- **حذف نهائي**: إزالة السجل نهائياً
### 8. إدارة القاعات الدراسية (Rooms / Classrooms)

- المسار: `/rooms`
- متاح لـ: exam (إدارة)
- **القائمة**: جدول يعرض القاعات مع الاسم، الكود، السعة، النوع، الموقع، المبنى، الحالة
- **إنشاء قاعة**: الاسم، الكود، السعة، النوع (قاعة محاضرات، مختبر، معمل حاسوب، استوديو، مسرح)، الحالة، الموقع، المبنى، الطابق، التجهيزات (أجهزة كمبيوتر، أجهزة إلكترونية، أرفف كتب، سبورات، بروجيكتور، مسرح، مقاعد، محطات عمل)، قابلية الحجز
- **عرض التفاصيل**: معلومات القاعة مع التجهيزات
- **تعديل قاعة**: تغيير البيانات
- **حذف نهائي**: إزالة السجل نهائياً
### 9. إدارة المستخدمين (Users)

- المسار: `/teachers` (إدارة الحسابات من ملف المحاضر)
- متاح لـ: faculty_affairs
- **القائمة**: جدول يعرض المستخدمين (اسم المستخدم، البريد الإلكتروني، الدور، القسم، تاريخ الإنشاء) مع بحث وتصفية
- **إنشاء مستخدم**: اسم المستخدم، كلمة السر، الدور، القسم
- **تعديل مستخدم**: تغيير البيانات والدور
- **حذف مستخدم**: لا يمكن حذف المستخدم نفسه
- **عرض الملف الشخصي**: معلومات المستخدم كاملة

### 10. الجدول الدراسي (Timetable)

- المسار: `/timetable`
- متاح لـ: جميع الأدوار (لكل دور ما يناسبه)
- **عرض الجدول الرئيسي**: جدول أسبوعي يعرض الأيام مقابل الفترات (A, B, C) مع المادة، المحاضر، القاعة، الشعبة، والقسم
- **إنشاء محاضرة**: اختيار اليوم، الفترة، المادة، المحاضر، القاعة، القسم، الشعبة مع التحقق من عدم تعارض القاعة أو المحاضر
- **تعديل محاضرة**: تغيير بيانات المحاضرة
- **حذف محاضرة**: إزالة محاضرة من الجدول
- **جدول المحاضر الشخصي**: يعرض جدول محاضر معين بكامل محاضراته
- **جدول حسب القسم**: عرض الجدول مصفى حسب القسم
- **جدول الامتحانات**: عرض جدول الامتحانات في قالب زمني
- **طباعة الجدول**: نسخة قابلة للطباعة

### 11. إدارة الامتحانات (Exams)

- المسار: `/exams`
- متاح لـ: exam (إدارة كاملة) — super_admin, head_of_department, teacher (عرض حسب الصلاحية)
- نظام متكامل لإدارة الامتحانات يشمل:

**أ. إعدادات الامتحانات** (`/exams/settings`):
- تاريخ بداية الامتحانات ونهايتها، أوقات الجلسات (A, B, C)، عدد المراقبين لكل قاعة، حالة الفترة

**ب. جدولة الامتحانات للقسم** (`/exams/department-schedule`):
- رئيس القسم يعين تاريخ امتحان لكل مادة مع وقت البدء والنهاية

**ج. تخطيط الامتحانات** (`/exams/planning`):
- توزيع الامتحانات على القاعات، عرض بياني حسب اليوم والقاعة، اقتراح توزيع تلقائي، نشر الجدول النهائي

**د. دمج الامتحانات** (`/exams/merge`):
- دمج جداول امتحانات الأقسام في جدول واحد موحد

**هـ. إدارة القاعات الامتحانية** (`/exams/halls`):
- إضافة وتعديل قاعات الامتحانات

**و. التوزيع على القاعات** (`/exams/hall-distribution`):
- توزيع الامتحانات على القاعات والمبانـي

**ز. المراقبون** (`/exams/proctors`):
- إدارة المراقبين وتوزيعهم

**ح. التقارير** (`/exams/reports`):
- تقارير عن جداول الامتحانات

**ط. توقيع رئيس القسم**: يمكن لرئيس القسم التوقيع على جداول الامتحانات بعد المراجعة (حالة الجدول: draft/submitted/received/merged/published)

### 12. محتوى المادة (Course Content)

- المسار: `/teacher/course-content`
- متاح لـ: teacher (تحرير) — faculty_affairs, exam (عرض) — research_development (مراجعة/نشر)
- المحاضر يرسل محتوى المادة (الأهداف، المتطلبات، المقررات، الساعات، وغيرها) كتسليم (submission)
- قسم البحث والتطوير يراجع التسليمات عبر `/teacher/super-admin/course-content` مع إمكانية قبولها أو نشرها أو إرجاعها مع ملاحظات
- رئيس القسم يطلع على ملفات المحاضرين من `/hod/materials`

### 13. حضور أعضاء هيئة التدريس (Faculty Attendance)

- نظام لحضور وغياب أعضاء هيئة التدريس (`faculty_attendance`)
- يمكن لرئيس القسم تحديث حالة الحضور للمحاضرين في قسمه

### 14. المراسلات والطلبات (Messages & Requests)

- متاح لـ: teacher, head_of_department
- **رفع الملفات** (`/teacher/upload`): المحاضر يرفع ملفاته (مستندات، محاضرات، إلخ) مع نوع الملف (منهج، محاضرات، امتحانات، كشوف درجات، أخرى)
- **المراسلات** (`/teacher/messages`): المحاضر يرسل رسائل واستفسارات وطلبات لرئيس القسم
- **الرد على المراسلات** (`/hod/messages`): رئيس القسم يعرض ويرد على طلبات المحاضرين
- **ملفات المحاضرين** (`/hod/materials`): رئيس القسم يطلع على ملفات المحاضرين وينزلها

### 15. الإشعارات (Notifications)

- متاح لـ: جميع المستخدمين المسجلين
- تعرض في الشريط العلوي (أيقونة الجرس)
- كل إشعار له: عنوان، رسالة، نوع، تاريخ
- يمكن وضع علامة "مقروء" على الإشعارات

### 16. الطباعة (Print)

- `/print/timetable`: طباعة الجدول الدراسي
- `/print/courses`: طباعة قائمة المواد

### 17. كيف يعمل النظام (Architecture)

**سير العمل العام**:
1. المستخدم يفتح الموقع → يتم توجيهه إلى `/login`
2. بعد إدخال بيانات الدخول الصحيحة → يتم حفظ الجلسة (session) وتوجيهه إلى لوحة التحكم الخاصة بدوره
3. كل صفحة تتحقق من صلاحية المستخدم عبر `@permission_required`
4. العمليات (إضافة، تعديل، حذف) تسجل في سجل التدقيق (history)
5. الدعم موجود للحذف الناعم (soft delete) في الكيانات الرئيسية

**هيكل البرمجة**:
- `routes/`: المسارات مقسمة إلى 24 blueprints (واحد لكل نطاق)
- `services/`: طبقة الخدمات (17 وحدة) التي تتعامل مع قاعدة البيانات
- `repositories/`: طبقة الوصول للبيانات (15 مخزناً)
- `database/schema.py` و `database/connection.py`: تهيئة قاعدة البيانات وترحيلاتها
- `templates/`: قوالب HTML مقسمة حسب الميزة

**حماية CSRF**: جميع نماذج POST تحتوي على رمز CSRF للحماية

### 18. المشاكل المعروفة والقيود (Known Issues)

1. **المراسلات**: نظام المراسلات بين المحاضرين ورؤساء الأقسام يحتاج إلى تحسين
2. **الواجهة الأمامية**: خليط بين Bootstrap و Tailwind - يحتاج إلى توحيد
3. **الامتحانات**: بعض إجراءات سير عمل الامتحانات لا تزال محدودة
4. **الاختبارات**: لا توجد تغطية اختبارية كافية
5. **تكرار القوالب**: بعض القوالب مكررة ويجب دمجها
6. **الجدول الدراسي**: لا توجد أداة استيراد جماعي للجدول - الإنشاء محاضرة بمحاضرة
```markdown
# شرح تفصيلي لمنظومة «أكواد المقررات ومحتوى المقرر»

> **ملف مرجعي شامل** يربط بين: `courses.py`، `teacher_pages.py`، `course_content_service.py`، `course_content.py`، `schema.sql`، `courses_list.js`، وصفحة `courses/codes.html`.

---

## فهرس المحتويات

1. [نظرة عامة معمارية](#1-نظرة-عامة-معمارية)
2. [خريطة الملفات وعلاقاتها](#2-خريطة-الملفات-وعلاقاتها)
3. [تحليل ملف courses.py](#3-تحليل-ملف-coursespy--سطرًا-بسطر)
4. [تحليل build_course_content_form_context](#4-تحليل-build_course_content_form_context-في-teacher_pagespy)
5. [تحليل course_content_service.py](#5-تحليل-course_content_servicepy--آلة-الحالة)
6. [تحليل courses/codes.html](#6-تحليل-coursescodeshtml)
7. [تحليل courses_list.js](#7-تحليل-courses_listjs--العلاقة-بالصفحة-الأخرى)
8. [تحليل schema.sql](#8-تحليل-schemasql--العلاقات)
9. [تحليل course_content.py](#9-تحليل-course_contentpy--api-للبحث-السريع)
10. [المشاكل المحتملة المُجمّعة](#10-المشاكل-المحتملة-المُجمّعة)
11. [تدفق العمل الكامل End-to-End](#11-تدفق-العمل-الكامل-end-to-end)
12. [العلاقات بين الملفات مصفوفة](#12-العلاقات-بين-الملفات-مصفوفة)
13. [توصيات الإصلاح](#13-توصيات-الإصلاح)
14. [خلاصة العلاقة الوظيفية](#14-خلاصة-العلاقة-الوظيفية)

---

## 1) نظرة عامة معمارية

النظام مبني على طبقات متتابعة:

```
Route (Blueprint)  →  Service Layer  →  Database (SQLite)  →  Template (Jinja)  →  JS
     courses.py         course_content_service.py    schema.sql      codes.html       courses_list.js
     teacher_pages.py
     api/course_content.py
```

**الفكرة المحورية:** صفحة `/courses/codes` هي الواجهة الموحّدة التي تجمع ثلاثة أنماط تحرير في تبويبات:

| التبويب | المعرّف | الغرض |
|---------|---------|-------|
| `inline` | `codesInlineForm` | تعديل الأكواد سطرًا بسطر |
| `paste` | `codesPasteForm` | لصق جماعي (كود + اسم) |
| `content` | `codesContentPanel` | نموذج مفردات المقرر (Course Content Sheet) |

---

## 2) خريطة الملفات وعلاقاتها

```
┌───────────────────────────────────────────────────────────────────────┐
│                         courses.py (Blueprint)                        │
│  url_prefix='/courses'                                                │
│                                                                       │
│  courses_list()      → /courses            → list.html + courses_list.js│
│  courses_codes()     → /courses/codes      → codes.html               │
│  courses_create()    → /courses/create     → create.html              │
│  courses_edit()      → /courses/edit/<id>  → edit.html                │
│  courses_delete()    → /courses/delete/<id>                           │
│  courses_bulk_delete()                                                │
│  courses_api_move()  → /courses/api/move   → api/courses.py           │
└──────────────┬────────────────────────────────────────────────────────┘
               │ يستدعي
               ▼
┌───────────────────────────────────────────────────────────────────────┐
│           teacher_pages.py (Blueprint url_prefix='/teacher')          │
│                                                                       │
│  build_course_content_form_context(db, course_id, submission_id)      │
│      ↓                                                                │
│  super_admin_course_content_send()  →  /teacher/super-admin/.../send  │
│      ↓ يستدعي                                                         │
│  transition_submission() / publish_directly()  ← course_content_service│
└──────────────┬────────────────────────────────────────────────────────┘
               │ يعتمد على
               ▼
┌───────────────────────────────────────────────────────────────────────┐
│           course_content_service.py (State Machine)                   │
│                                                                       │
│  TRANSITIONS = {(from, action): to}                                   │
│  transition_submission()  → خطوة واحدة                                │
│  publish_directly()       → سلسلة في معاملة واحدة                     │
│  copy_submission_as_draft()→ نسخة جديدة                               │
│  pdf_state_for()          → حالة عمود الملف                           │
└──────────────┬────────────────────────────────────────────────────────┘
               │ يقرأ/يكتب
               ▼
┌───────────────────────────────────────────────────────────────────────┐
│                         schema.sql (SQLite)                           │
│                                                                       │
│  course_content_submissions   course_content_curriculum               │
│  course_content_transitions   course_files   courses   departments    │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 3) تحليل ملف `courses.py` — سطرًا بسطر

### 3.1 الاستيرادات والتهيئة

```python
bp = Blueprint('courses', __name__, url_prefix='/courses')
```
- كل المسارات تبدأ بـ `/courses`.
- يعتمد على: `course_service`، `build_course_content_form_context` من `teacher_pages`.

### 3.2 دالة `_build_placements(form)`

```python
def _build_placements(form):
```
**الغرض:** استخراج الأقسام المرتبطة بالمقرر من نموذج HTML.

**الاستراتيجية (متدرجة):**

1. **أولاً:** حقل `placements` بصيغة JSON (الأحدث والأفضل):
   ```json
   [{"department_id": 1, "semester": 3}, ...]
   ```
2. **ثانيًا (Fallback):** `department_ids[]` + `dept_semester[]` كقائمتين متوازيتين.
3. **ثالثًا (توافق قديم):** إرجاع قائمة IDs صحيحة فقط.

> ⚠️ **مشكلة محتملة:** إذا كان `placements_json` صالحًا لكن قائمة الأقسام فارغة (`placements=[]`)، يعود للـ `department_ids` القديمة. لكن إذا اختلطت البيانات (JSON صالح + IDs قديمة)، الأولوية للـ JSON وقد تُهمل IDs مقصودة.

### 3.3 دالة `_codes_dataset(db, dept_id)`

```python
def _codes_dataset(db, dept_id):
```
- تنفذ استعلام SQL واحد يجلب:
  - `id`, `code`, `name`, `year`
  - `depts` = أسماء الأقسام مجمّعة بـ `GROUP_CONCAT(d.name, '، ')`
  - `dept_ids` = معرّفات الأقسام مجمّعة بـ `GROUP_CONCAT(cd3.department_id, ',')`

> ⚠️ **مشكلة محتملة:** `GROUP_CONCAT` بدون `ORDER BY` يعتمد على ترتيب SQLite العشوائي — لا ترتيب مضمون. الحل: `GROUP_CONCAT(d.name || ':' || cd2.department_id ORDER BY d.name)`.

### 3.4 دالة `_validate_code_updates(db, updates)`

```python
def _validate_code_updates(db, updates):
```
**يفحص ثلاث حالات:**

1. كود فارغ → خطأ.
2. طول > 40 → خطأ.
3. تكرار داخل الدفعة → خطأ.
4. تعارض مع قاعدة البيانات (لمقررات خارج التعديل) → خطأ.

**الاستعلام المهم:**
```sql
SELECT code FROM courses WHERE deleted_at IS NULL
AND code IN (?,?,...) AND id NOT IN (?,?,...)
```

> ⚠️ **مشكلة:** المعاملات تُمرر كـ `list(clean.values()) + list(clean.keys())` — هذا صحيح فقط إذا كانت `clean` بنفس الطول في القائمتين. بما أن `clean` dict فالقيم والمفاتيح بنفس الطول، لكن الترتيب يعتمد على ترتيب الإدراج. المنطق صحيح.

### 3.5 المسار الرئيسي `courses_codes()`

```python
@bp.route('/codes', methods=['GET', 'POST'])
@login_required
@permission_required('courses.manage')
@csrf_required
def courses_codes():
```

**التدفق:**

```
GET  → عرض الصفحة (tab=inline افتراضيًا)
POST → معالجة (inline code_N أو bulk_text) ثم redirect (PRG pattern)
```

**أ) تحديد `tab`:**
```python
tab = request.form.get('tab', request.args.get('tab', 'inline'))
if tab != 'content':
    tab = 'inline'
```
- تبويب `content` يحتاج صلاحية `course_content.manage`.
- أي قيمة أخرى → `inline`.

**ب) بناء سياق المحتوى:**
```python
if tab == 'content' and can_manage_content:
    cid = request.form.get('course_id', ..., type=int) or None
    sid = request.form.get('submission_id', ..., type=int) or None
    ctx = build_course_content_form_context(db, course_id=cid, submission_id=sid)
```

**ج) معالجة POST:**
- **نمط `bulk_text`:** يحاول فصل كل سطر بـ `\t | ، ,` (بالترتيب).
- **نمط `code_N`:** يستخرج المفاتيح ويبني `updates`.

> ⚠️ **مشكلة محتملة في `bulk_text`:**
> ```python
> for sep in ('\t', '|', '،', ','):
>     if sep in line:
>         parts = line.split(sep, 1)
>         break
> ```
> - إذا كان الاسم يحتوي فاصلة عربية (مثل: "رياضيات، متقدمة")، سيُقسّم خطأً. الحل: تجربة جميع الفواصل واختيار الأكثر منطقية، أو استخدام `،` فقط كفاصل مع `\t`.

**د) التحقق والتنفيذ:**
```python
errors, clean = _validate_code_updates(db, updates)
if errors: flash...
else:
    for cid, code in clean.items():
        row = db.execute('SELECT code FROM courses WHERE id = ?', (cid,)).fetchone()
        if row and _normalize_code(row['code']) != code:
            db.execute('UPDATE courses SET code = ? WHERE id = ?', (code, cid))
            add_history(...)
            changed += 1
    db.commit()
```

> ⚠️ **مشكلة:** لا يوجد `WHERE deleted_at IS NULL` في `SELECT code` — قد يُحدّث مقررًا محذوفًا ناعمًا إذا كان `cid` من نموذج قديم.

**هـ) Redirect بعد POST:**
```python
if embed:
    return redirect(url_for('courses.courses_list', view='codes'))
return redirect(url_for('courses.courses_codes', dept=dept_id or None))
```
- نمط PRG (Post/Redirect/Get) يمنع إعادة الإرسال عند التحديث.

---

## 4) تحليل `build_course_content_form_context()` في `teacher_pages.py`

```python
def build_course_content_form_context(db, course_id=None, submission_id=None):
```

**ثلاث حالات:**

### الحالة 1: `submission_id` موجود → تحميل من قاعدة البيانات

```python
sub = db.execute('''SELECT s.*, COALESCE(d.name, '') AS department_name
    FROM course_content_submissions s
    LEFT JOIN departments d ON s.department_id = d.id
    WHERE s.id = ?''', (submission_id,)).fetchone()
```
- يبني `doc` من حقول التسليم مباشرة.
- يجلب `curriculum` من `course_content_curriculum`.
- يقسمها إلى `theoretical_curriculum` و `practical_curriculum`.

### الحالة 2: `course_id` موجود → بناء من بيانات المقرر

```python
context = _course_context_course_only(db, course_id)
doc = {
    'course_name': context['course_name'],
    'course_code': context['course_code'],
    'credits': context['credits'],
    ...
    'course_objective': '',  # فارغ — يُملأ يدويًا
}
curriculum = []
```
- نموذج فارغ جاهز للتحرير.
- ⚠️ **ملاحظة:** لا يجلب النموذج السابق المنشور — سينشئ `submission` جديد عند الحفظ.

### الحالة 3: لا شيء → وضع الإنشاء

- `doc` فارغ بالكامل.
- `courses` = قائمة كل المقررات للاختيار.

**النتيجة النهائية:**
```python
return {
    'doc': doc,
    'courses': courses,
    'curriculum': curriculum,
    'theoretical_curriculum': theoretical_curriculum,
    'practical_curriculum': practical_curriculum,
    'page_mode': 'edit' if submission_id else 'create',
    'edit_submission_id': submission_id,
    'academic_periods': academic_periods,
    'default_period_id': _current_academic_period_id(academic_periods),
}
```

---

## 5) تحليل `course_content_service.py` — آلة الحالة

### 5.1 الحالات المُعرّفة

```python
DRAFT, PENDING_TEACHER, PENDING_RND, PENDING_HOD, PENDING_EXAM,
APPROVED, REJECTED, PUBLISHED, ARCHIVED
```

### 5.2 جدول الانتقالات `TRANSITIONS`

```python
TRANSITIONS = {
    (DRAFT, 'save'): DRAFT,
    (DRAFT, 'submit'): PENDING_RND,
    (PENDING_TEACHER, 'save'): PENDING_TEACHER,
    (PENDING_TEACHER, 'submit'): PENDING_RND,
    (PENDING_RND, 'approve'): APPROVED,
    (PENDING_RND, 'reject'): REJECTED,
    (REJECTED, 'save'): REJECTED,
    (REJECTED, 'submit'): PENDING_RND,
    (APPROVED, 'publish'): PUBLISHED,
    (PUBLISHED, 'archive'): ARCHIVED,
}
```

**رسم بياني:**

```
DRAFT ──submit──► PENDING_RND ──approve──► APPROVED ──publish──► PUBLISHED ──archive──► ARCHIVED
  ▲                    │                                                  ▲
  │                    reject                                             │
  │                    ▼                                                  │
  └────save──── REJECTED ──submit──────────────────────────────────────────┘
```

> ⚠️ **حالة مفقودة:** لا يوجد `(PENDING_TEACHER, 'approve')` — إذا دخل نموذج في هذه الحالة، سيرفض `_validate_step` أي إجراء لاحق.

> ⚠️ **مشكلة:** لا يوجد مسار من `PENDING_HOD` أو `PENDING_EXAM` — فهي حالات «ميتة» في الجدول الحالي (موروثة من نظام قديم متعدد المراحل). أي محاولة `transition_submission` منها سترمي `TransitionNotAllowed`.

### 5.3 دالة `_validate_step()`

```python
def _validate_step(db, submission_id, action, actor_role, weeks_total):
```

**تتحقق من:**

1. الإجراء ضمن القائمة المسموحة.
2. الدور يملك الصلاحية المناسبة:
   - `approve`/`reject` → `REVIEW_ROLES = {'research_development'}`
   - `publish` → `PUBLISH_ROLES = {'research_development'}`
   - `archive` → `ARCHIVE_ROLES = {'research_development'}`
3. مجموع الأسابيع ≤ 12 عند `submit`/`approve`/`publish`.

> ⚠️ **مشكلة محتملة:** `_validate_step` لا يتحقق من وجود `submission_id` — هذا يتم في `transition_submission` لاحقًا. لكن `_validate_step` يُستدعى أولاً، فإذا فشل التحقق بسبب صلاحية، لا يُتحقق من وجود التسليم أصلاً.

### 5.4 دالة `_apply_transition()`

```python
def _apply_transition(db, row, action, next_status, actor_role, *,
                      review_notes='', actor_user_id=None, commit=True):
```

**تكتب في قاعدة البيانات حسب الإجراء:**

- `reject`: يتحقق من وجود `review_notes` (يرفض إذا فارغ).
- `approve`: يسجل `reviewed_by` و `reviewed_at`.
- `publish`: يسجل `published_at`.
- `archive`: يسجل `archived_at`.
- `submit`: يسجل `submitted_at` (فقط إذا كان NULL).
- `save`: يحدّث `updated_at` فقط.

ثم:
```python
db.execute('INSERT INTO course_content_transitions ...')
```
> ⚠️ **مشكلة:** `course_content_transitions` يحتاج `from_status` — يُؤخذ من `row['status']` وهو الحالة قبل التطبيق. صحيح.

### 5.5 دالة `transition_submission()`

```python
def transition_submission(db, submission_id, action, actor_role, ...):
    _validate_step(db, submission_id, action, actor_role, weeks_total)
    row = db.execute('SELECT * FROM course_content_submissions WHERE id = ?', ...).fetchone()
    if not row: raise SubmissionNotFound(...)
    next_status = TRANSITIONS.get((row['status'], action))
    if next_status is None: raise TransitionNotAllowed(...)
    if not _can_operate(actor_role, row['status'], action):
        raise RoleNotAllowed(...)
    _apply_transition(...)
    return db.execute('SELECT * FROM ... WHERE id = ?', ...).fetchone()
```

### 5.6 دالة `publish_directly()`

```python
def publish_directly(db, submission_id, actor_role, *, weeks_total=0, actor_user_id=None):
```

**الاستراتيجية الذكية:** تبني سلسلة الخطوات المطلوبة من الحالة الحالية، ثم تتحقق من الكل *قبل* أي كتابة، ثم تنفذها في معاملة واحدة.

```python
if current == PUBLISHED: chain = []
elif current == APPROVED: chain = [('publish', PUBLISHED)]
elif current == PENDING_RND: chain = [('approve', APPROVED), ('publish', PUBLISHED)]
elif current in (DRAFT, PENDING_TEACHER, REJECTED):
    chain = [('submit', PENDING_RND), ('approve', APPROVED), ('publish', PUBLISHED)]
else: raise TransitionNotAllowed(...)
```

**التحقق المسبق:**
```python
for action, target in chain:
    _validate_step(...)
    if TRANSITIONS.get((current, action)) != target: raise ...
    if not _can_operate(...): raise ...
    current = target
```

**التنفيذ:**
```python
try:
    for action, target in chain:
        _apply_transition(db, row, action, target, ..., commit=False)
        row = db.execute('SELECT * ...').fetchone()
    db.commit()
except Exception:
    db.rollback()
    raise
```

> ⚠️ **مشكلة محتملة:** `_apply_transition` مع `commit=False` لا يزال ينفذ `db.execute` (INSERT/UPDATE). في SQLite مع `isolation_level` افتراضي، هذه ضمن معاملة تلقائية. `db.rollback()` يعمل بشكل صحيح *إذا* لم تكن هناك `commit` ضمنية داخل `_apply_transition`. لكن `commit=False` يمنع ذلك.

### 5.7 دالة `pdf_state_for()`

```python
def pdf_state_for(submission_status='', has_downloadable_form=False):
    if has_downloadable_form: return PDF_STATE_AVAILABLE
    return _PDF_STATE_FROM_SUBMISSION.get(submission_status or '', PDF_STATE_NONE)
```

**القاعدة:** وجود ملف قابل للتحميل يسبق كل شيء. تُستدعى من `super_admin_course_content_list` لبناء عمود «الملف».

---

## 6) تحليل `courses/codes.html`

### 6.1 البنية العامة

```html
<form id="codesInlineForm" ... style="display: none;">
    <!-- جدول الأكواد السطرية -->
</form>

<form id="codesPasteForm" ... style="display:none">
    <!-- textarea للصق -->
</form>

<div id="codesContentPanel" style="">
    <!-- نموذج مفردات المقرر الكامل -->
</div>
```

### 6.2 جافاسكربت التحويل بين التبويبات

```javascript
function switchCodesView(mode) {
    var inlineEl = document.getElementById('codesInlineForm');
    var pasteEl = document.getElementById('codesPasteForm');
    var contentEl = document.getElementById('codesContentPanel');
    inlineEl.style.display = (mode === 'inline') ? '' : 'none';
    if (pasteEl) pasteEl.style.display = (mode === 'paste') ? '' : 'none';
    if (contentEl) contentEl.style.display = (mode === 'content') ? '' : 'none';
    // ... تبديل الأصناف
}
switchCodesView("content");  // ← هنا المفتاح!
```

> ⚠️ **مشكلة واضحة جدًا:** السطر الأخير يستدعي `switchCodesView("content")` — أي أن الصفحة *دائمًا* تفتح على تبويب المحتوى، بغض النظر عن قيمة `tab` الممررة من الخادم.

**التأثير:** عند زيارة `/courses/codes` بدون `tab=content`، لا يزال التبويب النشط هو المحتوى. هذا قد يكون مقصودًا (لأن الصفحة أصبحت أساسًا لنموذج المحتوى)، لكنه يخالف منطق `tab` في الخادم.

**الحل المقترح:**
```javascript
switchCodesView("{{ tab|default('inline') }}");
```

### 6.3 نموذج المحتوى (Content Panel)

يحتوي على:

- **حقول المقرر:** `course_name`, `course_code`, `credits`, `semester`, `theory_hours`, ...
- **جدول المنهج النظري:** `theoretical_curriculum_topic[]`, `theoretical_curriculum_weeks[]`, ...
- **حقول المنهج العملي:** `practical_content`
- **حقول إنجليزية:** `course_name_en`, `course_objective_en`, ...

> ⚠️ **ملاحظة:** `<input type="hidden" name="course_id" value="57">` — قيمة صلبة! هذا يعني أن الصفحة المُصيَّرة من الخادم مرتبطة بمقرر رقم 57. في حالة `submission_id` مختلف، يجب أن يتغير هذا.

---

## 7) تحليل `courses_list.js` — العلاقة بالصفحة الأخرى

هذا الملف يخص صفحة `/courses` (القائمة)، *وليس* `/courses/codes`. لكن هناك علاقة:

### 7.1 دالة `contentBtns(c)`

```javascript
function contentBtns(c) {
    var cc = COURSE_CONTENT[c.id] || {};
    if (cc.form) html += '<a href="/course-file/' + cc.form.id + '?download=1" ...>...</a>';
    if (IS_RD) {
        var href = cc.form ? '/teacher/super-admin/course-content/' + cc.form.id
                           : '/courses/codes?tab=content&course_id=' + c.id;
        html += '<a href="' + href + '" ...>...</a>';
    }
}
```

**العلاقة المباشرة:** عند النقر على «إنشاء/تعديل المقرر»، يتم التوجيه إلى `/courses/codes?tab=content&course_id=N`. هذا هو نقطة الاتصال الرئيسية.

### 7.2 دالة `switchCodesEditorMode(mode)`

```javascript
function switchCodesEditorMode(mode) {
    var inline = document.getElementById('codesInlineForm');
    var paste = document.getElementById('codesPasteForm');
    ...
}
```
> ⚠️ **تكرار:** هذه الدالة موجودة في `courses_list.js` *وأيضًا* دالة `switchCodesView` موجودة في `codes.html` مباشرة. قد يحدث تعارض إذا حُمّل الملفان في نفس الصفحة (والذي لا يحدث عادة، لكنه خطر كامن).

---

## 8) تحليل `schema.sql` — العلاقات

### 8.1 الجداول الأساسية

```sql
course_content_submissions (
    id, teacher_id, user_id, department_id, course_id,
    course_name, course_code, credits, semester,
    theory_hours, practical_hours, tutorial_hours, total_hours,
    course_objective, prerequisites, textbooks, notes,
    practical_content, practical_content_en,
    study_type, section_id, teacher_name,
    filename, original_filename, file_size,
    status, submitted_to, submitted_at,
    reviewed_by, reviewed_at, review_notes,
    course_name_en, course_objective_en,
    prerequisites_en, textbooks_en, notes_en,
    created_at, updated_at
)
```

> ⚠️ **مشكلة:** الأعمدة `version_label`, `parent_submission_id`, `published_at`, `archived_at` **غير موجودة** في `schema.sql`! لكن `course_content_service.py` يستخدمها:

```python
ident_cols = [c for c in
              ('version_label', 'parent_submission_id', 'published_at', 'archived_at')
              if c in cols]
```

هذا يعني:

- إما أنها تُضاف عبر `_safe_add_column` في `database/schema.py` (مذكورة في تعليق نهاية `schema.sql`).
- أو أن `copy_submission_as_draft` ستفشل إذا لم تكن موجودة.

**التعليق في نهاية `schema.sql`:**
```sql
-- Created/migrated by ensure_schema (database/schema.py) on every startup.
-- course_content_submissions.academic_period_id / course_files.academic_period_id
-- reference this table (added via _safe_add_column for existing DBs).
```
يشير إلى `academic_period_id` فقط، وليس `version_label`. **هذه فجوة خطيرة**.

### 8.2 جدول `course_content_curriculum`

```sql
CREATE TABLE course_content_curriculum (
    id INTEGER PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES course_content_submissions(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    weeks INTEGER DEFAULT 1,
    content TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    section TEXT DEFAULT 'theoretical'
);
```

**العلاقة:** حذف التسليم → حذف كل صفوف المنهج تلقائيًا (CASCADE).

> ⚠️ **مشكلة:** `topic TEXT NOT NULL` — إذا أرسل المستخدم نموذجًا بحقل موضوع فارغ، سيفشل الإدراج. `_curriculum_from_form` يتحقق من `if (topic or '').strip():` لكن قد يكون هناك مسار آخر (في `super_admin_course_content_send`) لا يتحقق.

### 8.3 جدول `course_content_transitions`

```sql
CREATE TABLE course_content_transitions (
    id INTEGER PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES course_content_submissions(id) ON DELETE CASCADE,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    action TEXT NOT NULL,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**الغرض:** سجل تدقيق كامل لكل انتقال.

> ⚠️ **مشكلة:** لا يوجد فهرس على `created_at` — استعلامات التقارير الزمنية قد تكون بطيئة.

### 8.4 جدول `course_files`

```sql
CREATE TABLE course_files (
    id, course_id, file_type, filename, original_filename, file_size,
    uploaded_by, teacher_id, submission_id, status, academic_period_id
);
```

**العلاقة مع `course_content_submissions`:** عبر `submission_id`.

> ⚠️ **ملاحظة:** `file_type` قيم متوقعة: `'form'`, `'syllabus'`, `'vocabulary'`. لكن لا يوجد `CHECK constraint`.

---

## 9) تحليل `course_content.py` — API للبحث السريع

### 9.1 المسارات

| المسار | الغرض |
|--------|-------|
| `/api/course-content/teachers` | بحث المدرسين |
| `/api/course-content/courses` | بحث المقررات |
| `/api/course-content/teacher-courses` | مقررات مدرس معيّن |
| `/api/course-content/course-teachers` | مدرسو مقرر معيّن |

### 9.2 فلتر الإصدار النشط

```python
_ACTIVE_VERSION = "SELECT id FROM timetable_versions WHERE status = 'active'"

def _active_version_filter(alias='tt'):
    return f"({alias}.version_id IS NULL OR {alias}.version_id IN ({_ACTIVE_VERSION}))"
```

> ⚠️ **مشكلة محتملة:** إذا كان هناك أكثر من إصدار نشط (خطأ بيانات)، قد تُرجَع نتائج مكررة. يُفترض أن `status='active'` فريد.

---

## 10) المشاكل المحتملة المُجمّعة

### 🔴 مشاكل حرجة

| # | الملف | السطر/الدالة | المشكلة | التأثير |
|---|-------|--------------|---------|---------|
| 1 | `codes.html` | `switchCodesView("content")` | دائمًا يفتح على `content` | يتجاهل `tab` من الخادم |
| 2 | `schema.sql` | غياب أعمدة `version_label`, `parent_submission_id`, `published_at`, `archived_at` | `copy_submission_as_draft` قد يفشل | تعطّل الإصدارات |
| 3 | `courses.py` | `SELECT code FROM courses WHERE id = ?` (بدون `deleted_at IS NULL`) | تحديث مقررات محذوفة | بيانات غير متسقة |
| 4 | `course_content_service.py` | `TRANSITIONS` ناقص لـ `PENDING_TEACHER`, `PENDING_HOD`, `PENDING_EXAM` | حالات ميتة | تعطّل سير العمل |
| 5 | `teacher_pages.py` | `super_admin_course_content_send` | لا يتحقق من `topic NOT NULL` قبل الإدراج | فشل عند حفظ صف فارغ |

### 🟡 مشاكل متوسطة

| # | الملف | المشكلة |
|---|-------|---------|
| 6 | `codes.html` | `<input type="hidden" name="course_id" value="57">` قيمة صلبة |
| 7 | `courses_list.js` | دالة `switchCodesEditorMode` مكررة مع `switchCodesView` |
| 8 | `courses.py` | `GROUP_CONCAT` بدون `ORDER BY` → ترتيب عشوائي |
| 9 | `course_content_service.py` | `_validate_step` لا يتحقق من وجود التسليم قبل فحص الصلاحية |
| 10 | `teacher_pages.py` | `_translate_course_content_en` قد يفشل بصمت دون إشعار المستخدم |

### 🟢 مشاكل بسيطة

| # | الملف | المشكلة |
|---|-------|---------|
| 11 | `courses.py` | `unmatched` يُقتطع إلى 20 رسالة فقط (`unmatched[:20]`) |
| 12 | `course_content_service.py` | `_next_version_label` يستخدم `int(''.join(...))` — إذا كان الاسم نصيًا بالكامل → `ValueError` |
| 13 | `course_content.py` | `err('معرّف عضو هيئة التدريس مطلوب', 422)` — رمز 422 غير معتاد، عادةً 400 |

---

## 11) تدفق العمل الكامل (End-to-End)

### سيناريو 1: تعديل أكواد المقررات

```
1. المستخدم يزور /courses/codes
   ↓
2. courses_codes() [GET]
   - tab = 'inline' (افتراضي)
   - يبني courses = _codes_dataset(db, dept_id)
   - يمرر إلى codes.html
   ↓
3. codes.html يعرض جدولًا بكل مقرر
   ↓
4. المستخدم يعدّل code_57 → "SWE402"
   ↓
5. POST /courses/codes
   ↓
6. courses_codes() [POST]
   - updates = {57: "SWE402"}
   - _validate_code_updates → clean
   - UPDATE courses SET code = ...
   - add_history(...)
   - db.commit()
   - flash + redirect
   ↓
7. المستخدم يرى الصفحة محدّثة
```

### سيناريو 2: إنشاء نموذج محتوى ونشره مباشرة

```
1. من courses_list.js → النقر على "إنشاء/تعديل المقرر"
   ↓
2. التوجيه إلى /courses/codes?tab=content&course_id=57
   ↓
3. courses_codes() [GET]
   - tab = 'content'
   - build_course_content_form_context(db, course_id=57)
   - content_ctx = {doc, courses, curriculum, ...}
   ↓
4. codes.html يعرض النموذج معرّفًا بـ course_id=57
   ↓
5. المستخدم يملأ البيانات وينقر "حفظ مفردات المقرر"
   ↓
6. POST /teacher/super-admin/course-content/send
   - action = 'send'
   - course_id = 57
   - _curriculum_from_form(request.form)
   - theoretical_weeks = sum(...)
   - if > 12: flash error
   - context = _course_context_course_only(db, 57)
   - department_id = context['department_id']
   - submission_id = None → _insert_course_content(...)
   - _sync_form_course_file(...)
   - publish_directly(db, submission_id, role)
       - chain = [('submit', PENDING_RND), ('approve', APPROVED), ('publish', PUBLISHED)]
       - التحقق المسبق للكل
       - التنفيذ في معاملة واحدة
   - flash success
   ↓
7. redirect إلى /courses/codes?tab=content&course_id=57&submission_id=N
```

---

## 12) العلاقات بين الملفات (مصفوفة)

| الملف | يستدعي | يُستدعى من |
|-------|---------|-----------|
| `courses.py` | `course_service`, `build_course_content_form_context`, `api.courses` | `__init__.py` (تسجيل Blueprint) |
| `teacher_pages.py` | `course_content_service`, `notification_service`, `public_service` | `courses.py` (عبر `build_course_content_form_context`) |
| `course_content_service.py` | `flask.current_app` فقط | `teacher_pages.py`, `courses.py` |
| `course_content.py` | `api.helpers`, `flask_db` | `__init__.py` |
| `courses_list.js` | `window.COURSES_LIST_BOOT`, `TomSelect` | `courses/list.html` |
| `codes.html` | `courses_list.js`؟ (غير مباشر)، `switchCodesView` | `courses.py::courses_codes` |
| `schema.sql` | — | `database/schema.py` |

---

## 13) توصيات الإصلاح

### فوري (Hotfix)

1. **`codes.html`:** استبدال `switchCodesView("content")` بـ `switchCodesView("{{ tab|default('inline') }}")`.
2. **`courses.py`:** إضافة `AND deleted_at IS NULL` إلى `SELECT code FROM courses WHERE id = ?`.
3. **`schema.sql`:** إضافة أعمدة `version_label`, `parent_submission_id`, `published_at`, `archived_at` (أو التأكد من `_safe_add_column`).

### قصير المدى

4. **`course_content_service.py`:** إضافة انتقالات لـ `PENDING_TEACHER`, `PENDING_HOD`, `PENDING_EXAM` أو إزالتها من التعريفات.
5. **`teacher_pages.py`:** التحقق من `topic NOT NULL` قبل الإدراج في `_curriculum_from_form` و `_insert_course_content`.
6. **`courses.py`:** إضافة `ORDER BY` داخل `GROUP_CONCAT` لضمان ترتيب الأقسام.

### متوسط المدى

7. **توحيد JS:** نقل `switchCodesView` من `codes.html` إلى `courses_list.js` لتفادي التكرار.
8. **إزالة القيم الصلبة:** جعل `course_id` في `codes.html` يُمرَّر من الخادم.
9. **إضافة فهارس:** `idx_course_content_transitions_created` على `created_at`.

---

## 14) خلاصة العلاقة الوظيفية

```
┌─────────────────────────────────────────────────────────────────────┐
│                    المستخدم (R&D / HOD / Teacher)                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────┐
        │  /courses        →  courses_list.js   │  ← عرض/تحرير
        │  /courses/codes  →  codes.html        │  ← أكواد + محتوى
        └──────────┬───────────────────────────┘
                   │
                   ▼
        ┌──────────────────────────────────────┐
        │  courses.py (Blueprint)              │
        │  teacher_pages.py (Blueprint)        │
        └──────────┬───────────────────────────┘
                   │
                   ▼
        ┌──────────────────────────────────────┐
        │  course_content_service.py           │
        │  (آلة الحالة — مصدر الحقيقة)         │
        └──────────┬───────────────────────────┘
                   │
                   ▼
        ┌──────────────────────────────────────┐
        │  schema.sql (SQLite)                 │
        │  course_content_submissions          │
        │  course_content_curriculum           │
        │  course_content_transitions          │
        │  course_files                        │
        └──────────────────────────────────────┘
```

> **القاعدة الذهبية:** كل تعديل على `course_content_submissions` يجب أن يمر عبر `course_content_service.py` — لا كتابة مباشرة من المسارات. هذا يضمن سلامة آلة الحالة وسجل التدقيق.

---

## ملحق أ: جدول الرموز المستخدمة

| الرمز | المعنى |
|-------|--------|
| 🔴 | مشكلة حرجة — تؤثر على وظائف أساسية |
| 🟡 | مشكلة متوسطة — تؤثر على تجربة المستخدم أو الأداء |
| 🟢 | مشكلة بسيطة — تحسينية |
| ⚠️ | تحذير — نقطة تحتاج انتباه |
| ✅ | صحيح — لا مشكلة |

---

## ملحق ب: قائمة الدوال الحرجة (Quick Reference)

| الدالة | الملف | الغرض |
|--------|-------|-------|
| `_build_placements()` | `courses.py` | بناء قائمة الأقسام من النموذج |
| `_codes_dataset()` | `courses.py` | جلب بيانات المقررات للأكواد |
| `_validate_code_updates()` | `courses.py` | التحقق من صحة الأكواد |
| `build_course_content_form_context()` | `teacher_pages.py` | بناء سياق نموذج المحتوى |
| `transition_submission()` | `course_content_service.py` | تنفيذ انتقال حالة واحدة |
| `publish_directly()` | `course_content_service.py` | نشر مباشر (سلسلة انتقالات) |
| `copy_submission_as_draft()` | `course_content_service.py` | إنشاء نسخة جديدة |
| `pdf_state_for()` | `course_content_service.py` | حالة عمود الملف |
| `switchCodesView()` | `codes.html` | التبديل بين تبويبات الأكواد |

---

**نهاية الملف**
```