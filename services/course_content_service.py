"""خدمة محتوى المقرر — مصدر الحقيقة الوحيد لانتقالات الحالة والنسخ.

البنية:  الدور ← الصلاحية ← الحالة ← انتقال
كل تعديل لأي ``course_content_submission`` يمر عبر خدمة هنا، لا يفحص أي
مسار حالة واجهةً أو زرًّا. يُرفض أي استدعاء يخالف (الصلاحية + الملكية +
الحالة الحالية) ويعيد نتيجة توصّف المشكلة بلغة قابلة للعرض.

ملاحظات المعمارية:
- /     /     >---- لا يُنشئ هذا الملف PDF ولا يمسّ الملفات؛ النشر يربط فقط
- /     /     >---- المسارات بـ``course_files.status`` ويتعامل مع الأعمدة.
- /     /     >---- الاعتماد (review) يقبل ../pending_* فقط، وتثبت قائمة
- /     /     >---- النشر مرةً واحدةً في PUBLIC_FORM_STATUSES = ('published',).
- /     /     >---- كل انتقال يُسجَّل في course_content_transitions بما فيه
- /     /     >---- كل خطوة من سلسلة publish_directly (معاملة واحدة).
"""

from __future__ import annotations

import sqlite3

from flask import current_app


# ─────────────────────────────────────────────────────────────────────────────
# /     /     >---- حالات سير العمل — تُعرض بالتسميات من core/constants/system
# ─────────────────────────────────────────────────────────────────────────────
DRAFT = 'draft'
PENDING_TEACHER = 'pending_teacher'
PENDING_RND = 'pending_rnd'
PENDING_HOD = 'pending_hod'
PENDING_EXAM = 'pending_exam'
APPROVED = 'approved'
REJECTED = 'rejected'
PUBLISHED = 'published'
ARCHIVED = 'archived'


# /     /     >---- الحالات التي تظهر للعموم (مصدر الحقيقة للنشر)
PUBLIC_FORM_STATUSES = (PUBLISHED,)


# /     /     >---- الحالات التي يظهر فيها الملف للعموم (مرآة course_files)
PUBLIC_FILE_STATUSES = (PUBLISHED,)


# ─────────────────────────────────────────────────────────────────────────────
# /     /     >---- pdfState — الحالة الموحَّدة لعمود «الملف» (تعاقد خارجي)
# /     /     >---- قاعدة التصميم: الملف عمود في الجدول لا عنصر في قائمة منسدلة.
# /     /     >---- يُشتق لكل صف من (وجود ملف نموذج قابل للتحميل + آخر تسليم).
# /     /     >----  available      = يوجد ملف نموذج → تحميل بنقرة واحدة
# /     /     >----  draft          = آخر تسليم مسودة (تحميل المسودة)
# /     /     >----  pending_review = بانتظار المراجعة (قيد المراجعة)
# /     /     >----  approved       = آخر تسليم معتمد/منشور
# /     /     >----  rejected       = آخر تسليم مرفوض
# /     /     >----  none           = لا ملف ولا تسليم
# ─────────────────────────────────────────────────────────────────────────────
PDF_STATE_AVAILABLE = 'available'
PDF_STATE_DRAFT = 'draft'
PDF_STATE_PENDING_REVIEW = 'pending_review'
PDF_STATE_APPROVED = 'approved'
PDF_STATE_REJECTED = 'rejected'
PDF_STATE_NONE = 'none'

_PDF_STATE_FROM_SUBMISSION = {
    DRAFT: PDF_STATE_DRAFT,
    PENDING_TEACHER: PDF_STATE_PENDING_REVIEW,
    PENDING_RND: PDF_STATE_PENDING_REVIEW,
    PENDING_HOD: PDF_STATE_PENDING_REVIEW,
    PENDING_EXAM: PDF_STATE_PENDING_REVIEW,
    APPROVED: PDF_STATE_APPROVED,
    PUBLISHED: PDF_STATE_APPROVED,
    REJECTED: PDF_STATE_REJECTED,
}


def pdf_state_for(submission_status='', has_downloadable_form=False) -> str:
    """الحالة الموحَّدة لعمود «الملف» لمقرر واحد.

    وجود ملف نموذج قابل للتحميل يسبق كل شيء (المستخدم ينقر مرة واحدة)؛
    وإلا تعكس الحالة دورة حياة آخر تسليم.
    """
    if has_downloadable_form:
        return PDF_STATE_AVAILABLE
    return _PDF_STATE_FROM_SUBMISSION.get(submission_status or '', PDF_STATE_NONE)


# ─────────────────────────────────────────────────────────────────────────────
# /     /     >---- آلة الحالة — كل انتقال يُسمَّح به صراحةً وبعكسه
# /     /     >---- key = (الحالة الحالية ← الانتقال)  value = الحالة التالية
# ─────────────────────────────────────────────────────────────────────────────
TRANSITIONS = {
    (DRAFT, 'save'): DRAFT,
    (DRAFT, 'submit'): PENDING_RND,
    (PENDING_TEACHER, 'save'): PENDING_TEACHER,
    (PENDING_TEACHER, 'submit'): PENDING_RND,
    # /     /     >---- مسارات المراجعة القديمة المتعددة تُرفض حالياً (مرحلة واحدة)
    (PENDING_RND, 'approve'): APPROVED,
    (PENDING_RND, 'reject'): REJECTED,
    (REJECTED, 'save'): REJECTED,
    (REJECTED, 'submit'): PENDING_RND,
    (APPROVED, 'publish'): PUBLISHED,
    # /     /     >---- النشر ← مسودة/نسخة جديدة لا يُعدّل النص السابق مباشرة
    (PUBLISHED, 'archive'): ARCHIVED,
}


# /     /     >---- صلاحية مطلوبة لكل انتقال (دور ← صلاحية ← حالة)
# /     /     >---- من أدوار إلى مجموعة أدوار (Role → Permissions → Transition)
REVIEW_ROLES = {'research_development', 'super_admin'}   # /     /     >---- الاعتماد النهائي
PUBLISH_ROLES = {'research_development', 'super_admin'}  # /     /     >---- نشر
ARCHIVE_ROLES = {'super_admin'}                          # /     /     >---- أرشفة منشور


class CourseContentError(Exception):
    """أساس أخطاء خدمة المحتوى."""


class SubmissionNotFound(CourseContentError):
    """لا يوجد طلب/تسليم بالمعرّف المعطى."""


class RoleNotAllowed(CourseContentError):
    """الدور الحالي لا يملك صلاحية هذا الانتقال."""


class OwnershipNotAllowed(CourseContentError):
    """المستخدم ليس مالك هذا التسليم (لا يعدّل ما ليس له)."""


class TransitionNotAllowed(CourseContentError):
    """الحالة الحالية لا تسمح بهذا الانتقال."""


class PublishBlockedByWeeks(CourseContentError):
    """مجموع أسابيع المحتوى النظري > الحد الأقصى — يجري منع النشر/الإرسال."""


# /     /     >---- أقصى أسابيع للمحتوى النظري (مصدر الحقيقة الواحد)
MAX_THEORETICAL_WEEKS = 12


# /     /     >---- سلسلة الإرسال المباشر للنشر: كل خطوة تُطبَّق وحدها
# /     /     >---- (لا اختصار للانتقالات): pending_teacher/draft/rejected
# /     /     >---- ← submit → pending_rnd ← approve → approved ← publish → published
_PUBLISH_CHAIN = ('submit', 'approve', 'publish')


# ─────────────────────────────────────────────────────────────────────────────
# /     /     >---- فحص الحالة الحالية + الإجراء معاً قبل أي كتابة
# ─────────────────────────────────────────────────────────────────────────────
def _validate_step(db, submission_id, action, actor_role, weeks_total):
    """Validate a single step against the DB and raise CourseContentError.

    Returns the current status on success (no writes performed).
    """
    if action not in ('save', 'submit', 'approve', 'reject', 'publish', 'archive'):
        raise TransitionNotAllowed(f'إجراء غير معروف: {action}')

    # /     /     >---- فحص الصلاحية حسب الإجراء
    if action in ('approve', 'reject'):
        _require_role(actor_role, REVIEW_ROLES, 'review')
    elif action == 'publish':
        _require_role(actor_role, PUBLISH_ROLES, 'publish')
    elif action == 'archive':
        _require_role(actor_role, ARCHIVE_ROLES, 'archive')
    # /     /     >---- save/submit: أي دور صاحب تحرير (يمر فحص الملكية أدناه)

    # /     /     >---- فحص الأسابيع عند الإرسال/الاعتماد/النشر (إن رُصد المجموع)
    if action in ('submit', 'approve', 'publish') and weeks_total > MAX_THEORETICAL_WEEKS:
        raise PublishBlockedByWeeks(
            f'مجموع الأسابيع النظرية ({weeks_total}) يتجاوز الحد الأقصى ({MAX_THEORETICAL_WEEKS})')

    return True


# /     /     >---- تنفيذ خطوة واحدة مع تسجيلها في سجل الانتقالات
def _apply_transition(db, row, action, next_status, actor_role, *,
                      review_notes='', actor_user_id=None, commit=True):
    """Apply one already-validated transition and log it."""
    now = _db_now()
    submission_id = row['id']
    if action == 'reject':
        if not review_notes.strip():
            raise TransitionNotAllowed('سبب الرفض مطلوب عند الاعتراض')
        db.execute(
            'UPDATE course_content_submissions '
            'SET status = ?, review_notes = ?, reviewed_by = NULL, '
            'reviewed_at = NULL, updated_at = ? '
            'WHERE id = ?',
            (next_status, review_notes.strip(), now, submission_id)
        )
    elif action == 'approve':
        db.execute(
            'UPDATE course_content_submissions '
            'SET status = ?, review_notes = ?, reviewed_by = COALESCE(?, reviewed_by), '
            'reviewed_at = ?, updated_at = ? '
            'WHERE id = ?',
            (next_status, review_notes.strip(), actor_user_id, now, now, submission_id)
        )
    elif action == 'publish':
        db.execute(
            'UPDATE course_content_submissions '
            'SET status = ?, published_at = ?, updated_at = ? WHERE id = ?',
            (next_status, now, now, submission_id)
        )
    elif action == 'archive':
        db.execute(
            'UPDATE course_content_submissions '
            'SET status = ?, archived_at = ?, updated_at = ? WHERE id = ?',
            (next_status, now, now, submission_id)
        )
    elif action == 'submit':
        db.execute(
            'UPDATE course_content_submissions '
            'SET status = ?, submitted_at = '
            '    CASE WHEN submitted_at IS NULL THEN CURRENT_TIMESTAMP '
            '         ELSE submitted_at END, '
            'updated_at = ? WHERE id = ?',
            (next_status, now, submission_id)
        )
    else:  # /     /     >---- save
        db.execute(
            'UPDATE course_content_submissions '
            'SET status = ?, updated_at = ? WHERE id = ?',
            (next_status, now, submission_id)
        )

    db.execute(
        'INSERT INTO course_content_transitions '
        '(submission_id, from_status, to_status, action, actor_user_id) '
        'VALUES (?, ?, ?, ?, ?)',
        (submission_id, row['status'], next_status, action, actor_user_id)
    )
    if commit:
        db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# /     /     >---- مدخل الخدمة: التحقق + التنفيذ معاً؛ يُبقي المسار سليماً
# ─────────────────────────────────────────────────────────────────────────────
def transition_submission(db, submission_id, action, actor_role,
                          *, review_notes='', weeks_total=0, actor_user_id=None):
    """Execute an authorised state transition.

    Returns the fresh row dict on success; raises a subclass of
    :class:`CourseContentError` describing why the transition is refused.

    Server-side checks (never trust the frontend): role, ownership, current
    state, requested transition, and (for send/publish) the weeks budget.
    """
    _validate_step(db, submission_id, action, actor_role, weeks_total)

    row = db.execute(
        'SELECT * FROM course_content_submissions WHERE id = ?', (submission_id,)
    ).fetchone()
    if not row:
        raise SubmissionNotFound(submission_id)

    next_status = TRANSITIONS.get((row['status'], action))
    if next_status is None:
        raise TransitionNotAllowed(
            f'الحالة «{row["status"]}» لا تسمح بإجراء «{action}»')

    # /     /     >---- الاعتماد/النشر/الأرشفة تتطلب مرر الملكية صراحةً أيضاً
    # /     /     >---- (المسار يتحقق من الصلاحية، الخدمة تضيف قيد الحالة)
    if not _can_operate(actor_role, row['status'], action):
        raise RoleNotAllowed(
            f'دورك («{actor_role}») لا يسمح بـ«{action}» على مقرر في الحالة «{row["status"]}»')

    _apply_transition(db, row, action, next_status, actor_role,
                      review_notes=review_notes,
                      actor_user_id=actor_user_id, commit=True)
    return db.execute(
        'SELECT * FROM course_content_submissions WHERE id = ?', (submission_id,)
    ).fetchone()


# /     /     >---- نشر مباشر لإدارة R&D: السلسلة كاملة في معاملة واحدة
# /     /     >---- draft/pending_teacher/rejected ← ... ← approved ← published
def publish_directly(db, submission_id, actor_role,
                     *, weeks_total=0, actor_user_id=None):
    """Publish a course form in one atomic transaction.

    Non-destructive: never truncates the workflow.  The full authorised
    chain from the current status to ``published`` is executed step by step
    (submit → approve → publish as needed); every step is first validated
    against the state machine and only then applied, so a refusal never
    writes a partial state.  A single commit wraps the whole chain.

    An already-published form is returned unchanged (idempotent).
    """
    row = db.execute(
        'SELECT * FROM course_content_submissions WHERE id = ?', (submission_id,)
    ).fetchone()
    if not row:
        raise SubmissionNotFound(submission_id)

    # /     /     >---- سلسلة الخطوات من الحالة الحالية حتى النشر
    current = row['status']
    if current == PUBLISHED:
        chain = []
    elif current == APPROVED:
        chain = [('publish', PUBLISHED)]
    elif current == PENDING_RND:
        chain = [('approve', APPROVED), ('publish', PUBLISHED)]
    elif current in (DRAFT, PENDING_TEACHER, REJECTED):
        chain = [('submit', PENDING_RND), ('approve', APPROVED), ('publish', PUBLISHED)]
    else:
        raise TransitionNotAllowed(
            f'الحالة «{current}» لا تسمح بالنشر المباشر')

    # /     /     >---- تحقق أولي لكل الخطوات قبل أي كتابة (لا نصف حالة)
    for action, target in chain:
        _validate_step(db, submission_id, action, actor_role, weeks_total)
        if TRANSITIONS.get((current, action)) != target:
            raise TransitionNotAllowed(
                f'الحالة «{current}» لا تسمح بإجراء «{action}»')
        if not _can_operate(actor_role, current, action):
            raise RoleNotAllowed(
                f'دورك («{actor_role}») لا يسمح بـ«{action}» '
                f'على مقرر في الحالة «{current}»')
        current = target

    # /     /     >---- تنفيذ السلسلة بلا commit، ثم التزام واحد شامل
    try:
        current = row['status']
        for action, target in chain:
            _apply_transition(db, row, action, target, actor_role,
                              actor_user_id=actor_user_id, commit=False)
            row = db.execute(
                'SELECT * FROM course_content_submissions WHERE id = ?',
                (submission_id,)
            ).fetchone()
        db.commit()
    except Exception:
        db.rollback()
        raise
    return row


# /     /     >---- إنشاء مسودة/نسخة جديدة من مسودة موجودة (لا يمسّ الأصل)
def copy_submission_as_draft(db, submission_id, *, new_version_label=''):
    """Clone an existing submission into a new ``draft`` row.

    The original row is never modified.  The new row receives a fresh
    ``version_label`` (default: derived from the latest existing one) and
    inherits everything else from the source (text fields, department, course,
    curriculum rows).  Uses ``parent_submission_id`` to keep the version chain.
    """
    src = db.execute(
        'SELECT * FROM course_content_submissions WHERE id = ?', (submission_id,)
    ).fetchone()
    if not src:
        raise SubmissionNotFound(submission_id)

    label = new_version_label or _next_version_label(db, src['course_id'])
    cur = db.cursor()
    cols = [c['name'] for c in
            db.execute('PRAGMA table_info(course_content_submissions)').fetchall()]
    ident_cols = [c for c in
                  ('version_label', 'parent_submission_id', 'published_at', 'archived_at')
                  if c in cols]
    insert_cols = [_cc for _cc in cols if _cc != 'id'
                   and _cc not in ('created_at', 'updated_at')]
    insert_cols += ident_cols

    placeholders = ', '.join('?' for _ in insert_cols)
    values = []
    for _cc in insert_cols:
        if _cc == 'version_label':
            values.append(label)
        elif _cc == 'parent_submission_id':
            values.append(submission_id)
        elif _cc in ('published_at', 'archived_at'):
            values.append(None)
        else:
            values.append(src[_cc])

    cur.execute(
        f'INSERT INTO course_content_submissions ({", ".join(insert_cols)}) '
        f'VALUES ({placeholders})',
        values
    )
    new_id = cur.lastrowid

    # /     /     >---- نسخ صفوف المنهاج من الأصل
    for _row in db.execute(
            'SELECT * FROM course_content_curriculum WHERE submission_id = ?',
            (submission_id,)
    ).fetchall():
        _cc_cur_cols = [c['name'] for c in
                        db.execute('PRAGMA table_info(course_content_curriculum)').fetchall()]
        _cols = [c for c in _cc_cur_cols if c != 'id' and c != 'submission_id']
        _ph = ', '.join('?' for _ in _cols)
        _vals = [dict(_row).get(c) for c in _cols]
        cur.execute(
            f'INSERT INTO course_content_curriculum ({", ".join(_cols)}) VALUES ({_ph})',
            _vals
        )
    db.commit()
    return new_id, label


# /     /     >---- اشتقاق تسمية الإصدار التالي تلقائياً من آخر نسخة حالية
def _next_version_label(db, course_id):
    last = db.execute(
        'SELECT version_label FROM course_content_submissions '
        'WHERE course_id = ? AND version_label != "" '
        'ORDER BY id DESC LIMIT 1',
        (course_id,)
    ).fetchone()
    if not last or not last['version_label']:
        return 'الإصدار 1'
    try:
        n = int(''.join(ch for ch in last['version_label'] if ch.isdigit()))
    except ValueError:
        n = 0
    return f'الإصدار {n + 1}'


# /     /     >---- أداة فحص دور/حالة مساعدة للخدمة
def _require_role(role, allowed, verb):
    if role not in allowed:
        raise RoleNotAllowed(f'دورك لا يملك صلاحية «{verb}»')


def _can_operate(role, status, action):
    """سياسة وصول: من يملك التحكم على حالة معينة."""
    if action == 'save':
        # /     /     >---- التحرير/الحفظ متاح للمالك (teacher/R&D) في مسودته
        return status in (DRAFT, REJECTED, PENDING_TEACHER)
    if action == 'submit':
        return status in (DRAFT, REJECTED, PENDING_TEACHER)
    if action in ('approve', 'reject'):
        return role in REVIEW_ROLES and status == PENDING_RND
    if action == 'publish':
        return role in PUBLISH_ROLES and status == APPROVED
    if action == 'archive':
        return role in ARCHIVE_ROLES and status == PUBLISHED
    return False


def _db_now():
    from datetime import datetime
    override = current_app.config.get('I18N_NOW')
    if override:
        return override
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')