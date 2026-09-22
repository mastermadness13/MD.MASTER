# Security Audit — newRopey (Zuwaita Technical Engineering College)

**Date:** 2026-09-21
**Scope:** quick/scoped defensive audit of selected trust surfaces (auth/session, authorization gate, CSRF, uploads, public APIs, input validation, misc hardening).
**Method:** source-first audit per `AgintGuid/security-audit-skill-main` (boundary + concrete result required for a finding; no checklist-only findings). Verified by targeted re-reads of the cited source.
**Deployment assumption:** single Waitress process (`serve.py`).

Severity legend: **HIGH** = explicit control defeated with real consequence · **MEDIUM** = real boundary violation, limited blast radius · **LOW** = confirmed minimal-impact / hardening · **OK** = verified mitigated, do not re-hunt.

---

## HIGH

### H1 — Path traversal / IDOR lets any staff role read any teacher's uploads
- **Location:** `routes/uploads.py:39-49`
- **Boundary:** lowest-trust authenticated role (`visitor` has `uploads.serve`) → every teacher's private uploads.
- **Mechanism:** the folder-ownership gate inspects only the first path segment — `folder = filename.split('/', 1)[0]`. `send_from_directory()` resolves `..` via `safe_join`. Waitress does not normalize dot-segments, so a request for `/uploads/teacher_<my_id>/<x>/../teacher_<victim_id>/<file>` (or `%2e%2e`) passes the gate and serves the victim's file. Teacher IDs are sequential ints; a victim filename is learnable from shared/listed links.
- **Fix (smallest):** reject any `..` (and `.`) segment before branching — `if '..' in filename or filename.startswith(('.', '/')): abort(403)`, or normalize with `os.path.normpath` first and verify the prefix.

### H2 — Course-content uploads accept arbitrary extensions → same-origin stored XSS / content spoofing
- **Location:** `routes/teacher_pages.py:931-936`; allowlist `ALLOWED_UPLOAD_EXTENSIONS` in `core/constants/uploads.py:7` is **dead code** (never imported).
- **Boundary:** any teacher uploading course content → every visitor to the same-origin served file.
- **Mechanism:** `ext = os.path.splitext(upload.filename)[1].lower() or '.pdf'` accepts `.html`, `.svg`, `.xml`, etc. The file is later served via `send_from_directory` with `as_attachment` **off** for some routes (`services/download_service.py:34-38,81-85` with `?download=1` only), so a `.html`/`.svg` file renders inline **on the app origin** and can run scripts with the logged-in user's session/CSRF context.
- **Fix (smallest):** enforce `ALLOWED_UPLOAD_EXTENSIONS` on this save path (same as the teacher-photo/attachment path already does), plus force `X-Content-Type-Options: nosniff` (already set) and serve uploads with `as_attachment=True` or `Content-Disposition: attachment` by default.

---

## MEDIUM

### M1 — Unpublished (draft/planned) exam schedules are public
- **Location:** `routes/public.py:206-223` + `exam_service.build_exam_schedule_view` (`exam_service.py`; row query at ~345-354 has no status filter); internal workspace legitimately needs draft rows.
- **Boundary:** anonymous visitor → internal exam planning data (dates, halls, per-cell status) before publication, incl. `room` `capacity` in options.
- **Fix:** add `published_only=True` to `build_exam_schedule_view` that drops cells whose `status not in ('scheduled','published')`; call it from the public route. Keep internal use unchanged.

### M2 — Login timing leaks valid usernames (CWE-204, mitigation broken by short-circuit)
- **Location:** `services/user_service.py:91` (`if user and check_password_hash(pw_hash, password)`)
- **Mechanism:** for a non-existent user `check_password_hash` is never invoked (instant return); existing accounts cost a full PBKDF2. The `_DUMMY_PASSWORD_HASH` intent (comment lines 88-89) is defeated.
- **Fix:** always compute: `ok = user and check_password_hash(pw_hash, password)` (still constant cost per attempt).

### M3 — Forgot-password timing equalization is inverted
- **Location:** `services/user_service.py:173-184`
- **Mechanism:** the dummy `check_password_hash` runs **only for unknown accounts**; known accounts do the fast DB insert. Unknown = slower. Response bodies are uniform (OK), but timing now discloses existence in the other direction.
- **Fix:** run one dummy hash unconditionally before the branch.

### M4 — `ProxyFix` trusts client `X-Forwarded-*` with no allowlist when enabled
- **Location:** `serve.py:41-42`
- **Mechanism:** `ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)` rewrites `REMOTE_ADDR`/`HTTP_HOST` from the rightmost header value of any peer. This (a) lets an attacker rotate the per-IP login/forgot/reset throttle key (`core/auth_limits.py` uses `request.remote_addr`), and (b) poisons `request.host` (feeds M5/M6). Default off — risk is when `TRUST_PROXY_HEADERS=true`.
- **Fix:** restrict to a trusted-proxy source set (`ProxyFix(..., x_for=1, x_proto=1, x_host=1)` only when the peer is a validated proxy IP), and confirm the fronting proxy overwrites inbound XFF.

### M5 — Host-header poisoning → open redirect + hijackable password-reset links
- **Location:** `utils/redirects.py:16-21` (referrer host == `request.host` check), `routes/auth.py:103` (`_external=True` reset URL), `config.py` (no `SERVER_NAME`/trusted-host list).
- **Mechanism:** `request.host` is taken verbatim from the (`X-Forwarded-`n) Host header. `Host: attacker.com` + same-host `Referer` passes the netloc check → `redirect_back()` (used on CSRF failure, AppError, 413/429) redirects off-origin; the reset email's `url_for(..., _external=True)` renders a link to the attacker domain (token exfil if followed).
- **Fix:** validate `request.host` against an explicit allowlist (`config.py` `TRUSTED_HOSTS`); build external URLs from a fixed base URL; move reset delivery to use the fixed base.

### M6 — Deny-by-default applies only to authenticated sessions
- **Location:** `app.py:164-199` (anonymous returns `None` untouched; endpoints without `_required_permission` are blocked only for logged-in users).
- **Mechanism:** any endpoint that forgets `@login_required` is fully public to anonymous **and** dead for authenticated users. Today nothing exploitable reachable this way (verified), and the `spa.app`/teachers-API/permission-less super-admin routes are effective no-ops.
- **Fix:** mirror the gate for anonymous users — allow only `PUBLIC_ENDPOINTS`+ prefixes, redirect the rest to login. This converts "public by omission" into "public by declaration."

### M7 — API permission check uses single active role; HTML uses granted-role union
- **Location:** `api/helpers.py:119-139` (`session.get('role')`) vs `security/authorization.py` `get_granted_roles()`.
- **Mechanism:** same logical permission grants in HTML but denies in SPA (or vice versa for uploads photos branch) for multi-role users. No escalation (union ⊇ single), but authorization is not a single coherent decision.
- **Fix:** `api_permission_required` should test membership over `session.get('roles', [])`.

### M8 — Session roles are a login-time snapshot; revocation invisible for up to 7 days
- **Location:** `services/user_service.py:122-126`; `routes/dashboard.py:13-33` (`switch_role` is dead — blocked by the gate, so neither escalation *nor* reachable downgrade).
- **Mechanism:** `find_roles_by_user` read once at login; DB role/permission changes are not honored until logout. No in-app escalation found, but stale grants persist.
- **Fix:** re-derive granted roles per request from the DB (cacheable) or invalidate sessions on role change; give `switch_role` a real permission or delete it.

### M9 — Public legacy JSON exposes teacher PII fields
- **Location:** `routes/public_site.py:54-56` → `static/public/data/teachers.json` (also duplicated in `templates/public/data/teachers.json`), served anonymously (the gate does not apply to anonymous users).
- **Mechanism:** schema includes `phone`, `academicNumber`, `nationalId`, `userId` per teacher. Current exported values are mostly empty, but the surface is there and the portal is public by design.
- **Fix:** whitelist output fields for public export (name, academicRank, department, qualification only); stop exporting `userId`/`nationalId`/`phone`/`academicNumber`.

### M10 — CSP relies on `unsafe-inline`/`unsafe-eval` (Tailwind CDN + inline scripts)
- **Location:** `app.py:289-299`.
- **Accepted tradeoff** documented in code; a hardening item — precompile/self-host Tailwind and move to nonce/hash-based script-src to drop both unsafe sources. Not actionable as a quick fix.

---

## LOW

### L1 — Logout is a GET without CSRF (forced log-out / CSRF logout)
- **Location:** `routes/auth.py:76-81`; SPA links at `static/js/spa/app.js:102-103,144-145`.
- **Fix:** `methods=['POST']` + `@csrf_required`; update links to POST (small form / fetch with `X-CSRFToken`).

### L2 — `/api/auth/me` and `/api/auth/logout` are blocked by the deny-by-default gate
- **Location:** `api/auth.py:78-91`; `app.py:180-189`.
- **Fix:** add `api_auth.api_me` (and mark `api_logout`) as public/gated-allow; the gate's denial branch should return JSON 403 for `/api/*` instead of an HTML redirect.

### L3 — Password-reset expiry uses local time vs SQLite UTC (`datetime("now")`) → window drift
- **Location:** `services/user_service.py:177` (local `datetime.now()`) vs `database/repositories/user_repository.py:193-194`.
- **Fix:** use `datetime.now(timezone.utc)` when stamping `expires`.

### L4 — `core/validators` is dead code; teacher PII stored unvalidated
- **Location:** `core/validators/__init__.py` (never imported), `api/teachers.py:24-52,81`, `routes/teachers.py:389-411`.
- **Fix:** apply email/phone/length validation on teacher create/update; return 422 on invalid.

### L5 — Course create skips validation the update path has
- **Location:** `api/courses.py:89-100` vs `:126` (name ≤255, numeric coerce/bounds for year/semester/hours).
- **Fix:** share one `_course_form` validation routine.

### L6 — API mutation endpoints accept unvalidated numerics/dates/times
- **Location:** `api/departments.py:34-51` (semesters/majors no bounds), `api/rooms.py:39-45` (`capacity>=1` no cap; `fk()` silently nulls non-numeric), `api/timetable.py:27-71` (`day` unwhitelisted, `hours` unbounded, `"25:99"` passes ordering), `api/exams.py:418-435` (start≤end unenforced, `proctors_per_room` unbounded).
- **Fix:** bounds + whitelists + time-format regex; return `{ok:false, errors}` instead of silent coercion.

### L7 — HOD / full-access roles missing, photos scoping single-role
- **Location:** `routes/uploads.py:10,44-46`; `core/constants/permissions.py`.
- **Fix:** populate `_FULL_ACCESS_ROLES` for audit roles, grant HOD `uploads.serve`, scope the photos branch via the granted-role union.

### L8 — Exam HOD scoping uses `users.department_id`, not session `hod_department_id`
- **Location:** `api/exams.py:27-35` (inconsistent with `api/timetable.py:107-129`).
- **Fix:** `session.get('hod_department_id') or user_data['department_id']`.

### L9 — Duplicated public data (maintenance/divergence trap)
- **Location:** `templates/public/data/` and `static/public/data/` (8 files).
- **Fix:** single source + generator (or document which is authoritative).

---

## Verified OK (do not re-hunt)

- **SQL injection:** all search/LIKE and list queries parameterized (`services/search.py:95-97`, `course_service.py:43-44`, `teacher_service.py:447-448`, `classroom_service.py:39-40`, `history_service.py:40-41`, `faculty_service.py:26-27`). No f-string user input into SQL.
- **Stored XSS (server):** sole `| safe` uses wrap `highlight_text()`, which HTML-escapes text and term before emitting `<mark>` (`services/search.py:291-307`).
- **Stored XSS (SPA):** all interpolations via `S.escapeHtml` (`static/js/spa/app.js:12-19`).
- **CSRF:** all 124 POST/PUT/PATCH/DELETE view functions carry `@csrf_required` (verified per-file); all 62 POST forms include the token; SPA sends `X-CSRFToken` on every state-changing fetch; CSRF-failure path returns JSON 403 / same-origin redirect. The only gap is GET `/logout` (L1).
- **Session fixation:** `session.clear()` + fresh `_csrf_token` at login; Secure/HttpOnly/SameSite=Lax cookies; 7-day lifetime.
- **Rate limiting:** form and API share one budget; per-username key normalized; limits reset on success. In-memory is fine for the single-process deployment.
- **Account-disclosure bodies:** uniform login/forgot responses; reset link disclosed only under `RESET_LINK_FALLBACK` (dev).
- **Secret handling:** `SECRET_KEY` env → persisted `.secret_key` (git-ignored); no hardcoded fallback.
- **Public library downloads:** only `approved`/`published` rows served (`download_service.py:42,60`).
- **Upload size/name in teacher paths:** 16 MB cap, per-teacher folders, uuid names in the photo/attachment paths; only the course-content path (H2) lacks the extension allowlist.

---

## Deployment notes (single Waitress process)

- Rate-limit storage is in-memory — acceptable for the 1-process assumption; switch to a shared backend if that changes (see Phase 4).
- `TRUST_PROXY_HEADERS=true` must be accompanied by an allowlisted trusted-proxy config (M4).
- If TLS is terminated at the proxy, keep `WAITRESS_URL_SCHEME=http` and rely on ProxyFix with restricted trust.

---

## Priority order for remediation

1. H1, H2  → HIGH, immediate.
2. M2, M3 (timing enumeration), M1 (public draft exams), M4/M5 (proxy+host trust).
3. M6–M10 and L1–L9 → hardening pass.

---

## Remediation status (updated 2026-09-21)

| Finding | Status | Change |
|---|---|---|
| H1 uploads traversal/IDOR | Done | `routes/uploads.py` rejects `.`/`..` segments (backslash-normalized) before the ownership gate; tests in `test_phase5_public_leaks.py`. |
| H2 arbitrary extension upload | Done | `routes/teacher_pages.py` course-content upload now enforces `ALLOWED_UPLOAD_EXTENSIONS` (was dead code); regression in `test_teacher_course_upload_page.py`. |
| L1 GET /logout | Done | `routes/auth.py` logout is POST + `@csrf_required`; SPA + both layouts + bottom nav updated; framework enforces tokens for all state-changing methods. |
| L2 gate blocking api me/logout | Done | `api_auth.api_me` / `api_auth.api_logout` added to `PUBLIC_ENDPOINTS` (`app.py`). |
| L4 dead `core/validators` | Done | Now real + used: `integer_between`, `valid_time`, `in_choices`, `valid_date_range`; unit tests added. |
| L5 course create/update validation | Done | Shared `_validate_course` in `api/courses.py` (name ≤255, code ≤30, year/semester 1–20, hours bounds). |
| L6 API numerics/times | Done | `api/rooms.py` capacity cap 500, `api/timetable.py` day whitelist + HH:MM format + hours bounds, `api/exams.py` settings/period time+date-range validation; 32 tests in `test_api_input_validation.py`. |
| M1 public draft exams | Done | `build_dept_exam_data(..., published_only=True)` applied to `/public/api/exam-schedule`; internal API unchanged. |
| M9 teachers.json PII | Done | `email`/`phone`/`academicNumber`/`nationalId`/`userId` scrubbed from the served `static/public/data/teachers.json`; tests added. |
| CSRF framework enforcement | Done | `security/csrf.py` `enforce_csrf` before-request hook; 11 route-map/behaviour tests in `test_csrf_coverage.py`. |
| Dead deps bleach/defusedxml | Done | `security/sanitize.py` gateway (XSS/XXE tests: `test_sanitize.py`). |
| Rate-limiter backend | Done | Pluggable storage in `core/rate_limiter.py` (in-memory default, shared SQLite via env); tests in `test_rate_limiter_backend.py`. |
| M2/M3 timing, M4 proxy, M5 host, M7 roles, M8 session, M10 CSP | Partial | Deferred in the main pass; see follow-up section below. M2/M3/M4/M10 now done; M5/M7/M8 remain deferred. |
| L9 duplicated public data | Done | `templates/public/` was a dead, untracked duplicate of the git-tracked `static/public/` portal; removed. `static/public/data/` (served by `public_site.data_files`) is the single source. |

Verification: full suite `354 passed` (was 272); smoke test boots the app on a fresh DB — `/login` 200, public exam JSON 200, tokenless API POST 403, anonymous POST /logout 302 same-origin, GET /logout 405.

---

## Follow-up hardening pass (updated 2026-09-21)

| Finding | Status | Change |
|---|---|---|
| M2 login timing (CWE-204) | Done | `user_service.authenticate` always runs `check_password_hash` (dummy hash for unknown users) before the `not user` guard. |
| M3 forgot-password timing | Done | `create_password_reset` runs one dummy hash unconditionally before the lookup branch. |
| M4 proxy header trust | Done | New `core/wsgi_proxy.py::build_wsgi_chain`; `serve.py` honors `X-Forwarded-*` ONLY from `TRUSTED_PROXY_IPS`, fails safe (ignores + warns) otherwise. Note: the fronting proxy must strip/overwrite inbound XFF. |
| M10 CSP hardening | Done | CSP gains `base-uri 'self'`, `object-src 'none'`, `form-action 'self'`. Script/style `unsafe-inline`/`unsafe-eval` tradeoff (Tailwind CDN) intentionally retained and documented. |
| L9 public data divergence | Done | See table above. |
| M8 session role staleness | Deferred | Real fix re-derives granted roles from the DB each request (or invalidates sessions on role change) — a hot-path behavior change; flagged not low-risk. Cookie flags (Secure/HttpOnly/SameSite=Lax) were already verified OK and are unchanged. |
| M5 host allowlist, M7 API role union | Deferred | Keep these separated from the low-risk pass; M5 also needs a fixed external base URL for reset links. |

Tests: `tests/test_low_risk_hardening.py` (M2/M3/M4/M10/L9, 8 tests). The suite's rate-limit tests were also made order-independent: `RateLimiter.reset_all()` + an autouse isolation fixture in `tests/conftest.py`.