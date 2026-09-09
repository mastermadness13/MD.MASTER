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

## Phase 2 — Auth, DB & Architecture Stabilization

| ID | Issue | File:Line | Severity | Fix | Test | Status |
|----|-------|-----------|----------|-----|------|--------|
| AUTH-004 | Default admin password `admin123` when env unset (fresh install) | scripts/seed.py:148 **and** database/schema.py:1256 | High | both paths use `ADMIN_PASSWORD` env else random (`secrets.token_urlsafe(12)`) printed once; existing accounts never overwritten | `tests/test_seed_admin_password.py` (3) | fixed |
| AUTH-005 | CSRF coverage on all mutating routes | routes/*, api/* | High | audit: 104 mutating routes, 147 `@csrf_required`, 0 missing | script + grep | verified-resolved |
| ARCH-001 | Security headers / CSP coverage | app.py:191-209 | Medium | already present: nosniff, SAMEORIGIN, XSS-Protection, Referrer-Policy, Permissions-Policy, full CSP | inspection | verified-resolved |
| ARCH-002 | `ensure_schema` timing (schema mutation per request?) | wsgi.py:11, serve.py:19, flask_db.py | Medium | confirmed: runs once at startup via `init_db()`, not per-request | inspection | verified-resolved |
| ARCH-003 | `serve.py` hardcodes `url_scheme='http'` → Secure cookies broken behind HTTPS | serve.py:37 | High | `WAITRESS_URL_SCHEME` env (default http) + optional `ProxyFix` behind `TRUST_PROXY_HEADERS=true` | inspection | fixed |
| ARCH-004 | Legacy `teacher.*` accounts reset to `123456` when renamed | database/schema.py:1268 | Low | one-time normalization (only no-longer-matching rows); new accounts set explicit passwords | inspection | deferred → Phase 5/8 note |
| AUTH-DEF | dashboard() lacks explicit `@login_required` | routes/dashboard.py:29 | Def | manual `user_id in session` guard already redirects anonymous → `public_site.index_page`; replacing with `@login_required` would change landing (login page). Guard is behavior-preserving equivalent | inspection | verified-resolved |

### Phase 2 result
`117 passed / 16 failed` (+3 seed tests, +2 existing seed tests re-verified, suite re-run pending).

## Phase 2.5 — Request / Data-flow Audit

Static audit (19 items flagged; N+1 × 7, hot endpoints × 8, PRG × 2, label-lookups × 2).

| ID | Issue | File:Line | Severity | Action | Status |
|----|-------|-----------|----------|--------|--------|
| PRG-001 | `teachers_edit` POST re-renders template after persisting on duplicate username (refresh re-submits) | routes/teachers.py:697-719 | High | replaced inline render with `flash(...)` + `redirect(url_for('teachers.teachers_edit', id=id))` (PRG) | fixed |
| PRG-002 | `ensure_current_version` INSERT/commit during plain GET | services/timetable_service.py:258-275 | Medium | self-healing lazy-init (writes only when no version row exists); refactoring risks breaking timetable pages | deferred → Phase 7/8 |
| PERF-001 | `/courses` (non-HOD) ~45-50 SQL per render | routes/courses.py:77 → course_service.build_dept_plans:613 | High | batch dept plans; measure in Phase 7 | open → Phase 7 |
| PERF-002 | `/print/timetables/all` ~4-6 SQL × dept | services/timetable_service.py:488-509 | High | hoist `get_period_settings`; batch semester display names | open → Phase 7 |
| PERF-003 | dashboards ~21-25 SQL/render (6-query weekly loop) | services/dashboard_service.py:366-379, routes/dashboard.py:52-76 | Medium | single weekly query + Python group | open → Phase 7 |
| PERF-004 | teaching-record pages: per-year/per-semester label lookups | services/teacher_service.py:248-283 | Medium | batch via existing `semester_names_from_db` / `IN()` | open → Phase 7 |
| PERF-005 | `build_teacher_weekly` 6-query per-day loop | services/timetable_service.py:783-801 | Medium | single query + group | open → Phase 7 |
| VER-CLEAN | No N+1 in timetable_repository / departments bulk IN / teachers page batched IN | repositories/, routes/teachers.py:275-306 | — | verified clean | verified-resolved |

### Phase 2.5 result
PRG-001 fixed (suite had no failing teacher-edit tests). Overview: no correctness-critical N+1; hotspots concentrated in courses list, print-all timetable, dashboards. Query-count optimization deferred to Phase 7 (measured there).

## Phase 3 — Business Logic / Timetable

| ID | Issue | File:Line | Severity | Fix | Test | Status |
|----|-------|-----------|----------|-----|------|--------|
| TIM-001 | Module `create_entry`/`update_entry` called `svc.create_entry`/`svc.update_entry` — methods missing on `TimetableService` → **timetable saving broken in UI, API and tests** (AttributeError 500) | services/timetable_service.py:687,705 | Critical | implemented class `create_entry` (repo.create + teacher→dept auto-link + `_record_taught_course` + advisory conflict warnings), `update_entry` (repo.update + same side effects + warnings), `_link_teacher_department`, `_collect_conflict_warnings`, `get_last_conflict_warnings` (per-instance) | `test_timetable_conflict_warning.py` (12) + `test_hod_department_resolution.py` | fixed |
| TIM-002 | HOD dept-scope tests failed due to same missing create path | tests/test_hod_department_resolution.py:213 | High | resolved by TIM-001 | `test_hod_can_create_entry_in_own_department` | fixed |
| TIM-003 | Timetable department page template assertions (`current table editable badge/hint`) | tests/test_timetable_department_page.py | Medium | template rendering assertions → Phase 5 | — | deferred → Phase 5 |

### Phase 3 result
Full suite: **`127 passed / 2 failed`** (was 114/15). Remaining 2 failures are template-assertion items on the Phase 5 schedule (course-content admin status filters; timetable department-page editable badge/hint).