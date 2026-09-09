(function () {
  var BOOT = window.TIMETABLE_RND_BOOT || {};
  var BASE = BOOT.base || '/timetable/rnd';

  var P = BOOT.payload || {};
  var departments = P.departments || [];
  var periods = P.periods || [];
  var days = P.days || [];
  var availableSemesters = P.available_semesters || [];
  var versions = P.versions || [];
  var entries = P.entries || [];
  var vocabMap = P.vocab || {};
  var syllabiMap = P.syllabus || {};
  var formMap = P.form || {};

  var csrfToken = BOOT.csrfToken || '';

  var selDept = P.dept ? P.dept.id : null;
  var selSem = P.selected_semester;
  var activeVersionId = P.current_version_id;
  var viewingVersionId = P.viewing_version_id;
  var currentYear = P.active_academic_label || P.semester_code;
  var viewingYear = P.viewing_semester_name || P.viewing_semester_code;
  var viewingArchived = !!(viewingVersionId && viewingVersionId !== activeVersionId);

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
            var syllabusFile = syllabiMap[e.teacher_id + ':' + e.course_id] || syllabiMap['*:' + e.course_id] || {};
            html += '<div class="bg-primary-container rounded-lg p-3 shadow-md text-[11px]">' +
              '<h3 class="font-bold text-on-surface mb-1.5 text-xs">📘 مقرر: ' + esc(e.course_name || '—') + '</h3>' +
              '<div class="flex items-center gap-1.5 text-primary font-bold mb-1">' +
                '<span>⏰</span> <span>' + esc(timeStr) + '</span>' +
              '</div>' +
              '<div class="flex items-center gap-1.5 text-on-surface-variant mb-1"><span class="material-symbols-outlined text-[14px]">person</span> ' + esc(cleanTeacher(e.teacher_name)) + '</div>' +
              '<div class="flex items-center gap-1.5 text-on-surface-variant mb-1"><span class="material-symbols-outlined text-[14px]">meeting_room</span> ' + esc(e.room_name || '—') + '</div>' +
              '<div class="flex items-center gap-1.5 text-on-surface-variant mb-2"><span class="material-symbols-outlined text-[14px]">schedule</span> ' + esc(typeLabel(e.lecture_type)) + (durationLabel(e) ? ' · ' + esc(durationLabel(e)) : '') + '</div>' +
              '<div class="flex flex-wrap gap-1.5">' +
                  '<a href="' + formEditUrl + '" target="_blank" rel="noopener" class="bg-emerald-700 text-white px-2 py-0.5 rounded text-[10px] font-bold">' + (formFile.url ? '📝 تعديل المقرر' : '📝 إعداد المقرر') + '</a>' +
                (formFile.url ? '<a href="' + formFile.url + (formFile.url.indexOf('?') >= 0 ? '&' : '?') + 'download=1" target="_blank" rel="noopener" class="bg-primary text-white px-2 py-0.5 rounded text-[10px] font-bold">📄 تحميل المقرر</a>' : '<button disabled class="bg-gray-300 text-gray-600 px-2 py-0.5 rounded text-[10px] font-bold">📄 تحميل المقرر</button>') +
                (syllabusFile.url ? '<a href="' + syllabusFile.url + (syllabusFile.url.indexOf('?') >= 0 ? '&' : '?') + 'download=1" target="_blank" rel="noopener" class="bg-primary text-white px-2 py-0.5 rounded text-[10px] font-bold">⬇️ تحميل المنهج</a>' : '<button disabled class="bg-gray-300 text-gray-600 px-2 py-0.5 rounded text-[10px] font-bold">⬇️ تحميل المنهج</button>') +
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

    var banner = document.getElementById('viewingBanner');
    var bannerText = document.getElementById('viewingBannerText');
    if (viewingArchived) {
      banner.classList.remove('hidden');
      bannerText.textContent = 'أنت تتصفح جدولًا أرشيفيًا (' + (viewingYear || '') + ')';
    } else {
      banner.classList.add('hidden');
    }
    renderBadge();
    renderArchive();
  }

  function renderBadge() {
    var b = document.getElementById('currentBadge');
    var chipCls, dotCls, label;
    if (viewingArchived) {
      chipCls = 'border-amber-200 bg-amber-50 text-amber-700';
      dotCls = 'bg-amber-500';
      label = 'جدول أرشيفي · ' + (viewingYear || '') + ' · الفصل ' + semesterNumLabel(selSem) + ' — للعرض فقط';
    } else {
      chipCls = 'border-gray-200 bg-gray-100 text-gray-600';
      dotCls = 'bg-gray-400';
      label = 'الجدول الحالي · ' + (currentYear || '') + ' · الفصل ' + semesterNumLabel(selSem) + ' — للعرض فقط';
    }
    b.className = 'mr-auto inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold border ' + chipCls;
    b.innerHTML =
      '<span class="flex flex-col items-end leading-tight">' +
        '<span class="flex items-center gap-1.5">' +
          '<span class="w-2 h-2 rounded-full ' + dotCls + '"></span>' +
          '<span>' + esc(label) + '</span>' +
        '</span>' +
      '</span>';
  }

  // ── Archive ──────────────────────────────────────────────
  function toggleArchive() {
    var d = document.getElementById('archiveDropdown');
    if (d.classList.contains('hidden')) { renderArchive(); d.classList.remove('hidden'); }
    else d.classList.add('hidden');
  }
  function closeArchive() { document.getElementById('archiveDropdown').classList.add('hidden'); }
  function isArchiveTarget(node) {
    var n = node;
    while (n) {
      if (n.id === 'archiveDropdown' || n.id === 'archiveBtn') return true;
      n = n.parentNode;
    }
    return false;
  }
  function renderArchive() {
    var body = document.getElementById('archiveBody');
    body.innerHTML = '';
    document.getElementById('archiveCount').textContent = versions.length;
    document.getElementById('archiveTitle').textContent = 'أرشيف ' + (P.dept ? P.dept.name : '') + ' — الفصل ' + selSem;

    if (!versions.length) {
      body.innerHTML = '<div class="px-4 py-10 text-center">' +
        '<span class="material-symbols-outlined text-[32px] text-outline block mb-2">archive</span>' +
        '<div class="text-sm text-on-surface-variant">لا يوجد أرشيف لهذا القسم والفصل بعد</div>' +
        '</div>';
      return;
    }
    var lastYear = null;
    versions.forEach(function (v) {
      var html = '';
      var displayName = v.semester_name_ar || v.semester_code || '—';
      if (displayName !== lastYear) {
        lastYear = displayName;
        html += '<div class="px-4 pt-2.5 pb-1.5 flex items-center gap-2 text-xs font-bold text-on-surface-variant">' +
          '<span class="material-symbols-outlined text-[14px] text-primary">calendar_month</span>' +
          'الفصل: ' + esc(displayName) +
          '</div>';
      }
      var active = v.id === viewingVersionId;
      html += '<div class="flex items-center gap-1 px-3 py-2 hover:bg-surface-container transition' + (active ? ' bg-primary-container' : '') + '">' +
        '<button type="button" onclick="window.__ttOpenVersion(' + v.id + ')" class="flex-1 flex items-center justify-between gap-2 text-right">' +
          '<span>' +
            '<span class="block text-sm font-bold text-on-surface">' + v.cnt + ' محاضرة</span>' +
            '<span class="block text-[11px] text-on-surface-variant mt-0.5">آخر تعديل: ' + fmtDate(v.updated_at) + '</span>' +
          '</span>' +
          '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-surface-container-highest text-on-surface-variant">أرشيف</span>' +
        '</button>' +
        '<button type="button" title="فتح" onclick="window.__ttOpenVersion(' + v.id + ')" class="p-1.5 rounded-lg text-on-surface-variant hover:text-primary hover:bg-primary-container transition">' +
          '<span class="material-symbols-outlined text-[18px]">visibility</span>' +
        '</button>' +
        '</div>';
      body.insertAdjacentHTML('beforeend', html);
    });
  }
  function openVersion(id) {
    nav({ department_id: selDept, semester: selSem, version_id: id });
  }
  function returnToCurrent() {
    nav({ department_id: selDept, semester: selSem });
  }

  // ── Global hooks for inline handlers ─────────────────────
  window.__ttSetDept = function (id) { nav({ department_id: id }); };
  window.__ttSetSem = function (s) { nav({ department_id: selDept, semester: s }); };
  window.__ttOpenVersion = function (id) { openVersion(id); };
  window.toggleArchive = toggleArchive;
  window.closeArchive = closeArchive;
  window.returnToCurrent = returnToCurrent;

  // ── Init ─────────────────────────────────────────────────
  document.addEventListener('click', function (e) {
    var dd = document.getElementById('archiveDropdown');
    if (dd.classList.contains('hidden')) return;
    if (!isArchiveTarget(e.target)) closeArchive();
  });

  var printBtn = document.getElementById('printBtn');
  if (printBtn) printBtn.addEventListener('click', function () {
    window.print();
  });

  if (!P.dept) {
    document.getElementById('gridBody').innerHTML = '<tr><td colspan="' + Math.max(2, periods.length + 1) + '" class="py-16 text-center text-on-surface-variant">لا توجد أقسام متاحة</td></tr>';
    document.getElementById('departmentFilters').innerHTML =
      '<div class="col-span-full py-10 text-center text-on-surface-variant text-sm">لا توجد أقسام لعرض جداولها</div>';
    document.getElementById('semesterStep').classList.add('hidden');
  } else {
    renderFilters();
    renderGrid();
  }
})();
