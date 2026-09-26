(function () {
  var BOOT = window.TIMETABLE_UNIFIED_BOOT || {};
  var BASE = BOOT.base || '/timetable/department';
  var API = BOOT.api || '/timetable';
  var CSRF = (function () {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  })();

  var P = BOOT.payload || {};
  var departments = P.departments || [];
  var teachers = P.teachers || [];
  var rooms = P.rooms || [];
  var courses = P.courses || [];
  var teacherCourses = P.teacherCourses || [];
  var periods = P.periods || [];
  var days = P.days || [];
  var availableSemesters = P.available_semesters || [];
  var entries = P.entries || [];
  var vocabMap = P.vocab || {};
  var syllabiMap = P.syllabus || {};
  var formMap = P.form || {};
  var isRd = !!BOOT.isRd;
  var currentTeacherId = BOOT.currentTeacherId || null;
  var SURLS = BOOT.syllabusUrls || {};

  var UNASSIGNED_LABEL = 'محاضرة بدون أستاذ';

  var selDept = P.dept ? P.dept.id : null;
  var selSem = P.selected_semester;
  var activeVersionId = P.current_version_id;
  var currentYear = P.active_academic_label || P.semester_code;
  var locked = !!(P.locked || !P.can_manage);
  var canSwitchDept = !!P.can_switch_department;

  var editingRowId = null;
  var popupId = null;
  var dragRowId = null;

  var H = window.TimetableHelpers.create({ periods: periods, base: BASE });
  var esc = H.esc, semesterNumLabel = H.semesterNumLabel, fmtTime12 = H.fmtTime12,
      periodTime = H.periodTime, entryTime = H.entryTime, periodByCode = H.periodByCode,
      typeLabel = H.typeLabel, cleanTeacher = H.cleanTeacher, durationLabel = H.durationLabel,
      fmtDate = H.fmtDate, qs = H.qs, nav = H.nav;

  function periodHeaderTime(p) {
    if (p && p.start_time) return fmtTime12(p.start_time) + (p.end_time ? ' إلى ' + fmtTime12(p.end_time) : '');
    return '';
  }
  function getTeacher(id) {
    for (var i = 0; i < teachers.length; i++) if (teachers[i].id === id) return teachers[i];
    return null;
  }
  function teacherCell(e) {
    if (e && e.teacher_id) return esc(cleanTeacher(e.teacher_name));
    return '<span class="tt-no-teacher">' + esc(UNASSIGNED_LABEL) + '</span>';
  }
  function getRoom(id) {
    for (var i = 0; i < rooms.length; i++) if (rooms[i].id === id) return rooms[i];
    return null;
  }
  function getCourseById(id) {
    for (var i = 0; i < courses.length; i++) if (courses[i].id === id) return courses[i];
    return null;
  }
  function applyPeriodDefaults() {
    var p = periodByCode(document.getElementById('lecPeriod').value);
    if (p) {
      document.getElementById('lecStartTime').value = p.start_time || '';
      document.getElementById('lecEndTime').value = p.end_time || '';
    }
  }
  function toast(msg, color) {
    var el = document.getElementById('toast');
    el.innerHTML = '<span class="material-symbols-outlined text-lg">' + (color === 'error' ? 'error' : 'check_circle') + '</span> ' + msg;
    el.className = 'fixed bottom-6 left-6 z-50 flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg text-sm font-semibold text-white ' + (color === 'error' ? 'bg-red-600' : 'bg-primary');
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.classList.add('hidden'); }, 3600);
  }
  function fetchPost(url, body, okMsg, redirectField) {
    var headers = { 'X-CSRFToken': CSRF };
    var opts = { method: 'POST', headers: headers };
    if (body instanceof FormData) { opts.body = body; }
    else { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    fetch(url, opts)
      .then(function (r) { return r.json().catch(function () { return { ok: false, message: 'استجابة غير متوقعة من الخادم.' }; }); })
      .then(function (d) {
        if (d && d.ok) {
          toast(okMsg || (d.message || 'تم بنجاح.'));
          if (redirectField && d[redirectField]) setTimeout(function () { location.href = d[redirectField]; }, 350);
          else setTimeout(function () { location.reload(); }, 350);
        }
        else { toast((d && d.message) || 'فشلت العملية.', 'error'); }
      })
      .catch(function () { toast('تعذر الاتصال بالخادم.', 'error'); });
  }

  // ── Filters (server-rendered) ─────────────────────────────
  function renderFilters() {
    var addBtn = document.getElementById('addLecBtn');
    var nyBtn = document.getElementById('nextYearBtn');
    if (addBtn) {
      if (locked) { addBtn.disabled = true; addBtn.classList.add('opacity-40', 'cursor-not-allowed', 'pointer-events-none'); }
      else { addBtn.disabled = false; addBtn.classList.remove('opacity-40', 'cursor-not-allowed', 'pointer-events-none'); }
    }
    if (nyBtn) {
      if (locked) { nyBtn.disabled = true; nyBtn.classList.add('opacity-40', 'cursor-not-allowed', 'pointer-events-none'); }
      else { nyBtn.disabled = false; nyBtn.classList.remove('opacity-40', 'cursor-not-allowed', 'pointer-events-none'); }
    }
  }

  // ── Grid ─────────────────────────────────────────────────
  function filteredRows() { return entries; }

  function renderGrid() {
    var tbody = document.getElementById('gridBody');
    var gdn = document.getElementById('gridDeptName');
    if (gdn && P.dept) gdn.textContent = P.dept.name;

    var ths = document.querySelectorAll('[data-period-header]');
    periods.forEach(function (p, i) {
      var th = ths[i];
      if (th) th.innerHTML = esc(p.label || p.code) + (periodHeaderTime(p) ? '<div class="text-[10px] text-on-surface-variant font-normal" dir="ltr">' + esc(periodHeaderTime(p)) + '</div>' : '');
    });
    for (var hi = periods.length; hi < ths.length; hi++) {
      if (ths[hi]) ths[hi].style.display = 'none';
    }

    var html = '';
    days.forEach(function (day) {
      html += '<tr class="border-b border-outline hover:bg-surface-container-low transition-colors">';
      html += '<td class="px-4 py-3 font-bold text-sm text-on-surface border-b border-outline bg-surface-dim h-[110px] align-middle w-[90px]">' + day + '</td>';
      periods.forEach(function (p) {
        var list = [];
        entries.forEach(function (e) { if (e.day === day && e.period === p.code) list.push(e); });
        if (list.length) {
          html += '<td class="px-1 py-2 align-stretch h-[110px]"><div class="flex flex-col gap-1 h-full">';
          list.forEach(function (e) {
            var startStr = e.start_time ? fmtTime12(e.start_time) : '';
            var endStr = e.end_time ? fmtTime12(e.end_time) : '';
            var timeStr = startStr && endStr ? startStr + ' ← ' + endStr : (startStr || entryTime(e));
            var formFile = formMap[e.course_id] || {};
            var syllabusFile = syllabiMap[e.teacher_id + ':' + e.course_id] || syllabiMap['*:' + e.course_id] || {};
            var updateHref = formFile.id ? '/teacher/super-admin/course-content/' + formFile.id : '/teacher/super-admin/course-content/create?course_id=' + e.course_id;
            html += '<div class="tt-cell cell-card drop-target bg-primary-container rounded-lg p-3 shadow-md text-[11px]"' +
              (locked ? '' : ' draggable="true"') +
              ' onclick="window.__ttOpenPopup(' + e.id + ')"' +
              (locked ? '' :
                ' ondragstart="window.__ttDragStart(event,' + e.id + ')" ondragend="window.__ttDragEnd(event)" ondragover="window.__ttDragOver(event)" ondragleave="window.__ttDragLeave(event)" ondrop="window.__ttDropSwapTarget(event,' + e.id + ')"') +
              '>' +
              '<h3 class="font-bold text-on-surface mb-1.5 text-xs">📘 مقرر: ' + esc(e.course_name || '—') + '</h3>' +
              '<div class="flex items-center gap-1.5 text-primary font-bold mb-1">' +
                '<span>⏰</span> <span>' + esc(timeStr) + '</span>' +
              '</div>' +
              '<div class="flex items-center gap-1.5 ' + (e.teacher_id ? 'text-on-surface-variant' : 'text-amber-700') + ' mb-1"><span class="material-symbols-outlined text-[14px]">person</span> ' + teacherCell(e) + '</div>' +
              '<div class="flex items-center gap-1.5 text-on-surface-variant mb-1"><span class="material-symbols-outlined text-[14px]">meeting_room</span> ' + esc(e.room_name || '—') + '</div>' +
              '<div class="flex items-center gap-1.5 text-on-surface-variant mb-2"><span class="material-symbols-outlined text-[14px]">schedule</span> ' + esc(typeLabel(e.lecture_type)) + (durationLabel(e) ? ' · ' + esc(durationLabel(e)) : '') + '</div>' +
              '<div class="text-[10px] mb-1.5 font-bold">' +
                '<span class="' + (formFile.url ? 'text-green-600' : 'text-red-400') + '">● مقرر</span> ' +
                '<span class="' + (syllabusFile.url ? 'text-green-600' : 'text-red-400') + ' ms-2">● منهاج</span>' +
              '</div>' +
              '<div class="flex flex-wrap gap-1.5">' +
                (formFile.url ? '<a href="' + formFile.url + (formFile.url.indexOf('?') >= 0 ? '&' : '?') + 'download=1" class="bg-primary text-white px-2 py-0.5 rounded text-[10px] font-bold">📄 تحميل المقرر</a>' : '<button disabled class="bg-gray-300 text-gray-600 px-2 py-0.5 rounded text-[10px] font-bold">📄 تحميل المقرر</button>') +
                (syllabusFile.url ? '<a href="' + syllabusFile.url + (syllabusFile.url.indexOf('?') >= 0 ? '&' : '?') + 'download=1" class="bg-primary text-white px-2 py-0.5 rounded text-[10px] font-bold">⬇️ تحميل المنهج</a>' : '<button disabled class="bg-gray-300 text-gray-600 px-2 py-0.5 rounded text-[10px] font-bold">⬇️ تحميل المنهج</button>') +
                (isRd ? '<a href="' + updateHref + '" class="bg-primary text-white px-2 py-0.5 rounded text-[10px] font-bold">📤 إنشاء/تعديل المقرر</a>' : '') +
                (locked ? '' : sylEditContent(e)) +
              '</div>' +
              '</div>';
          });
          html += '</div></td>';
        } else {
          html += '<td class="px-1 py-2 align-stretch h-[110px]">' +
            '<div class="tt-empty drop-target flex-1 mx-1 p-2 bg-surface-container-highest rounded-lg text-[11px] flex items-center justify-center cursor-pointer h-full"' +
            (locked ? '' : ' onclick="window.__ttOpenAdd(' + "'" + day + "'" + ',' + "'" + p.code + "'" + ')" ondragover="window.__ttDragOver(event)" ondragleave="window.__ttDragLeave(event)" ondrop="window.__ttDropTarget(event,' + "'" + day + "'" + ',' + "'" + p.code + "'" + ')"') +
            '>' +
            '<span class="text-xs text-on-surface-variant font-medium flex items-center justify-center gap-1">' + (locked ? '' : '<span class="material-symbols-outlined text-[13px]">add_circle</span>') + ' فارغ</span>' +
            '</div></td>';
        }
      });
      html += '</tr>';
    });
    tbody.innerHTML = html;
    renderBadge();
    renderMobileGrid();
  }

  // ── Content files: syllabus upload / delete (owner only) ─
  function sylEditContent(e) {
    if (locked) return '';
    var isOwner = isRd || (currentTeacherId && e.teacher_id === currentTeacherId);
    if (!isOwner) return '';
    var syllabusFile = syllabiMap[e.teacher_id + ':' + e.course_id] || syllabiMap['*:' + e.course_id] || {};
    var hasSyl = !!(syllabusFile && syllabusFile.url);
    var out = '';
    var up = isRd ? (SURLS.rdUpload || '').replace('{cid}', e.course_id) : (SURLS.teacherUpload || '');
    if (up) {
      out += '<form action="' + up + '" method="POST" enctype="multipart/form-data" class="inline-flex m-0">' +
        '<input type="hidden" name="_csrf_token" value="' + CSRF + '">' +
        (isRd ? '' : '<input type="hidden" name="course_id" value="' + e.course_id + '">') +
        '<label title="' + (hasSyl ? 'تحديد المنهج' : 'رفع المنهج') + '" class="w-6 h-6 flex items-center justify-center rounded bg-primary text-white hover:bg-primary/90 transition cursor-pointer">' +
          '<input type="file" name="file" accept=".pdf" onchange="this.form.submit()" class="hidden">' +
          '<span class="material-symbols-outlined text-sm">' + (hasSyl ? 'swap_vert' : 'upload_file') + '</span>' +
        '</label>' +
      '</form>';
    }
    if (hasSyl) {
      var del = isRd ? (SURLS.rdDelete || '').replace('{cid}', e.course_id) : (SURLS.teacherDelete || '').replace('{tfid}', syllabusFile.id);
      if (del) {
        out += '<form action="' + del + '" method="POST" onsubmit="return confirm(\'حذف ملف المنهج هذا؟\');" class="inline-flex m-0">' +
          '<input type="hidden" name="_csrf_token" value="' + CSRF + '">' +
          '<button type="submit" title="حذف المنهج" class="w-6 h-6 flex items-center justify-center rounded bg-red-50 text-red-600 border border-red-200 hover:bg-red-100 transition cursor-pointer">' +
            '<span class="material-symbols-outlined text-sm">delete</span>' +
          '</button>' +
        '</form>';
      }
    }
    return out;
  }

  // ── Mobile card list (phones <1024px) ──────────────────────
  function renderMobileGrid() {
    var wrap = document.getElementById('mobileGrid');
    if (!wrap) return;
    if (!entries.length) {
      wrap.innerHTML = '<div class="tt-mempty"><span class="material-symbols-outlined">calendar_today</span>لا توجد حصص مجدولة في هذا الجدول</div>';
      return;
    }
    var html = '';
    days.forEach(function (day) {
      var list = [];
      entries.forEach(function (e) { if (e.day === day) list.push(e); });
      if (!list.length) return;
      html += '<div class="tt-mday">' +
        '<div class="tt-mday-head"><span class="material-symbols-outlined">today</span><span>' + esc(day) + '</span><span class="tt-mday-count">' + list.length + ' محاضرة</span></div>' +
        '<div class="tt-mday-body">';
      list.forEach(function (e) {
        var startStr = e.start_time ? fmtTime12(e.start_time) : '';
        var endStr = e.end_time ? fmtTime12(e.end_time) : '';
        var timeStr = startStr && endStr ? startStr + ' ← ' + endStr : (startStr || entryTime(e));
        var formFile = formMap[e.course_id] || {};
        var syllabusFile = syllabiMap[e.teacher_id + ':' + e.course_id] || syllabiMap['*:' + e.course_id] || {};
        var updateHref = formFile.id ? '/teacher/super-admin/course-content/' + formFile.id : '/teacher/super-admin/course-content/create?course_id=' + e.course_id;
        html += '<div class="tt-mcard" onclick="window.__ttOpenPopup(' + e.id + ')">' +
          '<div class="tt-mcard-title">' +
            '<span>' + esc(e.course_name || '—') + '</span>' +
            (e.course_code ? '<span class="code">(' + esc(e.course_code) + ')</span>' : '') +
            '<span class="tt-mday-count" style="margin-inline-start:auto">' +
              '<span class="' + (formFile.url ? 'text-green-600' : 'text-red-400') + '">● مقرر</span> ' +
              '<span class="' + (syllabusFile.url ? 'text-green-600' : 'text-red-400') + '">● منهاج</span>' +
            '</span>' +
          '</div>' +
          '<div class="tt-mrow tt-mtime"><span class="material-symbols-outlined">schedule</span><span dir="ltr">' + esc(timeStr) + '</span>' + (durationLabel(e) ? '<span>· ' + esc(durationLabel(e)) + '</span>' : '') + '</div>' +
          '<div class="tt-mrow' + (e.teacher_id ? '' : ' tt-mrow-warn') + '"><span class="material-symbols-outlined">person</span>' + teacherCell(e) + '</div>' +
          '<div class="tt-mrow"><span class="material-symbols-outlined">meeting_room</span>' + esc(e.room_name || '—') + '</div>' +
          '<div class="tt-mrow"><span class="material-symbols-outlined">category</span>' + esc(typeLabel(e.lecture_type)) + '</div>' +
          '<div class="tt-actions">' +
            (formFile.url ? '<a class="tt-chip tt-chip-primary" href="' + formFile.url + (formFile.url.indexOf('?') >= 0 ? '&' : '?') + 'download=1"><span class="material-symbols-outlined">description</span> تحميل المقرر</a>' : '<button class="tt-chip tt-chip-primary" disabled><span class="material-symbols-outlined">description</span> لا يوجد مقرر</button>') +
            (syllabusFile.url ? '<a class="tt-chip tt-chip-soft" href="' + syllabusFile.url + (syllabusFile.url.indexOf('?') >= 0 ? '&' : '?') + 'download=1"><span class="material-symbols-outlined">download</span> تحميل المنهج</a>' : '<button class="tt-chip tt-chip-soft" disabled><span class="material-symbols-outlined">download</span> لا يوجد منهج</button>') +
            (isRd ? '<a class="tt-chip tt-chip-soft" href="' + updateHref + '"><span class="material-symbols-outlined">description</span> إنشاء/تعديل المقرر</a>' : '') +
            (locked ? '' : sylEditMobile(e)) +
          '</div>' +
        '</div>';
      });
      if (!locked) {
        html += '<button type="button" class="tt-mday-add" onclick="window.__ttOpenAdd(' + "'" + day + "'" + ')"><span class="material-symbols-outlined">add</span> إضافة محاضرة في ' + esc(day) + '</button>';
      }
      html += '</div></div>';
    });
    wrap.innerHTML = html;
  }

  function sylEditMobile(e) {
    if (locked) return '';
    var isOwner = isRd || (currentTeacherId && e.teacher_id === currentTeacherId);
    if (!isOwner) return '';
    var syllabusFile = syllabiMap[e.teacher_id + ':' + e.course_id] || syllabiMap['*:' + e.course_id] || {};
    var hasSyl = !!(syllabusFile && syllabusFile.url);
    var out = '';
    var up = isRd ? (SURLS.rdUpload || '').replace('{cid}', e.course_id) : (SURLS.teacherUpload || '');
    if (up) {
      out += '<form action="' + up + '" method="POST" enctype="multipart/form-data" class="m-0">' +
        '<input type="hidden" name="_csrf_token" value="' + CSRF + '">' +
        (isRd ? '' : '<input type="hidden" name="course_id" value="' + e.course_id + '">') +
        '<label class="tt-chip tt-chip-soft cursor-pointer" title="' + (hasSyl ? 'تحديد المنهج' : 'رفع المنهج') + '">' +
          '<input type="file" name="file" accept=".pdf" onchange="this.form.submit()" class="hidden">' +
          '<span class="material-symbols-outlined">' + (hasSyl ? 'swap_vert' : 'upload_file') + '</span> ' + (hasSyl ? 'تحديد المنهج' : 'رفع المنهج') +
        '</label>' +
      '</form>';
    }
    if (hasSyl) {
      var del = isRd ? (SURLS.rdDelete || '').replace('{cid}', e.course_id) : (SURLS.teacherDelete || '').replace('{tfid}', syllabusFile.id);
      if (del) {
        out += '<form action="' + del + '" method="POST" onsubmit="return confirm(\'حذف ملف المنهج هذا؟\');" class="m-0">' +
          '<input type="hidden" name="_csrf_token" value="' + CSRF + '">' +
          '<button type="submit" class="tt-chip tt-chip-danger"><span class="material-symbols-outlined">delete</span> حذف المنهج</button>' +
        '</form>';
      }
    }
    return out;
  }

  function renderBadge() {
    var b = document.getElementById('currentBadge');
    var chipCls = 'border-green-200 bg-green-50 text-green-700';
    var dotCls = 'bg-green-500';
    var label = 'الجدول الحالي · ' + (currentYear || '') + ' — ' + (locked ? 'للعرض فقط' : 'قابل للتعديل');
    b.className = 'mr-auto inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold border ' + chipCls;
    b.innerHTML =
      '<span class="flex flex-col items-end leading-tight">' +
        '<span class="flex items-center gap-1.5">' +
          '<span class="w-2 h-2 rounded-full ' + dotCls + '"></span>' +
          '<span>' + esc(label) + '</span>' +
        '</span>' +
      '</span>';

    var nyBtn = document.getElementById('nextYearBtn');
    if (nyBtn) {
      nyBtn.title = locked ? 'متاح على الجدول الحالي فقط' : 'إنشاء نسخة العام القادم';
    }
  }

  // ── Live sync (token polling) ─────────────────────────────
  var POLL_MS = 25000;
  var stateToken = BOOT.initialToken || '';
  var pollTimer = null;
  var syncing = false;

  function isBusy() {
    if (dragRowId !== null) return true;
    return !document.getElementById('lecModal').classList.contains('hidden')
        || !document.getElementById('popupMenu').classList.contains('hidden')
        || !document.getElementById('nyModal').classList.contains('hidden');
  }
  function flashLive() {
    var b = document.getElementById('liveBadge');
    if (!b) return;
    b.classList.remove('hidden');
    b.classList.add('inline-flex');
    b.style.opacity = '1';
    clearTimeout(b._t);
    b._t = setTimeout(function () { b.classList.add('hidden'); b.classList.remove('inline-flex'); }, 4000);
  }
  function applyPayload(p) {
    P = p;
    departments = p.departments || [];
    teachers = p.teachers || [];
    rooms = p.rooms || [];
    courses = p.courses || [];
    teacherCourses = p.teacherCourses || [];
    periods = p.periods || [];
    days = p.days || [];
    availableSemesters = p.available_semesters || [];
    entries = p.entries || [];
    vocabMap = p.vocab || {};
    syllabiMap = p.syllabus || {};
    formMap = p.form || {};
    selDept = p.dept ? p.dept.id : null;
    selSem = p.selected_semester;
    activeVersionId = p.current_version_id;
    currentYear = p.active_academic_label || p.semester_code;
    locked = !!(p.locked || !p.can_manage);
    canSwitchDept = !!p.can_switch_department;
    H = window.TimetableHelpers.create({ periods: periods, base: BASE });
    esc = H.esc; semesterNumLabel = H.semesterNumLabel; fmtTime12 = H.fmtTime12;
    periodTime = H.periodTime; entryTime = H.entryTime; periodByCode = H.periodByCode;
    typeLabel = H.typeLabel; cleanTeacher = H.cleanTeacher; durationLabel = H.durationLabel;
    fmtDate = H.fmtDate; qs = H.qs; nav = H.nav;
  }
  function renderAll() {
    if (!P.dept) {
      document.getElementById('gridBody').innerHTML = '<tr><td colspan="' + Math.max(2, periods.length + 1) + '" class="py-16 text-center text-on-surface-variant">اختر قسماً لعرض الجدول الأسبوعي</td></tr>';
      var mw = document.getElementById('mobileGrid');
      if (mw) mw.innerHTML = '<div class="tt-mempty"><span class="material-symbols-outlined">domain</span>اختر قسماً لعرض جدوله الأسبوعي</div>';
      var addBtn = document.getElementById('addLecBtn');
      if (addBtn) addBtn.disabled = true;
      var nyBtn = document.getElementById('nextYearBtn');
      if (nyBtn) nyBtn.disabled = true;
      return;
    }
    renderFilters();
    renderGrid();
  }
  function refreshAll() {
    if (syncing) return;
    syncing = true;
    fetch(BASE + '?department_id=' + selDept + '&semester=' + selSem + '&format=json',
          { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
      .then(function (d) {
        if (d && d.ok && d.data) {
          applyPayload(d.data);
          renderAll();
          flashLive();
        }
      })
      .catch(function () {})
      .then(function () { syncing = false; });
  }
  function pollToken() {
    if (document.hidden) return;
    if (isBusy()) return;
    fetch(API + '/api/timetable/version/token?department_id=' + selDept + '&semester=' + selSem)
      .then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
      .then(function (d) {
        if (d && d.ok && d.data && d.data.token) {
          if (stateToken !== d.data.token) {
            stateToken = d.data.token;
            refreshAll();
          }
        }
      })
      .catch(function () {});
  }
  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollToken, POLL_MS);
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden && selDept) pollToken();
    });
    window.addEventListener('focus', function () {
      if (selDept) pollToken();
    });
  }

  // ── Next year ────────────────────────────────────────────
  function openNextYear() {
    if (locked) { toast('لا يمكن إنشاء نسخة من جدول للعرض فقط.', 'error'); return; }
    document.getElementById('nyInfo').textContent = 'سيُفتح جدول جديد فارغ للقسم «' + (P.dept ? P.dept.name : '') + '» الفصل ' + semesterNumLabel(selSem) + '. يُحفظ الجدول الحالي ويُنشأ الجدول الجديد.';
    document.getElementById('nyWarn').classList.add('hidden');
    document.getElementById('nySeason').value = '';
    document.getElementById('nyYear').value = '';
    document.getElementById('nyOverlay').classList.remove('hidden');
    document.getElementById('nyModal').classList.remove('hidden');
  }
  function closeNextYear() {
    document.getElementById('nyOverlay').classList.add('hidden');
    document.getElementById('nyModal').classList.add('hidden');
  }
  function createNextYear() {
    var copy = document.getElementById('nyCopy').checked;
    var season = document.getElementById('nySeason').value || '';
    var yearVal = document.getElementById('nyYear').value.trim();
    var year = yearVal ? parseInt(yearVal, 10) : null;
    var payload = { version_id: activeVersionId, copy_entries: copy };
    if (season) payload.season = season;
    if (year) payload.year = year;
    var headers = { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF };
    fetch(API + '/api/version/create-next', { method: 'POST', headers: headers, body: JSON.stringify(payload) })
      .then(function (r) { return r.json().catch(function () { return { ok: false, message: 'استجابة غير متوقعة من الخادم.' }; }); })
      .then(function (d) {
        if (d && d.ok) {
          closeNextYear();
          toast(d.message || 'تم إنشاء النسخة بنجاح.');
          if (d.url && selDept) setTimeout(function () { location.href = d.url; }, 400);
          else setTimeout(function () { location.reload(); }, 400);
        }
        else if (d && d.duplicate) {
          var warnBox = document.getElementById('nyWarn');
          warnBox.querySelector('span').innerText = (d.message || 'توجد نسخة لهذا الفصل/العام مسبقًا — اختر تاريخًا مختلفًا.');
          warnBox.classList.remove('hidden');
        }
        else { toast((d && d.message) || 'فشل إنشاء النسخة.', 'error'); }
      })
      .catch(function () { toast('تعذر الاتصال بالخادم.', 'error'); });
  }

  // ── Popup ────────────────────────────────────────────────
  function findEntry(id) {
    for (var i = 0; i < entries.length; i++) if (entries[i].id === id) return entries[i];
    return null;
  }
  function openPopup(id) {
    var e = findEntry(id);
    if (!e) return;
    popupId = id;
    var content = document.getElementById('popupContent');
    if (locked) {
      content.innerHTML =
        '<div class="bg-gradient-to-l from-primary/5 to-transparent border border-outline-variant rounded-xl p-4">' +
          '<div class="text-primary text-sm font-bold mb-1">' + esc(e.course_name || '—') + ' <span class="text-xs text-on-surface-variant font-normal">(' + esc(e.course_code || '') + ')</span></div>' +
          '<div class="text-xs text-on-surface-variant">' + (P.dept ? esc(P.dept.name) : '—') + ' — ' + currentYear + ' / الفصل ' + semesterNumLabel(e.semester) + '</div>' +
        '</div>' +
        '<div class="grid grid-cols-2 gap-3">' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">person</span><span class="text-xs text-on-surface-variant">عضو هيئة التدريس</span></div>' +
            '<div class="text-sm font-semibold ' + (e.teacher_id ? 'text-on-surface' : 'text-amber-700') + '">' + teacherCell(e) + '</div>' +
          '</div>' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">meeting_room</span><span class="text-xs text-on-surface-variant">القاعة</span></div>' +
            '<div class="text-sm font-semibold text-on-surface">' + esc(e.room_name || '—') + '</div>' +
          '</div>' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">today</span><span class="text-xs text-on-surface-variant">اليوم / الفترة</span></div>' +
            '<div class="text-sm font-semibold text-on-surface">' + esc(e.day) + ' — ' + esc(e.period) + '</div>' +
          '</div>' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">schedule</span><span class="text-xs text-on-surface-variant">الوقت</span></div>' +
            '<div class="text-sm font-semibold text-on-surface" dir="ltr">' + esc(periodTime(periodByCode(e.period))) + '</div>' +
          '</div>' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">category</span><span class="text-xs text-on-surface-variant">النوع</span></div>' +
            '<div class="text-sm font-semibold text-on-surface">' + typeLabel(e.lecture_type) + (durationLabel(e) ? ' — ' + durationLabel(e) : '') + '</div>' +
          '</div>' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">verified</span><span class="text-xs text-on-surface-variant">الإصدار</span></div>' +
            '<div class="text-sm font-semibold text-on-surface">' + esc(currentYear) + ' — ' + 'للعرض فقط' + '</div>' +
          '</div>' +
        '</div>' +
        fileActionsContent(e);
      document.getElementById('popupActions').style.display = 'none';
    } else {
      content.innerHTML =
        '<div class="bg-gradient-to-l from-primary/5 to-transparent border border-outline-variant rounded-xl p-4">' +
          '<div class="text-primary text-sm font-bold mb-1">' + esc(e.course_name || '—') + ' <span class="text-xs text-on-surface-variant font-normal">(' + esc(e.course_code || '') + ')</span></div>' +
          '<div class="text-xs text-on-surface-variant">' + (P.dept ? esc(P.dept.name) : '—') + ' — ' + currentYear + ' / الفصل ' + semesterNumLabel(e.semester) + '</div>' +
        '</div>' +
        '<div class="grid grid-cols-2 gap-3">' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">person</span><span class="text-xs text-on-surface-variant">عضو هيئة التدريس</span></div>' +
            '<div class="text-sm font-semibold ' + (e.teacher_id ? 'text-on-surface' : 'text-amber-700') + '">' + teacherCell(e) + '</div>' +
          '</div>' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">meeting_room</span><span class="text-xs text-on-surface-variant">القاعة</span></div>' +
            '<div class="text-sm font-semibold text-on-surface">' + esc(e.room_name || '—') + '</div>' +
          '</div>' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">today</span><span class="text-xs text-on-surface-variant">اليوم / الفترة</span></div>' +
            '<div class="text-sm font-semibold text-on-surface">' + esc(e.day) + ' — ' + esc(e.period) + '</div>' +
          '</div>' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">schedule</span><span class="text-xs text-on-surface-variant">الوقت</span></div>' +
            '<div class="text-sm font-semibold text-on-surface" dir="ltr">' + esc(periodTime(periodByCode(e.period))) + '</div>' +
          '</div>' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">category</span><span class="text-xs text-on-surface-variant">النوع</span></div>' +
            '<div class="text-sm font-semibold text-on-surface">' + typeLabel(e.lecture_type) + (durationLabel(e) ? ' — ' + durationLabel(e) : '') + '</div>' +
          '</div>' +
          '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
            '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-base">verified</span><span class="text-xs text-on-surface-variant">الإصدار</span></div>' +
            '<div class="text-sm font-semibold text-on-surface">' + esc(currentYear) + ' — ' + (locked ? 'للعرض فقط' : 'محفوظ') + '</div>' +
          '</div>' +
        '</div>' +
        fileActionsContent(e);
      document.getElementById('popupActions').style.display = '';
    }
    document.getElementById('popupOverlay').classList.remove('hidden');
    document.getElementById('popupMenu').classList.remove('hidden');
  }
  function fileActionsContent(e) {
    var formFile = formMap[e.course_id] || {};
    var syllabusFile = syllabiMap[e.teacher_id + ':' + e.course_id] || syllabiMap['*:' + e.course_id] || {};
    var html = '<div class="bg-surface border border-outline-variant rounded-xl p-3">' +
      '<div class="text-xs text-on-surface-variant font-bold mb-2 border-b border-outline-variant pb-2 flex items-center gap-1.5"><span class="material-symbols-outlined text-primary text-base">folder_open</span> ملفات المقرر</div>' +
      '<div class="flex flex-wrap gap-2">';
    if (formFile.url) {
      html += '<a class="tt-chip tt-chip-primary" href="' + formFile.url + (formFile.url.indexOf('?') >= 0 ? '&' : '?') + 'download=1" target="_blank" rel="noopener"><span class="material-symbols-outlined">description</span> تحميل المقرر</a>';
    } else {
      html += '<button class="tt-chip tt-chip-primary" disabled><span class="material-symbols-outlined">description</span> لا يوجد مقرر</button>';
    }
    if (syllabusFile.url) {
      html += '<a class="tt-chip tt-chip-soft" href="' + syllabusFile.url + (syllabusFile.url.indexOf('?') >= 0 ? '&' : '?') + 'download=1" target="_blank" rel="noopener"><span class="material-symbols-outlined">download</span> تحميل المنهج</a>';
    } else {
      html += '<button class="tt-chip tt-chip-soft" disabled><span class="material-symbols-outlined">download</span> لا يوجد منهج</button>';
    }
    html += '</div></div>';
    return html;
  }
  function closePopup() {
    document.getElementById('popupOverlay').classList.add('hidden');
    document.getElementById('popupMenu').classList.add('hidden');
  }

  // ── Modal add / edit ─────────────────────────────────────
  function showWarn(msg) {
    var w = document.getElementById('lecWarn');
    w.querySelector('span:last-child').textContent = msg;
    w.classList.remove('hidden');
  }
  function hideWarn() { document.getElementById('lecWarn').classList.add('hidden'); }
  function showHint(msg) {
    var h = document.getElementById('lecHint');
    h.querySelector('span:last-child').textContent = msg;
    h.classList.remove('hidden');
  }
  function hideHint() { document.getElementById('lecHint').classList.add('hidden'); }

  function deptCourses() {
    var out = [];
    var modalDept = parseInt(document.getElementById('lecDept').value, 10) || selDept;
    var modalSemester = parseInt(document.getElementById('lecSemester').value, 10) || selSem;
    courses.forEach(function (c) {
      if (c.deptIds && c.deptIds.indexOf(modalDept) === -1) return;
      var m = c.deptSemesters || {};
      var sem = m[modalDept] != null ? m[modalDept] : (c.semester || null);
      if (sem != null && sem !== modalSemester) return;
      out.push(c);
    });
    return out;
  }
  function setModalSemesters(semesters, selected) {
    var semSel = document.getElementById('lecSemester');
    semSel.innerHTML = '';
    semesters.forEach(function (semester) {
      semSel.insertAdjacentHTML('beforeend',
        '<option value="' + semester + '">الفصل ' +
        esc(semesterNumLabel(semester)) + '</option>');
    });
    semSel.value = String(selected || '');
    semSel.disabled = semesters.length === 0;
  }
  function populateModal() {
    var deptEl = document.getElementById('lecDept');
    if (deptEl.tagName === 'SELECT') {
      deptEl.innerHTML = '';
      departments.forEach(function (d) {
        deptEl.insertAdjacentHTML('beforeend',
          '<option value="' + d.id + '">' + esc(d.name) + '</option>');
      });
    } else {
      deptEl.value = selDept || '';
    }
    setModalSemesters(availableSemesters, selSem);

    var daySel = document.getElementById('lecDay');
    daySel.innerHTML = '';
    days.forEach(function (d) {
      daySel.insertAdjacentHTML('beforeend', '<option value="' + esc(d) + '">' + esc(d) + '</option>');
    });
    var pSel = document.getElementById('lecPeriod');
    pSel.innerHTML = '';
    periods.forEach(function (p) {
      pSel.insertAdjacentHTML('beforeend', '<option value="' + esc(p.code) + '">' + esc(p.code) + ' — ' + esc(periodTime(p)) + '</option>');
    });
    var rSel = document.getElementById('lecRoom');
    rSel.innerHTML = '';
    rooms.forEach(function (r) {
      rSel.insertAdjacentHTML('beforeend', '<option value="' + r.id + '">' + esc(r.name_ar || r.name) + '</option>');
    });
  }

var teacherPool = [];
var coursePool = [];
var availableTeacherIds = null;
function teacherAvailable(id) {
  return availableTeacherIds === null || availableTeacherIds.indexOf(id) !== -1;
}
function refreshTeachersAvailability() {
  var params = {
    day: document.getElementById('lecDay').value,
    period_code: document.getElementById('lecPeriod').value,
    start_time: document.getElementById('lecStartTime').value,
    end_time: document.getElementById('lecEndTime').value,
    hours: parseInt(document.getElementById('lecHours').value, 10) || 1
  };
  if (editingRowId) params.exclude_id = editingRowId;
  return fetch(API + '/api/available-teachers' + qs(params))
    .then(function (resp) { return resp.json(); })
    .then(function (d) {
      var list = (d && d.data && d.data.teachers) || [];
      availableTeacherIds = [];
      list.forEach(function (t) { availableTeacherIds.push(t.id); });
      var picked = document.getElementById('lecTeacher');
      if (picked && picked.value && availableTeacherIds.indexOf(parseInt(picked.value, 10)) === -1) {
        picked.value = '';
        document.getElementById('lecTeacherSearch').value = '';
      }
      return availableTeacherIds;
    })
    .catch(function () { return null; });
}
function buildTeacherPool() {
  teacherPool = [];
  teacherPool.push({ id: '', name: UNASSIGNED_LABEL, search: UNASSIGNED_LABEL, home: false, clear: true });
  teachers.forEach(function (t) {
    if (!teacherAvailable(t.id)) return;
    teacherPool.push({
      id: t.id,
      name: String(t.name != null ? t.name : ''),
      search: String(t.name != null ? t.name : ''),
      home: !!(selDept && t.department_id && t.department_id === selDept)
    });
  });
  teacherPool.sort(function (a, b) {
    if (a.home !== b.home) return a.home ? -1 : 1;
    return a.name < b.name ? -1 : (a.name > b.name ? 1 : 0);
  });
}
  function buildCoursePool() {
    coursePool = [];
    deptCourses().forEach(function (c) {
      var name = String(c.name != null ? c.name : '');
      var code = String(c.code != null ? c.code : '');
      coursePool.push({
        id: c.id,
        name: name,
        code: code,
        search: (name + ' ' + code).trim(),
        display: name + (code ? ' (' + code + ')' : ''),
        detail: name + (code ? ' (' + code + ')' : '') + ' — نظري ' + (c.theory || 0) + '/عملي ' + (c.practical || 0)
      });
    });
    coursePool.sort(function (a, b) {
      return a.name < b.name ? -1 : (a.name > b.name ? 1 : 0);
    });
  }

  var AR_NO_ROOMS = 'لا توجد قاعات متاحة في هذا التوقيت';
  function isLabRoom(r) {
    if (!r) return false;
    if (r.css_class === 'lab') return true;
    return String(r.name_ar || '').indexOf('معمل') !== -1;
  }
  function natKey(name) {
    return String(name == null ? '' : name).split(/(\d+)/).map(function (t) {
      var n = parseInt(t, 10);
      return isNaN(n) ? t : ('000000' + n).slice(-7);
    }).join('\u0001');
  }
  function sortRooms(list) {
    list.sort(function (a, b) {
      var la = isLabRoom(a) ? 1 : 0, lb = isLabRoom(b) ? 1 : 0;
      if (la !== lb) return la - lb;
      var ka = natKey(a.name_ar), kb = natKey(b.name_ar);
      return ka < kb ? -1 : (ka > kb ? 1 : 0);
    });
  }
  function refreshRoomOptions(keepId) {
    var rSel = document.getElementById('lecRoom');
    if (!rSel) return;
    var prev = (keepId !== undefined && keepId !== null) ? keepId : (parseInt(rSel.value, 10) || 0);
    var params = {
      day: document.getElementById('lecDay').value,
      period_code: document.getElementById('lecPeriod').value,
      start_time: document.getElementById('lecStartTime').value,
      end_time: document.getElementById('lecEndTime').value,
      hours: parseInt(document.getElementById('lecHours').value, 10) || 1
    };
    if (editingRowId) params.exclude_id = editingRowId;
    fetch(API + '/api/available-rooms' + qs(params))
      .then(function (resp) { return resp.json(); })
      .then(function (d) {
        var list = (d && d.data && d.data.rooms) || [];
        sortRooms(list);
        rSel.innerHTML = '';
        if (!list.length) {
          rSel.insertAdjacentHTML('beforeend', '<option value="">— ' + AR_NO_ROOMS + ' —</option>');
          return;
        }
        var found = false;
        list.forEach(function (r) {
          if (r.id === prev) found = true;
          rSel.insertAdjacentHTML('beforeend', '<option value="' + r.id + '">' + esc(r.name_ar || r.name) + '</option>');
        });
        if (found) rSel.value = String(prev);
        else rSel.value = String(list[0].id);
      })
      .catch(function () { /* keep current options on network failure */ });
  }

  function renderList(listEl, pool, q, emptyText, onPick, badgeFn) {
    listEl.innerHTML = '';
    var shown = 0;
    q = (q || '').trim();
    pool.forEach(function (item) {
      if (q && item.search.indexOf(q) === -1) return;
      shown++;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'w-full text-right px-3 py-2 text-sm text-on-surface hover:bg-primary-container transition flex items-center justify-between gap-2';
      var html = '<span>' + esc(item.detail || item.name) + '</span>';
      var badge = badgeFn ? badgeFn(item) : '';
      if (badge) html += '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-primary-container text-primary shrink-0">' + esc(badge) + '</span>';
      btn.innerHTML = html;
      btn.addEventListener('click', function () { onPick(item); });
      listEl.appendChild(btn);
    });
    if (!shown) {
      listEl.insertAdjacentHTML('beforeend', '<div class="px-3 py-3 text-sm text-on-surface-variant">' + esc(emptyText) + '</div>');
    }
    listEl.classList.remove('hidden');
  }
  function closeLists(exceptId) {
    ['lecTeacherList', 'lecCourseList'].forEach(function (id) {
      if (id !== exceptId) document.getElementById(id).classList.add('hidden');
    });
  }
  function openTeacherList() {
    buildTeacherPool();
    closeLists('lecTeacherList');
    renderList(document.getElementById('lecTeacherList'), teacherPool,
      '', 'لا توجد نتائج مطابقة', pickTeacher,
      function (t) { return t.home && P.dept ? P.dept.name : ''; });
  }
  function filterTeacherList() {
    var pickedId = document.getElementById('lecTeacher').value;
    if (pickedId) {
      var pickedT = getTeacher(parseInt(pickedId, 10));
      if (!pickedT || document.getElementById('lecTeacherSearch').value !== pickedT.name) {
        document.getElementById('lecTeacher').value = '';
      }
    }
    renderList(document.getElementById('lecTeacherList'), teacherPool,
      document.getElementById('lecTeacherSearch').value, 'لا توجد نتائج مطابقة', pickTeacher,
      function (t) { return t.home && P.dept ? P.dept.name : ''; });
  }
  function openCourseList() {
    buildCoursePool();
    closeLists('lecCourseList');
    renderList(document.getElementById('lecCourseList'), coursePool,
      '', 'لا توجد مقررات مسجلة لهذا القسم', pickCourse, null);
  }
  function filterCourseList() {
    var pickedId = document.getElementById('lecCourse').value;
    if (pickedId) {
      var pickedC = getCourseById(parseInt(pickedId, 10));
      if (!pickedC || document.getElementById('lecCourseSearch').value !== (pickedC.name + (pickedC.code ? ' (' + pickedC.code + ')' : ''))) {
        document.getElementById('lecCourse').value = '';
      }
    }
    renderList(document.getElementById('lecCourseList'), coursePool,
      document.getElementById('lecCourseSearch').value, 'لا توجد مقررات مسجلة لهذا القسم', pickCourse, null);
  }
  function pickTeacher(t) {
    document.getElementById('lecTeacher').value = t.id || '';
    document.getElementById('lecTeacherSearch').value = t.id ? t.name : UNASSIGNED_LABEL;
    closeLists();
  }
  function pickCourse(c) {
    document.getElementById('lecCourse').value = c.id;
    document.getElementById('lecCourseSearch').value = c.display;
    closeLists();
  }
  function resetPickers() {
    document.getElementById('lecTeacher').value = '';
    document.getElementById('lecCourse').value = '';
    document.getElementById('lecTeacherSearch').value = '';
    document.getElementById('lecCourseSearch').value = '';
    closeLists();
  }

  function openModal(title) {
    document.getElementById('lecTitle').textContent = title;
    document.getElementById('lecOverlay').classList.remove('hidden');
    document.getElementById('lecModal').classList.remove('hidden');
  }
  function closeModal() {
    document.getElementById('lecOverlay').classList.add('hidden');
    document.getElementById('lecModal').classList.add('hidden');
    editingRowId = null;
  }

  function openAdd(day, period) {
    if (locked) { toast('هذا جدول للعرض فقط — لا يمكن إضافة محاضرات.', 'error'); return; }
    editingRowId = null;
    hideWarn(); hideHint();
    populateModal();
    document.getElementById('lecDept').value = selDept;
    document.getElementById('lecSemester').value = selSem;
    document.getElementById('lecDay').value = day || days[0];
    document.getElementById('lecPeriod').value = period || (periods.length ? periods[0].code : '');
    var slotRow = document.getElementById('lecSlotRow');
    slotRow.classList.toggle('hidden', !!(day && period));
    applyPeriodDefaults();
    document.getElementById('lecHours').value = 3;
    resetPickers();
    refreshRoomOptions();
    refreshTeachersAvailability();
    document.querySelector('input[name="lecType"][value="theory"]').checked = true;
    openModal('إضافة محاضرة');
  }

  function openEdit(id) {
    if (locked) return;
    var e = findEntry(id);
    if (!e) return;
    editingRowId = id;
    closePopup();
    hideWarn(); hideHint();
    populateModal();
    document.getElementById('lecDept').value = e.department_id || selDept;
    document.getElementById('lecSemester').value = String(e.semester);
    document.getElementById('lecDay').value = e.day;
    document.getElementById('lecPeriod').value = e.period;
    document.getElementById('lecStartTime').value = e.start_time || '';
    document.getElementById('lecEndTime').value = e.end_time || '';
    document.getElementById('lecRoom').value = e.room_id;
    document.getElementById('lecHours').value = e.hours || 0;
    refreshRoomOptions(e.room_id);
    refreshTeachersAvailability();
    if (e.lecture_type === 'practical') document.querySelector('input[name="lecType"][value="practical"]').checked = true;
    else document.querySelector('input[name="lecType"][value="theory"]').checked = true;
    document.getElementById('lecSlotRow').classList.add('hidden');
    var t = getTeacher(e.teacher_id);
    document.getElementById('lecTeacher').value = e.teacher_id || '';
    document.getElementById('lecTeacherSearch').value = t ? t.name : UNASSIGNED_LABEL;
    var c = getCourseById(e.course_id);
    document.getElementById('lecCourse').value = e.course_id;
    document.getElementById('lecCourseSearch').value = c ? (c.name + (c.code ? ' (' + c.code + ')' : '')) : '';
    closeLists();
    openModal('تعديل المحاضرة');
  }

  function _ttTimeMin(v) {
    if (!v) return null;
    var m = String(v).split(':');
    if (m.length < 2) return null;
    var h = parseInt(m[0], 10), mi = parseInt(m[1], 10);
    if (isNaN(h) || isNaN(mi)) return null;
    return h * 60 + mi;
  }
  function conflictsAt(day, period, teacherId, room, excludeId, startTime, endTime) {
    for (var i = 0; i < entries.length; i++) {
      var r = entries[i];
      if (r.id === excludeId) continue;
      if (r.day !== day) continue;
      if (startTime && endTime && r.start_time && r.end_time) {
        var as = _ttTimeMin(startTime), ae = _ttTimeMin(endTime);
        var bs = _ttTimeMin(r.start_time), be = _ttTimeMin(r.end_time);
        if (as !== null && ae !== null && bs !== null && be !== null) {
          if (!(as < be && bs < ae)) continue;
        } else if (r.period !== period) {
          continue;
        }
      } else if (r.period !== period) {
        continue;
      }
      if (teacherId && r.teacher_id === teacherId) return 'عضو هيئة التدريس لديه محاضرة متداخلة في هذا التوقيت.';
      if (r.room_id === room) return 'هذه القاعة محجوزة في هذا التوقيت.';
    }
    return null;
  }

  function saveLecture() {
    var teacherRaw = document.getElementById('lecTeacher').value;
    var teacherId = parseInt(teacherRaw, 10) || 0;
    var courseId = parseInt(document.getElementById('lecCourse').value, 10) || 0;
    var deptId = parseInt(document.getElementById('lecDept').value, 10) || selDept;
    var semester = parseInt(document.getElementById('lecSemester').value, 10) || selSem;
    var day = document.getElementById('lecDay').value;
    var period = document.getElementById('lecPeriod').value;
    var room = parseInt(document.getElementById('lecRoom').value, 10) || 0;
    var type = document.querySelector('input[name="lecType"]:checked').value;
    var hours = parseInt(document.getElementById('lecHours').value, 10) || 0;

    hideWarn();
    if (!courseId || !deptId || !day || !period || !room || hours < 1) {
      showWarn('يرجى إكمال جميع الحقول المطلوبة وساعات صحيحة (1–6). يمكن حفظ الحصة بدون تعيين عضو هيئة التدريس.');
      return;
    }
    var stVal = document.getElementById('lecStartTime').value;
    var etVal = document.getElementById('lecEndTime').value;
    var conflict = conflictsAt(day, period, teacherId, room, editingRowId, stVal, etVal);
    if (conflict) { showWarn(conflict); return; }

    if (stVal && etVal && stVal >= etVal) {
      showWarn('وقت النهاية يجب أن يكون بعد وقت البداية بنظام 24 ساعة.');
      return;
    }

    var fd = new FormData();
    fd.append('day', day);
    fd.append('semester', semester);
    fd.append('section', period);
    fd.append('course_id', courseId);
    fd.append('teacher_id', teacherRaw || '');
    fd.append('room_id', room);
    fd.append('department_id', deptId);
    fd.append('lecture_type', type);
    fd.append('hours', hours);
    fd.append('start_time', document.getElementById('lecStartTime').value);
    fd.append('end_time', document.getElementById('lecEndTime').value);
    fd.append('modal', '1');

    var url = editingRowId ? API + '/' + editingRowId + '/edit' : API + '/create';
    fetchPost(url, fd, editingRowId ? 'تم تحديث المحاضرة' : 'تمت إضافة المحاضرة');
    closeModal();
  }

  function duplicateEntry(id) {
    if (locked) return;
    var e = findEntry(id);
    if (!e) return;
    closePopup();
    var fd = new FormData();
    fd.append('day', e.day);
    fd.append('semester', e.semester);
    fd.append('section', e.period);
    fd.append('course_id', e.course_id);
    fd.append('teacher_id', e.teacher_id || '');
    fd.append('room_id', e.room_id);
    fd.append('department_id', e.department_id || selDept);
    fd.append('lecture_type', e.lecture_type || 'theory');
    fd.append('hours', e.hours || 0);
    fd.append('start_time', e.start_time || '');
    fd.append('end_time', e.end_time || '');
    fd.append('modal', '1');
    fetchPost(API + '/create', fd, 'تم تكرار المحاضرة');
  }

  function deleteEntry(id) {
    if (locked) return;
    closePopup();
    fetchPost(API + '/api/delete-entry', { lecture_id: id }, 'تم حذف المحاضرة');
  }

  // ── Drag & drop ──────────────────────────────────────────
  function dragStart(ev, id) {
    if (locked) { ev.preventDefault(); return; }
    dragRowId = id;
    ev.dataTransfer.setData('text/plain', String(id));
    ev.dataTransfer.effectAllowed = 'move';
    ev.currentTarget.classList.add('dragging');
  }
  function dragEnd(ev) {
    dragRowId = null;
    var els = document.querySelectorAll('.dragging, .drop-hover');
    for (var i = 0; i < els.length; i++) els[i].classList.remove('dragging', 'drop-hover');
  }
  function dragOver(ev) {
    ev.preventDefault();
    ev.dataTransfer.dropEffect = 'move';
    if (!ev.currentTarget.classList.contains('drop-hover')) ev.currentTarget.classList.add('drop-hover');
  }
  function dragLeave(ev) { ev.currentTarget.classList.remove('drop-hover'); }
  function persistMove(id, day, period) {
    var e = findEntry(id);
    if (!e) return;
    var conflict = conflictsAt(day, period, e.teacher_id, e.room_id, id, e.start_time, e.end_time);
    if (conflict) { toast(conflict, 'error'); return; }
    var fd = new FormData();
    fd.append('day', day);
    fd.append('semester', e.semester);
    fd.append('section', period);
    fd.append('course_id', e.course_id);
    fd.append('teacher_id', e.teacher_id || '');
    fd.append('room_id', e.room_id);
    fd.append('lecture_type', e.lecture_type || 'theory');
    fd.append('hours', e.hours || 0);
    fd.append('start_time', e.start_time || '');
    fd.append('end_time', e.end_time || '');
    fd.append('modal', '1');
    fetchPost(API + '/' + id + '/edit', fd, 'تم نقل المحاضرة');
  }
  function dropMove(id, day, period) { persistMove(id, day, period); }
  function dropSwap(aId, bId) {
    if (locked) return;
    var a = findEntry(aId);
    var b = findEntry(bId);
    if (!a || !b || a.id === b.id) return;
    if (a.day === b.day && a.period === b.period) return;
    var msg = conflictsAt(b.day, b.period, a.teacher_id, a.room_id, aId, a.start_time, a.end_time);
    if (!msg) msg = conflictsAt(a.day, a.period, b.teacher_id, b.room_id, bId, b.start_time, b.end_time);
    if (msg) { toast(msg, 'error'); return; }
    persistMove(aId, b.day, b.period);
  }
  function dropTarget(ev, day, period) {
    ev.preventDefault();
    var id = dragRowId !== null ? dragRowId : parseInt(ev.dataTransfer.getData('text/plain'), 10);
    dragEnd(ev);
    if (id) dropMove(id, day, period);
  }
  function dropSwapTarget(ev, targetId) {
    ev.preventDefault();
    var id = dragRowId !== null ? dragRowId : parseInt(ev.dataTransfer.getData('text/plain'), 10);
    dragEnd(ev);
    if (id) dropSwap(id, targetId);
  }

  // ── Global hooks for inline handlers ─────────────────────
  window.__ttSetDept = function (id) { nav({ department_id: id, semester: selSem }); };
  window.__ttSetSem = function (s) { nav({ department_id: selDept, semester: s }); };
  window.__ttOpenAdd = function (d, p) { openAdd(d, p); };
  window.openTeacherList = openTeacherList;
  window.filterTeacherList = filterTeacherList;
  window.openCourseList = openCourseList;
  window.filterCourseList = filterCourseList;
  window.__ttOpenPopup = function (id) { openPopup(id); };
  window.__ttPopupId = function () { return popupId; };
  window.__ttDragStart = dragStart;
  window.__ttDragEnd = dragEnd;
  window.__ttDragOver = dragOver;
  window.__ttDragLeave = dragLeave;
  window.__ttDropTarget = dropTarget;
  window.__ttDropSwapTarget = dropSwapTarget;
  window.openAdd = openAdd;
  window.openEdit = openEdit;
  window.closePopup = closePopup;
  window.closeModal = closeModal;
  window.saveLecture = saveLecture;
  window.deleteEntry = deleteEntry;
  window.duplicateEntry = duplicateEntry;
  window.openNextYear = openNextYear;
  window.closeNextYear = closeNextYear;
  window.createNextYear = createNextYear;

  // ── Init ─────────────────────────────────────────────────
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (!document.getElementById('lecModal').classList.contains('hidden')) closeModal();
      else if (!document.getElementById('popupMenu').classList.contains('hidden')) closePopup();
      else if (!document.getElementById('nyModal').classList.contains('hidden')) closeNextYear();
    }
  });
  document.addEventListener('click', function (e) {
    if (!document.getElementById('lecTeacherCtl').contains(e.target)) {
      document.getElementById('lecTeacherList').classList.add('hidden');
    }
    if (!document.getElementById('lecCourseCtl').contains(e.target)) {
      document.getElementById('lecCourseList').classList.add('hidden');
    }
  });

  var printBtn = document.getElementById('printBtn');
  if (printBtn) printBtn.addEventListener('click', function () {
    if (!P.dept) { toast('اختر قسماً أولاً.', 'error'); return; }
    var u = new URL(BOOT.printUrl || '/print/timetables/department', window.location.origin);
    u.searchParams.set('department_id', P.dept.id);
    u.searchParams.set('semester', P.selected_semester);
    if (P.current_version_id) u.searchParams.set('version_id', P.current_version_id);
    console.debug('[TIMETABLE PRINT]', {
      departmentId: P.dept.id,
      semester: P.selected_semester,
      versionId: P.current_version_id || null,
      printUrl: u.toString()
    });
    window.open(u.toString(), '_blank');
  });

  ['lecDay', 'lecPeriod', 'lecHours', 'lecStartTime', 'lecEndTime'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('change', function () {
      if (id === 'lecPeriod') applyPeriodDefaults();
      refreshRoomOptions();
      refreshTeachersAvailability();
    });
  });

  var modalSemesterRequest = 0;
  ['lecDept', 'lecSemester'].forEach(function (id) {
    var el = document.getElementById(id);
    if (!el || el.tagName !== 'SELECT') return;
    el.addEventListener('change', function () {
      document.getElementById('lecCourse').value = '';
      document.getElementById('lecCourseSearch').value = '';
      document.getElementById('lecCourseList').classList.add('hidden');
      if (id === 'lecDept') {
        var selectedDept = parseInt(el.value, 10);
        var semEl = document.getElementById('lecSemester');
        var requestId = ++modalSemesterRequest;
        semEl.disabled = true;
        fetch(BASE + qs({
          department_id: selectedDept,
          semester: selSem,
          format: 'json'
        }))
          .then(function (response) {
            if (!response.ok) throw new Error('تعذر تحميل فصول القسم المختار.');
            return response.json();
          })
          .then(function (result) {
            if (requestId !== modalSemesterRequest) return;
            if (!result || !result.ok || !result.data) {
              throw new Error((result && result.message) || 'تعذر تحميل فصول القسم المختار.');
            }
            setModalSemesters(
              result.data.available_semesters || [],
              result.data.selected_semester
            );
          })
          .catch(function (error) {
            if (requestId !== modalSemesterRequest) return;
            el.value = String(selDept || '');
            setModalSemesters(availableSemesters, selSem);
            semEl.disabled = false;
            toast(error.message || 'تعذر تحميل فصول القسم المختار.', 'error');
          });
      }
    });
  });

  if (!P.dept) {
    document.getElementById('gridBody').innerHTML = '<tr><td colspan="' + Math.max(2, periods.length + 1) + '" class="py-16 text-center text-on-surface-variant">اختر قسماً لعرض الجدول الأسبوعي</td></tr>';
    var mw = document.getElementById('mobileGrid');
    if (mw) mw.innerHTML = '<div class="tt-mempty"><span class="material-symbols-outlined">domain</span>اختر قسماً لعرض جدوله الأسبوعي</div>';
    var addBtn = document.getElementById('addLecBtn');
    if (addBtn) addBtn.disabled = true;
    var nyBtn = document.getElementById('nextYearBtn');
    if (nyBtn) nyBtn.disabled = true;
  } else {
    renderFilters();
    renderGrid();
    startPolling();
  }
})();