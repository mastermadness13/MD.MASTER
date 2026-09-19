(function () {
  var BOOT = window.TIMETABLE_RND_BOOT || {};
  var BASE = BOOT.base || '/timetable/rnd';

  var P = BOOT.payload || {};
  var departments = P.departments || [];
  var periods = P.periods || [];
  var days = P.days || [];
  var availableSemesters = P.available_semesters || [];
  var entries = P.entries || [];
  var vocabMap = P.vocab || {};
  var formMap = P.form || {};

  var csrfToken = BOOT.csrfToken || '';

  var selDept = P.dept ? P.dept.id : null;
  var selSem = P.selected_semester;
  var activeVersionId = P.current_version_id;
  var currentYear = P.active_academic_label || P.semester_code;

  var H = window.TimetableHelpers.create({ periods: periods, base: BASE });
  var esc = H.esc, semesterNumLabel = H.semesterNumLabel, fmtTime12 = H.fmtTime12,
      periodTime = H.periodTime, entryTime = H.entryTime, periodByCode = H.periodByCode,
      typeLabel = H.typeLabel, cleanTeacher = H.cleanTeacher, durationLabel = H.durationLabel,
      fmtDate = H.fmtDate, qs = H.qs, nav = H.nav;
  function periodHeaderTime(p) {
    if (p && p.start_time) return fmtTime12(p.start_time) + (p.end_time ? ' إلى ' + fmtTime12(p.end_time) : '');
    return '';
  }
  // ── Filters ──────────────────────────────────────────────
  function renderFilters() {
    var dWrap = document.getElementById('departmentFilters');
    dWrap.innerHTML = '';
    departments.forEach(function (d) {
      var active = d.id === selDept ? ' active' : '';
      dWrap.insertAdjacentHTML('beforeend',
        '<button type="button" class="dept-card' + active + ' flex items-center gap-3 rounded-xl border border-outline-variant bg-surface-card p-3 text-right" onclick="window.__ttSetDept(' + d.id + ')">' +
          '<span class="material-symbols-outlined text-primary text-[22px] shrink-0">domain</span>' +
          '<span class="flex-1 font-bold text-sm text-on-surface">' + esc(d.name) + '</span>' +
          '<span class="material-symbols-outlined text-base text-on-surface-variant shrink-0">chevron_left</span>' +
        '</button>');
    });

    var semStep = document.getElementById('semesterStep');
    var sWrap = document.getElementById('semesterFilters');
    var semDept = document.getElementById('semesterDeptLabel');
    if (selDept && availableSemesters.length > 1) {
      semStep.classList.remove('hidden');
      sWrap.innerHTML = '';
      availableSemesters.forEach(function (s) {
        var active = s === selSem ? ' active' : '';
        sWrap.insertAdjacentHTML('beforeend',
          '<button type="button" class="filter-btn' + active + '" onclick="window.__ttSetSem(' + s + ')">الفصل ' + s + '</button>');
      });
      var deptName = '';
      departments.forEach(function (d) { if (d.id === selDept) deptName = d.name; });
      semDept.innerHTML = '<span class="material-symbols-outlined text-[14px]">domain</span>' + esc(deptName);
    } else {
      semStep.classList.add('hidden');
      semDept.innerHTML = '';
    }
  }

  // ── Grid ─────────────────────────────────────────────────
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
            var formEditUrl = '/teacher/super-admin/course-content/create?course_id=' + e.course_id + (formFile.submission_id ? '&amp;submission_id=' + formFile.submission_id : '');
            html += '<div class="bg-primary-container rounded-lg p-3 shadow-md text-[11px]">' +
              '<h3 class="font-bold text-on-surface mb-1.5 text-xs">📘 مقرر: ' + esc(e.course_name || '—') + '</h3>' +
              '<div class="flex items-center gap-1.5 text-primary font-bold mb-1">' +
                '<span>⏰</span> <span>' + esc(timeStr) + '</span>' +
              '</div>' +
              '<div class="flex items-center gap-1.5 text-on-surface-variant mb-1"><span class="material-symbols-outlined text-[14px]">person</span> ' + esc(cleanTeacher(e.teacher_name)) + '</div>' +
              '<div class="flex items-center gap-1.5 text-on-surface-variant mb-1"><span class="material-symbols-outlined text-[14px]">meeting_room</span> ' + esc(e.room_name || '—') + '</div>' +
              '<div class="flex items-center gap-1.5 text-on-surface-variant mb-2"><span class="material-symbols-outlined text-[14px]">schedule</span> ' + esc(typeLabel(e.lecture_type)) + (durationLabel(e) ? ' · ' + esc(durationLabel(e)) : '') + '</div>' +
              '<div class="text-[10px] mb-1.5 font-bold">' +
                '<span class="' + (formFile.url ? 'text-green-600' : 'text-red-400') + '">● مقرر</span> ' +
              '</div>' +
              '<div class="flex flex-wrap gap-1.5">' +
                  '<a href="' + formEditUrl + '" target="_blank" rel="noopener" class="bg-emerald-700 text-white px-2 py-0.5 rounded text-[10px] font-bold">📝 إنشاء/تعديل المقرر</a>' +
                (formFile.url ? '<a href="' + formFile.url + (formFile.url.indexOf('?') >= 0 ? '&' : '?') + 'download=1" class="bg-primary text-white px-2 py-0.5 rounded text-[10px] font-bold">📄 تحميل المقرر</a>' : '<button disabled class="bg-gray-300 text-gray-600 px-2 py-0.5 rounded text-[10px] font-bold">📄 تحميل المقرر</button>') +
              '</div>' +
              '</div>';
          });
          html += '</div></td>';
        } else {
          html += '<td class="px-1 py-2 align-stretch h-[110px]">' +
            '<div class="flex-1 mx-1 p-2 bg-surface-container-highest rounded-lg text-[11px] flex items-center justify-center h-full">' +
            '<span class="text-xs text-on-surface-variant font-medium">فارغ</span>' +
            '</div></td>';
        }
      });
      html += '</tr>';
    });
    tbody.innerHTML = html;
    renderBadge();
    renderMobileGrid();
  }

  // ── Mobile card list (phones <1024px, read-only) ──────────
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
        var formEditUrl = '/teacher/super-admin/course-content/create?course_id=' + e.course_id + (formFile.submission_id ? '&amp;submission_id=' + formFile.submission_id : '');
        html += '<div class="tt-mcard">' +
          '<div class="tt-mcard-title">' +
            '<span>' + esc(e.course_name || '—') + '</span>' +
            (e.course_code ? '<span class="code">(' + esc(e.course_code) + ')</span>' : '') +
            '<span class="tt-mday-count" style="margin-inline-start:auto"><span class="' + (formFile.url ? 'text-green-600' : 'text-red-400') + '">● مقرر</span></span>' +
          '</div>' +
          '<div class="tt-mrow tt-mtime"><span class="material-symbols-outlined">schedule</span><span dir="ltr">' + esc(timeStr) + '</span>' + (durationLabel(e) ? '<span>· ' + esc(durationLabel(e)) + '</span>' : '') + '</div>' +
          '<div class="tt-mrow"><span class="material-symbols-outlined">person</span>' + esc(cleanTeacher(e.teacher_name)) + '</div>' +
          '<div class="tt-mrow"><span class="material-symbols-outlined">meeting_room</span>' + esc(e.room_name || '—') + '</div>' +
          '<div class="tt-mrow"><span class="material-symbols-outlined">category</span>' + esc(typeLabel(e.lecture_type)) + '</div>' +
          '<div class="tt-actions">' +
            '<a class="tt-chip tt-chip-soft" href="' + formEditUrl + '" target="_blank" rel="noopener"><span class="material-symbols-outlined">description</span> إنشاء/تعديل المقرر</a>' +
            (formFile.url ? '<a class="tt-chip tt-chip-primary" href="' + formFile.url + (formFile.url.indexOf('?') >= 0 ? '&' : '?') + 'download=1"><span class="material-symbols-outlined">description</span> تحميل المقرر</a>' : '<button class="tt-chip tt-chip-primary" disabled><span class="material-symbols-outlined">description</span> لا يوجد مقرر</button>') +
          '</div>' +
        '</div>';
      });
      html += '</div></div>';
    });
    wrap.innerHTML = html;
  }

  function renderBadge() {
    var b = document.getElementById('currentBadge');
    var chipCls = 'border-gray-200 bg-gray-100 text-gray-600';
    var dotCls = 'bg-gray-400';
    var label = 'الجدول الحالي · ' + (currentYear || '') + ' · الفصل ' + semesterNumLabel(selSem) + ' — للعرض فقط';
    b.className = 'mr-auto inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold border ' + chipCls;
    b.innerHTML =
      '<span class="flex flex-col items-end leading-tight">' +
        '<span class="flex items-center gap-1.5">' +
          '<span class="w-2 h-2 rounded-full ' + dotCls + '"></span>' +
          '<span>' + esc(label) + '</span>' +
        '</span>' +
      '</span>';
  }


  // ── Global hooks for inline handlers ─────────────────────
  window.__ttSetDept = function (id) { nav({ department_id: id }); };
  window.__ttSetSem = function (s) { nav({ department_id: selDept, semester: s }); };

  // ── Init ─────────────────────────────────────────────────

  var printBtn = document.getElementById('printBtn');
  if (printBtn) printBtn.addEventListener('click', function () {
    window.print();
  });

  if (!P.dept) {
    document.getElementById('gridBody').innerHTML = '<tr><td colspan="' + Math.max(2, periods.length + 1) + '" class="py-16 text-center text-on-surface-variant">لا توجد أقسام متاحة</td></tr>';
    var mw = document.getElementById('mobileGrid');
    if (mw) mw.innerHTML = '<div class="tt-mempty"><span class="material-symbols-outlined">domain</span>لا توجد أقسام لعرض جداولها</div>';
    document.getElementById('departmentFilters').innerHTML =
      '<div class="col-span-full py-10 text-center text-on-surface-variant text-sm">لا توجد أقسام لعرض جداولها</div>';
    document.getElementById('semesterStep').classList.add('hidden');
  } else {
    renderFilters();
    renderGrid();
  }
})();
