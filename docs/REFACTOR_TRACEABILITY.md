# Refactor Traceability Matrix

Single source of truth. Status: `open` / `fixed` / `verified-resolved` / `deferred`.

Audit carried 194 findings. Baseline verified against current code, fixed item by item.

## Phase 0 — Baseline

| ID | Issue | File:Line | Severity | Fix | Test | Status |
|----|-------|-----------|----------|-----|------|--------|
| BASE-001 | No version control | repo root | Critical | `git init` + baseline commit `1d4a9ae`, .gitignore hardened (`.env`, `*.db`, stray `3`, non-ASCII folder, AI tooling, `_archive/`) | `git status` clean | fixed |
| BASE-002 | `.env` has live Gmail app password | `.env` | Critical | excluded from git; **credential rotation is a user action** | not committed | open (user rotation) |
| BASE-003 | Baseline test state unknown | repo | Medium | ran suite: 90 passed / 20 failed (12 = timetable conflicts) | pytest | fixed (recorded) |
| BASE-004 | Stray `3` SQLite DB (634 KB, 52 tables) | root/`3` | Medium | verified schema = old copy of `data.db`; gitignored | inspection | deferred → Phase 8 |
| BASE-005 | Stray `مشروع تخرح للكلية` folder | root | Low | empty/inaccessible (OneDrive unicode); gitignored | inspection | deferred → Phase 8 |
| BASE-006 | Dead student tables (`students`, `attendance`, `student_grades`) | database/schema.py:772-776 | Low | only referenced by DROP; `faculty_attendance` is LIVE | grep | deferred → Phase 8 |

## Phase 1 — Critical Security

| ID | Issue | File:Line | Severity | Fix | Test | Status |
|----|-------|-----------|----------|-----|------|--------|
| SEC-001 | Hardcoded SECRET_KEY fallback enables session forgery | config.py:12-16 | Critical | env → persisted `.secret_key` → random generated+persisted; no constant | `test_load_secret_key_*` (4) | fixed |
| SEC-002 | SESSION_COOKIE_SECURE missing | config.py | Critical | default True, env override + `.env.example` doc | `test_session_cookie_secure_*` (2) | fixed |
| DB-001 | `journal_mode=MEMORY` → data loss on crash | database/connection.py:21 | Critical | WAL + busy_timeout | `test_connection_uses_wal_journal_mode` | fixed |
| DB-002 | semesters table DROPPED every startup | database/schema.py:2670 | Critical | migration-log guard; runs once, preserves admin data | `test_migrate_to_named_semesters_*` (2) | fixed |
| SEC-003 | `highlight_text()` unescaped XSS (7 templates `| safe`) | services/search.py:282 | Critical | HTML-escape before `<mark>` injection | `test_highlight_text_*` (3) | fixed |
| AUTH-001 | API login has no throttle | api/auth.py:48 | Critical | shared `RateLimiter(5/60s)`, 429 on excess | `test_api_login_is_rate_limited` | fixed |
| AUTH-002 | switch-role POST lacks CSRF + blind referrer | routes/dashboard.py:11-22 | Critical | `@csrf_required` + `redirect_back(fallback)` | `test_switch_role_*` (3) | fixed |
| AUTH-003 | module `delete_user` bypasses super-admin guard | services/user_service.py:528 | Critical | delegate through guarded `UserService.delete_user` | `test_module_delete_user_*` (2) | fixed |
| SEC-004 | `_last_warnings` module-global (thread-unsafe) | services/timetable_service.py:677 | Critical | per-request `contextvars` | 16 existing conflict tests still run | fixed |
| SEC-005 | SQL injection `_archive_file_send` | routes/teacher_pages.py:1824 | Critical | function no longer exists in current code | grep | verified-resolved |
| SEC-DEF | dashboard() lacks `@login_required` | routes/dashboard.py:25 | High→Def | behavior-preserving change deferred | — | deferred → Phase 2 |

### Phase 1 result
`112 passed / 16 failed` (was 90/20). 12 of 16 are timetable conflict-detection (Phase 3; root cause: `TimetableService` has no `create_entry`), 2 are timetable department page template assertions (Phase 5), 1 HOD dept-resolution (Phase 3), 1 course-content admin status filters (Phase 5).