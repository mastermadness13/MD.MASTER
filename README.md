# newRopey

A Flask-based college management system with Arabic RTL support, role-based dashboards, timetable management, exam scheduling, course content and course plans, teacher messaging, classroom change requests, faculty attendance, notifications, and basic audit/history features.

This README consolidates the most important information from the earlier project documentation into a single source of truth.

## Project Overview

newRopey is a web application for managing core academic and administrative operations at Zuwaita Technical Engineering College. The system is built around a single Flask application and a SQLite database, with a mix of Bootstrap-based and Tailwind-based templates.

### Main Goals
- Manage users, departments, teachers, rooms, and courses
- Support timetable and exam scheduling workflows
- Manage course content and course plans per teacher
- Provide staff messaging and classroom change request workflows
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
- Soft-delete/archive support for major entities
- Weekly timetable display and scheduling workflows
- Exam scheduling, planning, hall distribution, and merging
- Course content submissions and review
- Course plan creation and management
- Teacher messaging (staff to head of department)
- Classroom change requests with availability checks
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

The system has six roles:

| Role | Arabic Label | Purpose |
|------|--------------|---------|
| super_admin | مدير النظام | Full management |
| research_development | قسم البحث والتطوير | View teachers, courses, timetable, and course content |
| faculty_affairs | مكتب هيئة التدريس | Manage teachers; view departments, courses, timetable |
| head_of_department | رئيس القسم | Manage department timetable, materials, messages, classroom requests |
| teacher | عضو هيئة تدريس | View own timetable, edit course content, manage course plans, uploads, messages |
| exam | الامتحانات | Manage exam scheduling, planning, halls, proctors, and department schedules |

(Note: the former `support_admin` role no longer exists in the running application; the
application implements the six roles above.)

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
- classroom_change_requests
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

النظام هو تطبيق ويب متكامل لإدارة الكلية (كلية التقنية الهندسية زوارة) يشمل إدارة المستخدمين، الأقسام، أعضاء هيئة التدريس، المواد الدراسية، القاعات، الجداول الدراسية، الامتحانات، محتوى المواد، الخطط الدراسية، المراسلات، وطلبات تغيير القاعات. النظام مبني بلغة Python مع إطار Flask ويستخدم SQLite كقاعدة بيانات مع واجهة باللغة العربية (RTL).

### 2. الأدوار والصلاحيات (Roles & Permissions)

النظام يدعم 6 أدوار رئيسية:

| الدور | الوصف |
|---|---|
| **super_admin** | مدير النظام الأعلى - صلاحية كاملة على كل شيء |
| **research_development** | قسم البحث والتطوير - عرض المحاضرين والمواد والجداول ومحتوى المواد |
| **faculty_affairs** | مكتب هيئة التدريس - إدارة شؤون المحاضرين، عرض الأقسام والمواد والجداول |
| **head_of_department** | رئيس القسم - إدارة جدول القسم، مراجعة المواد والمحتوى والمراسلات وطلبات تغيير القاعات |
| **teacher** | عضو هيئة تدريس - الاطلاع على جدوله، تحرير محتوى المادة، إدارة الخطط الدراسية، رفع الملفات، المراسلات |
| **exam** | لجنة الامتحانات - إدارة جداول الامتحانات والتخطيط والقاعات والمراقبين |

كل صلاحية تحدد الصفحات التي يمكن للمستخدم الوصول إليها والبيانات التي يراها. خريطة الصلاحيات الكاملة موجودة في `navigation.py` (`ROLE_PERMISSIONS`).

### 3. شاشة الدخول (Login)

- المسار: `/login`
- المستخدم الافتراضي: `superadmin` / كلمة السر: `admin123`
- حسابات المحاضرين المزروعة افتراضياً: `123456`
- عند الدخول يتم التحقق من صلاحية المستخدم وتوجيهه إلى لوحة التحكم الخاصة بدوره
- يوجد خيار "نسيت كلمة السر" لإعادة تعيين كلمة المرور

### 4. لوحات التحكم (Dashboards)

كل دور له لوحة تحكم خاصة تعرض إحصائيات مناسبة له:

- **super_admin / faculty_affairs**: إحصائيات شاملة (الأقسام، المحاضرين، المواد، القاعات، المستخدمين، جداول الامتحانات)
- **research_development**: إحصائيات خاصة بقسم البحث والتطوير
- **head_of_department**: إحصائيات خاصة بقسمه فقط
- **teacher**: جدول محاضراته وإشعاراته
- **exam**: إحصائيات الامتحانات

### 5. إدارة الأقسام (Departments)

- المسار: `/departments`
- متاح لـ: super_admin (إدارة كاملة)
- **القائمة**: جدول يعرض جميع الأقسام مع إمكانية البحث
- **إنشاء قسم**: إدخال اسم القسم، عدد الفصول الدراسية، عدد الشعب، دعم الشعب
- **تعديل قسم**: تغيير بيانات القسم
- **حذف (ناعم)**: نقل إلى الأرشفة (soft delete)
- **استرجاع**: إعادة القسم من الأرشيف
- **حذف نهائي**: إزالة القسم نهائياً
- **إدارة الشعب (المياجر)**: إضافة وحذف الشعب لكل قسم
- **الأرشيف**: يعرض الأقسام المحذوفة (ناعم) مع إمكانية الاسترجاع أو الحذف النهائي

الأقسام الافتراضية: القسم العام، قسم الاتصالات، قسم الحاسوب، قسم المدني، قسم المعماري، قسم النفط

### 6. إدارة المحاضرين (Teachers)

- المسار: `/teachers`
- متاح لـ: super_admin, faculty_affairs (إدارة) — research_development, head_of_department (عرض)
- **القائمة**: جدول يعرض المحاضرين مع البحث بالاسم أو الرقم الكلية أو البريد، وتصفية حسب القسم، وترقيم الصفحات
- **إنشاء محاضر**: الاسم، البريد الإلكتروني، الهاتف، القسم، الرقم الكلية، الرقم الوطني، المؤهل العلمي، الرتبة الكلية، التصنيف، تاريخ التعاقد، المهام الموكلة
- **عرض التفاصيل**: صفحة تعرض معلومات المحاضر والمواد التي يدرسها
- **تعديل محاضر**: تغيير أي من المعلومات
- **حذف (ناعم)** - **استرجاع** - **حذف نهائي**
- **الأرشيف**: قائمة المحاضرين المحذوفين
- **إعادة تعيين كلمة السر** لحساب المحاضر

### 7. إدارة المواد الدراسية (Courses)

- المسار: `/courses`
- متاح لـ: super_admin (إدارة) — research_development, faculty_affairs, head_of_department, exam, teacher (عرض)
- **القائمة**: جدول يعرض المواد مع الكود، الاسم، القسم، السنة، الفصل الدراسي، والساعات النظرية والعملية والإجمالية
- **إنشاء مادة**: الكود، الاسم، القسم، السنة، الفصل الدراسي، الساعات، الاعتماد الكلية، المفردات، رفع ملف المنهج (syllabus)، المتطلبات السابقة (prerequisites)، الأيقونة
- **عرض التفاصيل**: معلومات المادة مع المتطلبات السابقة والمواد التابعة
- **تعديل مادة**: تغيير البيانات
- **حذف (ناعم)** - **استرجاع** - **حذف نهائي**
- **الأرشيف**: قائمة المواد المحذوفة

### 8. إدارة القاعات الدراسية (Rooms / Classrooms)

- المسار: `/rooms`
- متاح لـ: super_admin (إدارة) — exam (عرض)
- **القائمة**: جدول يعرض القاعات مع الاسم، الكود، السعة، النوع، الموقع، المبنى، الحالة
- **إنشاء قاعة**: الاسم، الكود، السعة، النوع (قاعة محاضرات، مختبر، معمل حاسوب، استوديو، مسرح)، الحالة، الموقع، المبنى، الطابق، التجهيزات (أجهزة كمبيوتر، أجهزة إلكترونية، أرفف كتب، سبورات، بروجيكتور، مسرح، مقاعد، محطات عمل)، قابلية الحجز
- **عرض التفاصيل**: معلومات القاعة مع التجهيزات
- **تعديل قاعة**: تغيير البيانات
- **حذف (ناعم)** - **استرجاع** - **حذف نهائي**
- **الأرشيف**: قائمة القاعات المحذوفة

### 9. إدارة المستخدمين (Users)

- المسار: `/users`
- متاح لـ: super_admin
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
- متاح لـ: teacher (تحرير) — head_of_department, research_development, exam (عرض/مراجعة)
- المحاضر يرسل محتوى المادة (الأهداف، المتطلبات، المقررات، الساعات، وغيرها) كتسليم (submission)
- رئيس القسم / super_admin يراجع التسليمات عبر `/teacher/super-admin/course-content` مع إمكانية قبولها أو إرجاعها مع ملاحظات
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

### 15. طلبات تغيير القاعة (Classroom Change Requests)

- المسار: `/classroom-requests`
- متاح لـ: teacher, head_of_department
- **إنشاء طلب**: المحاضر يطلب تغيير قاعة لمحاضرة معينة مع ذكر السبب
- **طلباتي**: عرض طلبات المستخدم
- **الطلبات المعلقة** (لرئيس القسم): عرض ومراجعة الطلبات
- **مراجعة الطلب**: موافقة أو رفض من رئيس القسم مع تعليق
- **فحص التوفر**: التحقق من توفر القاعة المطلوبة

### 16. الإشعارات (Notifications)

- متاح لـ: جميع المستخدمين المسجلين
- تعرض في الشريط العلوي (أيقونة الجرس)
- كل إشعار له: عنوان، رسالة، نوع، تاريخ
- يمكن وضع علامة "مقروء" على الإشعارات

### 17. الطباعة (Print)

- `/print/timetable`: طباعة الجدول الدراسي
- `/print/courses`: طباعة قائمة المواد

### 18. كيف يعمل النظام (Architecture)

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

### 19. المشاكل المعروفة والقيود (Known Issues)

1. **المراسلات**: نظام المراسلات بين المحاضرين ورؤساء الأقسام يحتاج إلى تحسين
2. **الواجهة الأمامية**: خليط بين Bootstrap و Tailwind - يحتاج إلى توحيد
3. **الامتحانات**: بعض إجراءات سير عمل الامتحانات لا تزال محدودة
4. **الاختبارات**: لا توجد تغطية اختبارية كافية
5. **تكرار القوالب**: بعض القوالب مكررة ويجب دمجها
6. **الجدول الدراسي**: لا توجد أداة استيراد جماعي للجدول - الإنشاء محاضرة بمحاضرة
