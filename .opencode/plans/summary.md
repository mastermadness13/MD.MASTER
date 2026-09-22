# Session Summary

- Workdir: C:\Users\MD.MASTER\OneDrive\Desktop\newRopey_final_test (Flask, Arabic RTL)
- Status: PLAN MODE (read-only). No edits made yet.

## Objective
Fix state-sync mismatch between the unified timetable UI (/timetable/department + templates/timetable/unified.html + static/js/timetable_live.js) and the print page /print/timetables/department. UI shows dept + semester 4 courses; print shows "الفصل الثاني" with different courses. Print must be driven by UI live state: department_id + semester + version_id. Fix only; no redesign, no feature removal, no permission-rule changes; leave the uncommitted WIP set in git status untouched.

## Important Details
User's 5-point spec: (A) trace state UI->Print in unified.html + timetable_live.js; (B) add temporary console.debug('[TIMETABLE PRINT]', {departmentId, semester, versionId, printUrl}) before opening print; (C) audit print route: keep usable semester as-is, missing dept -> /timetable/department, HOD always uses hod_department_id, non-HOD applies session rules, never let semester=4 silently become 2; (D) pass the exact loaded version_id; (E) verify version fingerprints match on both sides.

Decisions from questions:
1. templates/timetable/unified.html is MISSING from disk -> recreate a functional thin wrapper that emits TIMETABLE_UNIFIED_BOOT wired to the existing timetable_live.js (page boots, tests pass).
2. /print/timetables/department with NO semester -> redirect to /timetable/department (no silent default).
3. Print header term line -> show selected semester (semester_label) instead of the global active_academic_label.

Root cause (confirmed by reading code):
- routes/print_routes.py:148 `semester = request.args.get('semester', type=int) or 1`: missing/invalid -> None -> 1 -> not allowed -> redirect to allowed[0] = 2 for non-general departments. Only confirmed code path that prints semester 2.
- services/timetable_service.py:384-385 get_department_view self-heals missing/invalid semester to available_semesters[0] (=2). Fine for the live page, must not be reached from print anymore.
- templates/print/timetables/_department_content.html:3 sem_label shows global term (e.g. خريف 2026) instead of selected semester, making the header look inconsistent.

Domain rules (services/timetable_scope.py): GENERAL_DEPT_NAME='القسم العام' -> only semester [1]; other depts -> [2..semesters] (max 8); INVALID_SEMESTER_MESSAGE='الفصل المختار غير مسموح لهذا القسم'; allowed_semesters_for, semester_token, validate_semester_allowed, InvalidSemesterError.

Test constraints that must keep passing:
- test_print_department_invalid_semester_redirects_to_allowed (general dept semester=2 -> 302 to semester=1).
- test_print_department_missing_dept_redirects_to_unified / unknown_dept (302 -> /timetable/department).
- test_print_department_hod_scoped_to_own_department.
- test_live_bundle_opens_print_route_with_live_state: reads static/js/timetable_live.js, requires BOOT.printUrl, searchParams.set('department_id', searchParams.set('semester', window.open(..., and CRITICALLY 'window.print()' NOT in js.
- test_unified_page_boots_live_assets and test_unified_page_wires_separate_print_route: HTML body must contain TIMETABLE_UNIFIED_BOOT, id="liveBadge", timetable_live.js, initialToken, syllabusUrls, printUrl, '/print/timetables/department'.

JS facts (timetable_live.js): BOOT keys required = base, api, payload, isRd, currentTeacherId, syllabusUrls, initialToken, printUrl. It RENDERS the grid/badges from payload (renderGrid/renderBadge/renderFilters/applyPayload/refreshAll) and touches DOM ids: printBtn, liveBadge, currentBadge, gridBody, gridDeptName, gridHead, mobileGrid, addLecBtn, nextYearBtn, toast, lecModal/lecOverlay + fields (lecDay, lecPeriod, lecHours, lecStartTime, lecEndTime, lecTeacherCtl/List, lecCourseCtl/List, lecWarn, lecHint), popupMenu/popupOverlay/popupContent/popupActions, nyModal/nyOverlay/nyInfo/nyWarn/nySeason/nyYear/nyCopy. Print handler (lines 1081-1088) already builds the correct URL from P.dept.id, P.selected_semester, P.current_version_id -> prints semester 4 correctly TODAY; only logging will be added.

_render_unified (routes/timetable.py:85-132): payload = get_department_view + can_manage/can_switch_department + form/vocab/syllabus + fingerprint (semester_token); ?format=json -> ok(payload) is what the live poller uses. Template receives: payload, user, nav_active, is_rd, current_teacher_id, initial_token, syllabus_urls.

print_timetable_department (print_routes.py:130-161): HOD -> hod_department_id; else dept_id or session.department_id; missing/unknown dept -> redirect to timetable_department_view; invalid semester -> redirect to allowed[0] keeping version_id; fingerprint = semester_token(db, dept_id, semester).

## Work State
### Completed
- Full trace done (read routes/timetable.py, print_routes.py, timetable_service.py view/semester functions, utils/format.py, print templates, base layout, JS bundle essentials). Root causes identified. Existing tests audited so they won't break. Choices confirmed via questions.
### Active
- Final plan ready below; awaiting approval to implement.
### Blocked
- None for this task. Environment notes (not blockers): templates/timetable/unified.html absent (to be recreated in step 1); templates/timetable/list.html, form.html, teacher.html are staged-deleted in git -> /print/timetable, /timetable/create, /timetable/teachers-schedule would 500. OUT OF SCOPE, not touched, flagged for the user.

## Next Move - THE PLAN
1. Create templates/timetable/unified.html (functional thin wrapper): extends shared/layouts/base.html; blocks title/head_extra/content/scripts; content includes toolbar (dept select for renderFilters, semester select, print button #printBtn, badges #liveBadge + #currentBadge), #gridBody + #mobileGrid, and the three modals (#lecModal, #popupMenu, #nyModal) with the DOM ids above; scripts block sets window.TIMETABLE_UNIFIED_BOOT = { payload: {{ payload|tojson }}, base: url_for('timetable.timetable_department_view'), api: url_for('timetable.timetable'), printUrl: url_for('print_routes.print_timetable_department'), isRd, currentTeacherId, syllabusUrls, initialToken } and loads static/js/timetable_live.js. Satisfies all six test markers.
2. Add diagnostic logging in timetable_live.js print handler (after building u, before window.open): console.debug('[TIMETABLE PRINT]', { departmentId: P.dept.id, semester: P.selected_semester, versionId: P.current_version_id || null, printUrl: u.toString() }). Keep 'window.print()' out of the file.
3. Fix print route (print_routes.py): change line 148 to semester = request.args.get('semester', type=int) (drop the `or 1`); after the dept-exists check, if semester is None: redirect to url_for('timetable.timetable_department_view', department_id=dept_id, version_id=version_id). Keep invalid-semester -> allowed[0] redirect with version_id (existing behavior/test). Add optional server-side debug log of dept/semester/version.
4. Fix print header term (templates/print/timetables/_department_content.html:3): sem_label = semester_label(payload.selected_semester) if payload.selected_semester else (payload.viewing_semester_name or payload.semester_name_ar or payload.semester_code or '—'). Stop using active_academic_label there so the sheet header matches the UI badge and the printed rows.
5. Add tests in tests/test_timetable_print_unified.py:
   - test_print_department_missing_semester_redirects_to_unified: /print/timetables/department?department_id=X -> 302, Location starts with /timetable/department.
   - test_print_department_semester_4_preserved_and_prints_fourth: seed a version for semester 4 in the fixture; request semester=4 -> 200, body contains 'الفصل الرابع' (proves 4 never becomes 2).
   - test_print_matches_live_fingerprint_and_semester: live /timetable/department?department_id=X&semester=4&format=json returns selected_semester==4 and fingerprint == semester_token(4); print with semester=4 body contains the same token.
6. Verify: python -m pytest tests/test_timetable_print_unified.py tests/test_timetable_unified_live.py -q, then full test suite; manual check in browser (badge الفصل الرابع, F12 console shows [TIMETABLE PRINT], print page shows same dept/semester/token as the live page).

## Relevant Files
- routes/timetable.py (unified renderers + _render_unified)
- static/js/timetable_live.js (print handler lines 1081-1088, BOOT keys, render fns)
- routes/print_routes.py (print_timetable_department lines 130-161)
- services/timetable_service.py (get_department_view 356-485, available_semesters_for 186, ensure_current_version 263)
- services/timetable_scope.py (allowed_semesters_for, semester_token, GENERAL_DEPT_NAME)
- templates/timetable/unified.html (MISSING - step 1 recreates)
- templates/print/timetables/_department_content.html (line 3 sem_label - step 4)
- templates/print/timetables/department.html, print/layouts/print.html, shared/layouts/base.html (layout blocks)
- utils/format.py (semester_label line 13)
- tests/test_timetable_print_unified.py, tests/test_timetable_unified_live.py (constraints + new tests)
- Out of scope: templates/timetable/list.html, form.html, teacher.html (staged-deleted, would 500)