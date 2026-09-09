# Template Conversion Script
# Converts standalone Tailwind HTML templates to use shared layouts

param(
    [string]$TemplatesDir = "C:\Users\MD.MASTER\OneDrive\Desktop\newRopey\templates"
)

# Template mapping: filename -> layout, sidebar_active, page_title
$templateMap = @{
    # AUTH templates
    "auth\login.html" = @{layout="auth"; active=""; title="تسجيل الدخول"}
    "auth\forgot_password.html" = @{layout="auth"; active=""; title="استعادة كلمة المرور"}
    "auth\reset_password.html" = @{layout="auth"; active=""; title="إعادة تعيين كلمة المرور"}
    "auth\change_password.html" = @{layout="auth"; active=""; title="تغيير كلمة المرور"}
    
    # USERS
    "users\list.html" = @{layout="super_admin"; active="users"; title="إدارة المستخدمين"}
    "users\edit.html" = @{layout="super_admin"; active="users"; title="تعديل المستخدم"}
    "users\profile.html" = @{layout="super_admin"; active="profile"; title="الملف الشخصي"}
    "users\settings.html" = @{layout="super_admin"; active="settings"; title="الإعدادات"}
    
    # TEACHERS
    "teachers\list.html" = @{layout="super_admin"; active="teachers"; title="إدارة هيئة التدريس"}
    "teachers\create.html" = @{layout="super_admin"; active="teachers"; title="إضافة عضو هيئة تدريس"}
    "teachers\edit.html" = @{layout="super_admin"; active="teachers"; title="تعديل عضو هيئة تدريس"}
    "teachers\detail.html" = @{layout="super_admin"; active="teachers"; title="تفاصيل عضو هيئة تدريس"}
    "teachers\archive.html" = @{layout="super_admin"; active="teachers"; title="أرشيف هيئة التدريس"}
    "teachers\grades.html" = @{layout="teacher"; active="grades"; title="الدرجات"}
    "teachers\messages.html" = @{layout="teacher"; active="messages"; title="الرسائل"}
    "teachers\upload.html" = @{layout="teacher"; active="upload"; title="رفع الملفات"}
    
    # STUDENTS
    "students\list.html" = @{layout="super_admin"; active="students"; title="إدارة الطلاب"}
    "students\create.html" = @{layout="super_admin"; active="students"; title="إضافة طالب"}
    "students\edit.html" = @{layout="super_admin"; active="students"; title="تعديل طالب"}
    "students\detail.html" = @{layout="super_admin"; active="students"; title="تفاصيل الطالب"}
    "students\archive.html" = @{layout="super_admin"; active="students"; title="أرشيف الطلاب"}
    
    # CLASSROOMS
    "classrooms\list.html" = @{layout="super_admin"; active="rooms"; title="إدارة القاعات"}
    "classrooms\create.html" = @{layout="super_admin"; active="rooms"; title="إضافة قاعة"}
    "classrooms\edit.html" = @{layout="super_admin"; active="rooms"; title="تعديل القاعة"}
    "classrooms\detail.html" = @{layout="super_admin"; active="rooms"; title="تفاصيل القاعة"}
    "classrooms\archive.html" = @{layout="super_admin"; active="rooms"; title="أرشيف القاعات"}
    
    # COURSES
    "courses\list.html" = @{layout="super_admin"; active="courses"; title="إدارة المقررات"}
    "courses\create.html" = @{layout="super_admin"; active="courses"; title="إضافة مقرر"}
    "courses\edit.html" = @{layout="super_admin"; active="courses"; title="تعديل المقرر"}
    "courses\detail.html" = @{layout="super_admin"; active="courses"; title="تفاصيل المقرر"}
    "courses\archive.html" = @{layout="super_admin"; active="courses"; title="أرشيف المقررات"}
    "courses\print.html" = @{layout="super_admin"; active="courses"; title="طباعة المقررات"}
    
    # DEPARTMENTS
    "departments\list.html" = @{layout="super_admin"; active="departments"; title="إدارة الأقسام"}
    "departments\messages.html" = @{layout="hod"; active="messages"; title="رسائل الأقسام"}
    "departments\teacher_files.html" = @{layout="hod"; active="files"; title="ملفات أعضاء هيئة التدريس"}
    
    # EXAMS
    "exams\list.html" = @{layout="super_admin"; active="exams"; title="إدارة الامتحانات"}
    "exams\halls.html" = @{layout="super_admin"; active="exams"; title="توزيع القاعات"}
    "exams\merge.html" = @{layout="super_admin"; active="exams"; title="دمج الامتحانات"}
    "exams\proctors.html" = @{layout="super_admin"; active="exams"; title="المراقبون"}
    "exams\reports.html" = @{layout="super_admin"; active="exams"; title="تقارير الامتحانات"}
    "exams\settings.html" = @{layout="super_admin"; active="exams"; title="إعدادات الامتحانات"}
    
    # EXAM FLOW
    "exam_flow\exam_flow.html" = @{layout="super_admin"; active="exams"; title="سير الامتحانات"}
    "exam_flow\halls_distribution.html" = @{layout="super_admin"; active="exams"; title="توزيع القاعات"}
    "exam_flow\merge.html" = @{layout="super_admin"; active="exams"; title="دمج الامتحانات"}
    "exam_flow\proctors.html" = @{layout="super_admin"; active="exams"; title="المراقبون"}
    "exam_flow\reports.html" = @{layout="super_admin"; active="exams"; title="تقارير"}
    "exam_flow\settings.html" = @{layout="super_admin"; active="exams"; title="الإعدادات"}
    
    # TIMETABLE
    "timetable\list.html" = @{layout="super_admin"; active="timetable"; title="الجدول الدراسي"}
    "timetable\lecture.html" = @{layout="super_admin"; active="timetable"; title="محاضرات"}
    "timetable\lecture_schedule.html" = @{layout="super_admin"; active="timetable"; title="جدول المحاضرات"}
    "timetable\teacher.html" = @{layout="super_admin"; active="timetable"; title="جدول أعضاء هيئة التدريس"}
    "timetable\teachers_schedule.html" = @{layout="super_admin"; active="timetable"; title="جدول التدريس"}
    "timetable\exam.html" = @{layout="super_admin"; active="timetable"; title="جدول الامتحانات"}
    "timetable\timetable_exam.html" = @{layout="super_admin"; active="timetable"; title="جدول الامتحانات"}
    "timetable\department.html" = @{layout="super_admin"; active="timetable"; title="جدول الأقسام"}
    "timetable\department_exam_view.html" = @{layout="super_admin"; active="timetable"; title="عرض امتحانات الأقسام"}
    "timetable\timetable.html" = @{layout="super_admin"; active="timetable"; title="الجدول"}
    "timetable\print.html" = @{layout="super_admin"; active="timetable"; title="طباعة الجدول"}
    
    # ATTENDANCE
    "attendance\list.html" = @{layout="super_admin"; active="attendance"; title="الحضور"}
    "attendance\create.html" = @{layout="super_admin"; active="attendance"; title="تسجيل الحضور"}
    
    # AUDIT
    "audit\list.html" = @{layout="super_admin"; active="history"; title="سجل التغييرات"}
    "audit\detail.html" = @{layout="super_admin"; active="history"; title="تفاصيل التغيير"}
    
    # ARCHIVE
    "archive\teachers_archive.html" = @{layout="super_admin"; active="teachers"; title="أرشيف هيئة التدريس"}
    "archive\students_archive.html" = @{layout="super_admin"; active="students"; title="أرشيف الطلاب"}
    "archive\rooms_archive.html" = @{layout="super_admin"; active="rooms"; title="أرشيف القاعات"}
    "archive\courses_archive.html" = @{layout="super_admin"; active="courses"; title="أرشيف المقررات"}
    
    # HOD
    "hod\messages.html" = @{layout="hod"; active="messages"; title="الرسائل"}
    "hod\teacher_files.html" = @{layout="hod"; active="files"; title="الملفات"}
    
    # OLD LIST/CREATE/EDIT/DETAIL DIRECTORIES
    "list\users_list.html" = @{layout="super_admin"; active="users"; title="قائمة المستخدمين"}
    "list\teachers_list.html" = @{layout="super_admin"; active="teachers"; title="قائمة أعضاء هيئة التدريس"}
    "list\students_list.html" = @{layout="super_admin"; active="students"; title="قائمة الطلاب"}
    "list\rooms_list.html" = @{layout="super_admin"; active="rooms"; title="قائمة القاعات"}
    "list\courses_list.html" = @{layout="super_admin"; active="courses"; title="قائمة المقررات"}
    "list\departments_list.html" = @{layout="super_admin"; active="departments"; title="قائمة الأقسام"}
    "list\history_list.html" = @{layout="super_admin"; active="history"; title="سجل التغييرات"}
    
    "create\users_create.html" = @{layout="super_admin"; active="users"; title="إنشاء مستخدم"}
    "create\teachers_create.html" = @{layout="super_admin"; active="teachers"; title="إنشاء عضو هيئة تدريس"}
    "create\students_create.html" = @{layout="super_admin"; active="students"; title="إنشاء طالب"}
    "create\rooms_create.html" = @{layout="super_admin"; active="rooms"; title="إنشاء قاعة"}
    "create\courses_create.html" = @{layout="super_admin"; active="courses"; title="إنشاء مقرر"}
    
    "edit\users_edit.html" = @{layout="super_admin"; active="users"; title="تعديل المستخدم"}
    "edit\teachers_edit.html" = @{layout="super_admin"; active="teachers"; title="تعديل عضو هيئة تدريس"}
    "edit\students_edit.html" = @{layout="super_admin"; active="students"; title="تعديل الطالب"}
    "edit\rooms_edit.html" = @{layout="super_admin"; active="rooms"; title="تعديل القاعة"}
    "edit\courses_edit.html" = @{layout="super_admin"; active="courses"; title="تعديل المقرر"}
    
    "detail\teacher_detail.html" = @{layout="super_admin"; active="teachers"; title="تفاصيل عضو هيئة تدريس"}
    "detail\student_detail.html" = @{layout="super_admin"; active="students"; title="تفاصيل الطالب"}
    "detail\room_detail.html" = @{layout="super_admin"; active="rooms"; title="تفاصيل القاعة"}
    "detail\course_detail.html" = @{layout="super_admin"; active="courses"; title="تفاصيل المقرر"}
    "detail\history_detail.html" = @{layout="super_admin"; active="history"; title="تفاصيل التغيير"}
    
    # PRINT
    "print\courses_print.html" = @{layout="super_admin"; active="courses"; title="طباعة المقررات"}
    "print\dashboard_print.html" = @{layout="super_admin"; active="dashboard"; title="طباعة لوحة التحكم"}
    "print\timetable_official_print.html" = @{layout="super_admin"; active="timetable"; title="طباعة الجدول الرسمي"}
}

Write-Host "Converting templates to use shared layouts..." -ForegroundColor Green

foreach ($pair in $templateMap.GetEnumerator()) {
    $relativePath = $pair.Key
    $info = $pair.Value
    $fullPath = Join-Path $TemplatesDir $relativePath
    
    if (-not (Test-Path $fullPath)) {
        Write-Host "  SKIP $relativePath (not found)" -ForegroundColor Yellow
        continue
    }
    
    $content = Get-Content $fullPath -Raw
    $originalLength = $content.Length
    
    # Skip if already converted (starts with {% extends)
    if ($content -match '^\s*\{\%\s*extends\s') {
        Write-Host "  SKIP $relativePath (already converted)" -ForegroundColor Cyan
        continue
    }
    
    # Extract the page title from <title> tag
    $titleMatch = [regex]::Match($content, '<title>(.*?)</title>')
    $pageTitle = $info.title
    if ($titleMatch.Success -and $titleMatch.Groups[1].Value) {
        $extractedTitle = $titleMatch.Groups[1].Value -replace '\s*\|\s*.*$', ''
        if ($extractedTitle.Trim().Length -gt 0) {
            $pageTitle = $extractedTitle.Trim()
        }
    }
    
    # Find the main content between <main...> and </main>
    $mainMatch = [regex]::Match($content, '<main[^>]*>(.*?)</main>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    
    if (-not $mainMatch.Success) {
        Write-Host "  SKIP $relativePath (no <main> tag found)" -ForegroundColor Yellow
        continue
    }
    
    $mainContent = $mainMatch.Groups[1].Value
    
    # Find any page-specific <style> blocks and <script> blocks that are INSIDE the main content
    # These should stay as-is
    
    # Build the new template
    $extends = "{% extends `"shared/layouts/$($info.layout).html`" %}"
    $varActive = "{% set sidebar_active = '$($info.active)' %}"
    $varTitle = "{% set page_title = '$pageTitle' %}"
    
    $newContent = @"
$extends
$varActive
$varTitle
{% block content %}
$mainContent
{% endblock %}
"@
    
    # Remove any duplicate tailwind_config includes from the content (they're already in base)
    $newContent = $newContent -replace '\{% include .partials/tailwind_config.html. %\}\s*', ''
    
    Set-Content -Path $fullPath -Value $newContent -Encoding UTF8
    $newLength = $newContent.Length
    $saved = $originalLength - $newLength
    Write-Host "  OK  $relativePath (saved $saved bytes)" -ForegroundColor Green
}

Write-Host "`nDone! Converted templates to use shared layouts." -ForegroundColor Green

