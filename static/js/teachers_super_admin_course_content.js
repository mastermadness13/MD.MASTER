
(function () {
  var BOOT = window.TEACHERS_SUPER_ADMIN_COURSE_CONTENT_BOOT || {};
  'use strict';
  var H = window.CourseHelpers || {};
  var esc = H.esc || function (s) { return String(s == null ? '' : s); };
  var COURSES = BOOT.courses || [];
  var SYLLABUS_BY_COURSE = BOOT.syllabusByCourse || {};

  // Build department list from all visible departments (server-provided) merged with course dept_names
  var deptNames = [];
  (BOOT.departmentNames || []).forEach(function (n) { deptNames.push(n); });
  // Add any dept names found only on courses
  COURSES.forEach(function (c) {
    (c.dept_names || []).forEach(function (d) {
      if (deptNames.indexOf(d) === -1) deptNames.push(d);
    });
  });
  var departments = deptNames.filter(Boolean).map(function (name) { return { name: name }; });

  // Semester labels
  function semLabel(s) {
    var n = parseInt(s, 10);
    if (!n) return '—';
    var ord = ['الأول','الثاني','الثالث','الرابع','الخامس','السادس','السابع','الثامن'];
    return ord[n - 1] || ('الفصل ' + n);
  }

  // ============ LIST VIEW ============
  function listRows() {
    var q = (document.getElementById('ccListSearch').value || '').trim().toLowerCase();
    var did = document.getElementById('ccListDeptFilter').value;
    var st = document.getElementById('ccListStatusFilter').value;
    return COURSES.filter(function (c) {
      if (did) {
        var has = (c.dept_names || []).some(function (d) { return d === did; });
        if (!has) return false;
      }
      if (st) {
        var status = c.form_status || '';
        if (status !== st) return false;
      }
      if (!q) return true;
      var hay = ((c.name || '') + ' ' + (c.code || '') + ' ' + (c.dept_names || []).join(' ') + ' ' + (c.teachers || []).join(' ') + ' ' + semLabel(c.semester)).toLowerCase();
      return hay.indexOf(q) !== -1;
    });
  }

  function formStatusBadge(c) {
    return H.formStatusBadge ? H.formStatusBadge(c.form_status) : '';
  }

  function teachersCell(c) {
    return H.teachersCell ? H.teachersCell(c.teachers) : '';
  }

  function deptBadges(c) {
    return H.deptBadges ? H.deptBadges(c.dept_names) : '';
  }

  function prereqBadges(c) {
    return H.prereqBadges ? H.prereqBadges(c.prereqs) : '';
  }

  function actionsCell(c) {
    var syl = SYLLABUS_BY_COURSE[c.id];
    var formEditUrl = c.latest_form_submission_id
      ? '/teacher/super-admin/course-content/create?course_id=' + c.id + '&amp;submission_id=' + c.latest_form_submission_id
      : '/teacher/super-admin/course-content/create?course_id=' + c.id;
    var sylHref = (syl && syl.id)
      ? '/teacher/super-admin/course-content/course-file/' + syl.id + '?download=1'
      : formEditUrl;
    function actBtn(href, icon, title) {
      return '<a href="' + href + '" class="w-7 h-7 inline-flex items-center justify-center rounded-lg hover:bg-primary-faint text-primary transition-all" title="' + title + '">' +
        '<span class="material-symbols-outlined text-base">' + icon + '</span></a>';
    }
    function printBtn(title) {
      return '<button type="button" onclick="ccPreparePrint(this)" class="w-7 h-7 inline-flex items-center justify-center rounded-lg hover:bg-primary-faint text-primary transition-all" title="' + title + '" data-cid="' + c.id + '" data-sid="' + (c.latest_form_submission_id || '') + '">' +
        '<span class="material-symbols-outlined text-base">print</span></button>';
    }
    return '<div class="flex items-center justify-center gap-1">' +
      actBtn(sylHref, 'download', 'تحميل المنهج') +
      printBtn('طباعة المقرر') +
      actBtn(formEditUrl, 'edit', 'تعديل المقرر') +
    '</div>';
  }

  function ccPreparePrint(btn) {
    var sid = btn.getAttribute('data-sid');
    if (!sid) return;
    var frame = document.getElementById('ccPrintFrame');
    if (!frame) {
      frame = document.createElement('iframe');
      frame.id = 'ccPrintFrame';
      frame.setAttribute('aria-hidden', 'true');
      frame.style.cssText = 'position:absolute;left:-9999px;top:0;width:1200px;height:1000px;border:0;';
      frame.onload = function () {
        var win = frame.contentWindow;
        if (win) {
          win.focus();
          win.print();
        }
        window.setTimeout(function () {
          if (frame.parentNode) frame.parentNode.removeChild(frame);
        }, 1000);
      };
      document.body.appendChild(frame);
    }
    frame.src = '/teacher/super-admin/course-content/' + sid + '?print=1';
  }
  window.ccPreparePrint = ccPreparePrint;

  function renderList() {
    var tbody = document.getElementById('ccCourseTableBody');
    var rows = listRows().slice();
    rows.sort(function (a, b) {
      var sa = SYLLABUS_BY_COURSE[a.id] ? 1 : 0;
      var sb = SYLLABUS_BY_COURSE[b.id] ? 1 : 0;
      return sb - sa;
    });
    document.getElementById('ccCourseCount').textContent = rows.length;
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="13" class="px-4 py-12 text-center"><div class="flex flex-col items-center gap-2"><span class="material-symbols-outlined text-4xl text-text-faint">search_off</span><p class="text-text-muted text-sm">لا توجد مقررات مطابقة</p></div></td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(function (c, i) {
      var total = c.total_hours || ((c.theoretical_hours || 0) + (c.practical_hours || 0));
      return '<tr class="hover:bg-surface-hover transition-colors">' +
        '<td class="px-3 py-2 text-center text-text-muted text-xs font-semibold">' + (i + 1) + '</td>' +
        '<td class="px-3 py-2"><a href="/teacher/super-admin/course-content/course/' + c.id + '" class="font-mono text-xs font-bold text-primary bg-primary/10 px-2 py-0.5 rounded border border-primary/20 no-underline hover:bg-primary/20 transition-all">' + esc(c.code) + '</a></td>' +
        '<td class="px-3 py-2"><span class="font-medium text-text-primary text-sm">' + esc(c.name) + '</span></td>' +
        '<td class="px-3 py-2">' + deptBadges(c) + '</td>' +
        '<td class="px-3 py-2 text-center text-xs font-semibold text-text-secondary">' + semLabel(c.semester) + '</td>' +
        '<td class="px-3 py-2">' + teachersCell(c) + '</td>' +
        '<td class="px-3 py-2 text-center whitespace-nowrap">' + formStatusBadge(c) + '</td>' +
        '<td class="px-3 py-2 text-center text-text-secondary text-sm">' + (c.theoretical_hours || 0) + '</td>' +
        '<td class="px-3 py-2 text-center text-text-secondary text-sm">' + (c.practical_hours || 0) + '</td>' +
        '<td class="px-3 py-2 text-center font-bold text-text-primary text-sm">' + total + '</td>' +
        '<td class="px-3 py-2 text-center"><span class="inline-flex items-center justify-center w-7 h-7 rounded-md bg-primary-faint text-primary text-[11px] font-bold">' + total + '</span></td>' +
        '<td class="px-3 py-2 text-center whitespace-nowrap">' + prereqBadges(c) + '</td>' +
        '<td class="px-3 py-2">' + actionsCell(c) + '</td>' +
      '</tr>';
    }).join('');
  }

  function fillListDeptFilter() {
    var sel = document.getElementById('ccListDeptFilter');
    sel.innerHTML = '<option value="">جميع الأقسام</option>';
    departments.forEach(function (d) {
      var o = document.createElement('option');
      o.value = d.name;
      o.textContent = d.name;
      sel.appendChild(o);
    });
  }

  // ============ PLAN VIEW ============
  var ccCurrentDept = null;

  function planSearchQuery() {
    return (document.getElementById('ccPlanSearch').value || '').trim();
  }

  function renderDeptGrid(filtered) {
    var grid = document.getElementById('ccPlanDeptGrid');
    grid.innerHTML = '';
    if (!filtered.length) {
      grid.innerHTML = '<p class="text-sm text-text-muted w-full py-2">لا يوجد قسم مطابق للبحث</p>';
      return;
    }
    filtered.forEach(function (d) {
      var btn = document.createElement('button');
      var count = coursesOfDept(d.name).length;
      btn.className = 'cc-dept-card flex items-center gap-2 px-4 py-2.5 rounded-xl border text-sm font-semibold transition-all cursor-pointer ' +
        (d.name === ccCurrentDept ? 'active border-primary bg-primary-faint text-primary' : 'border-border bg-white text-text-secondary hover:bg-surface-hover hover:text-primary');
      btn.innerHTML = '<span class="material-symbols-outlined text-lg">domain</span>' +
        '<span>' + esc(d.name) + '</span>' +
        '<span class="text-[11px] font-bold px-2 py-0.5 rounded-full ' + (d.name === ccCurrentDept ? 'bg-white text-primary' : 'bg-surface-zebra text-text-muted') + '">' + count + '</span>';
      btn.onclick = function () { ccSelectDept(d.name, true); };
      grid.appendChild(btn);
    });
  }

  function coursesOfDept(deptName) {
    return COURSES.filter(function (c) {
      return (c.dept_names || []).indexOf(deptName) !== -1;
    });
  }

  function ccSelectDept(name, scroll) {
    ccCurrentDept = name;
    document.getElementById('ccPlanDeptSelect').value = name;
    renderDeptGrid(departments.filter(function (d) { return !planSearchQuery() || d.name.indexOf(planSearchQuery()) !== -1; }));
    renderPlan();
    if (scroll) {
      var el = document.getElementById('ccPlanTablesContainer');
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  function renderPlan() {
    var container = document.getElementById('ccPlanTablesContainer');
    container.innerHTML = '';
    if (!ccCurrentDept) {
      container.innerHTML =
        '<div class="bg-white rounded-2xl border border-dashed border-border py-16 text-center">' +
          '<span class="material-symbols-outlined text-[44px] text-text-faint">search</span>' +
          '<p class="text-text-secondary font-semibold mt-3">اختر قسماً من الأعلى لعرض جداول تحميل المقررات</p>' +
        '</div>';
      return;
    }

    var deptCourses = coursesOfDept(ccCurrentDept);
    var grouped = {};
    deptCourses.forEach(function (c) {
      var s = parseInt(c.semester, 10) || 1;
      if (!grouped[s]) grouped[s] = [];
      grouped[s].push(c);
    });
    Object.keys(grouped).forEach(function (s) {
      grouped[s].sort(function (a, b) {
        var sa = SYLLABUS_BY_COURSE[a.id] ? 1 : 0;
        var sb = SYLLABUS_BY_COURSE[b.id] ? 1 : 0;
        return sb - sa;
      });
    });
    var semKeys = Object.keys(grouped).sort(function (a, b) { return +a - +b; });
    if (!semKeys.length) {
      container.innerHTML = '<div class="bg-white rounded-xl border border-dashed border-border py-16 text-center"><span class="material-symbols-outlined text-[40px] text-text-faint">domain</span><p class="text-text-secondary font-semibold mt-3">لا توجد مقررات محتوى لهذا القسم</p></div>';
      return;
    }

    var stripped = ccCurrentDept.replace(/\s+/g, '');
    var deptIcon = /حاسوب|عام/.test(stripped) ? 'computer' : (/اتصال|اتصالات/.test(stripped) ? 'cell_tower' : (/نفط/.test(stripped) ? 'oil_barrel' : (/مدني/.test(stripped) ? 'engineering' : (/معمار/.test(stripped) ? 'apartment' : (/بحث|تطوير/.test(stripped) ? 'science' : 'account_balance')))));

    var html = '';
    html += '<div class="bg-gradient-to-l from-primary to-purple-800 rounded-2xl px-5 py-4 text-white shadow-sm mb-5 flex items-center justify-between flex-wrap gap-3">' +
      '<div class="flex items-center gap-3">' +
        '<span class="w-10 h-10 rounded-xl bg-white/15 flex items-center justify-center"><span class="material-symbols-outlined text-2xl">' + deptIcon + '</span></span>' +
        '<div><h2 class="text-base font-bold m-0 leading-tight text-white">' + esc(ccCurrentDept) + '</h2>' +
        '<span class="text-xs text-white/70">' + deptCourses.length + ' مادة لتحميل المقررات</span></div>' +
      '</div>' +
      '<div class="flex items-center gap-2">' +
        '<div class="bg-white/15 rounded-xl px-4 py-2 text-center"><div class="text-lg font-bold leading-none">' + semKeys.length + '</div><div class="text-[11px] text-white/70 mt-1">فصل</div></div>' +
        '<div class="bg-white/15 rounded-xl px-4 py-2 text-center"><div class="text-lg font-bold leading-none">' + deptCourses.length + '</div><div class="text-[11px] text-white/70 mt-1">مادة</div></div>' +
      '</div>' +
    '</div>';

    html += '<div class="grid grid-cols-1 gap-4">';
    semKeys.forEach(function (sem) {
      var list = grouped[sem];
      var units = list.reduce(function (acc, c) { return acc + (c.total_hours || ((c.theoretical_hours || 0) + (c.practical_hours || 0))); }, 0);
      var rows = list.map(function (c) {
        var total = c.total_hours || ((c.theoretical_hours || 0) + (c.practical_hours || 0));
        return '<tr class="hover:bg-surface-hover transition-colors">' +
          '<td class="px-3 py-2 text-center text-text-muted text-xs font-semibold">' + esc(c.code) + '</td>' +
          '<td class="px-3 py-2"><span class="font-medium text-text-primary text-sm">' + esc(c.name) + '</span></td>' +
          '<td class="px-3 py-2">' + teachersCell(c) + '</td>' +
          '<td class="px-3 py-2 text-center text-text-secondary text-sm">' + (c.theoretical_hours || 0) + '</td>' +
          '<td class="px-3 py-2 text-center text-text-secondary text-sm">' + (c.practical_hours || 0) + '</td>' +
          '<td class="px-3 py-2 text-center font-bold text-text-secondary text-sm">' + total + '</td>' +
          '<td class="px-3 py-2 text-center"><span class="inline-flex items-center justify-center w-6 h-6 rounded-md bg-primary-faint text-primary text-[11px] font-bold">' + total + '</span></td>' +
          '<td class="px-3 py-2 text-center whitespace-nowrap">' + formStatusBadge(c) + '</td>' +
          '<td class="no-print px-3 py-2 text-center whitespace-nowrap">' + actionsCell(c) + '</td>' +
        '</tr>';
      }).join('');
      html += '<div class="bg-white rounded-xl border border-border shadow-sm overflow-hidden print-sheet">' +
        '<div class="px-4 py-3 border-b border-border-subtle flex items-center justify-between bg-gradient-to-l from-primary/5 to-transparent">' +
          '<div class="flex items-center gap-2.5">' +
            '<span class="w-8 h-8 rounded-lg bg-primary-faint text-primary flex items-center justify-center"><span class="material-symbols-outlined text-lg">table_chart</span></span>' +
            '<div><h3 class="text-sm font-bold text-text-primary m-0 leading-tight">' + esc(ccCurrentDept) + ' — ' + semLabel(sem) + '</h3>' +
            '<span class="text-[11px] text-text-muted">' + list.length + ' مادة — تحميل المقررات</span></div>' +
          '</div>' +
          '<span class="text-xs font-bold text-primary bg-primary-faint px-2.5 py-1 rounded-full whitespace-nowrap">' + units + ' ساعة</span>' +
        '</div>' +
        '<div class="overflow-x-auto"><table class="w-full min-w-[900px]">' +
          '<thead class="bg-surface-zebra"><tr>' +
            '<th class="px-3 py-2 text-right font-semibold text-text-secondary text-xs">رقم المادة</th>' +
            '<th class="px-3 py-2 text-right font-semibold text-text-secondary text-xs">اسم المادة</th>' +
            '<th class="px-3 py-2 text-right font-semibold text-text-secondary text-xs">المدرّس</th>' +
            '<th class="px-3 py-2 text-center font-semibold text-text-secondary text-xs">نظري</th>' +
            '<th class="px-3 py-2 text-center font-semibold text-text-secondary text-xs">عملي</th>' +
            '<th class="px-3 py-2 text-center font-semibold text-text-secondary text-xs">الساعات</th>' +
            '<th class="px-3 py-2 text-center font-semibold text-text-secondary text-xs">الوحدات</th>' +
            '<th class="px-3 py-2 text-center font-semibold text-text-secondary text-xs">حالة النموذج</th>' +
            '<th class="no-print px-3 py-2 text-center font-semibold text-text-secondary text-xs">إجراءات</th>' +
          '</tr></thead>' +
          '<tbody class="divide-y divide-border-subtle">' + rows + '</tbody>' +
        '</table></div>' +
      '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }

  // ============ VIEW SWITCHING ============
  var ccActiveView = 'list';

  function ccSwitchView(view) {
    ccActiveView = view;
    var isList = view === 'list';
    document.getElementById('viewList').classList.toggle('hidden', !isList);
    document.getElementById('viewPlan').classList.toggle('hidden', isList);
    var b1 = document.getElementById('tabListBtn');
    var b2 = document.getElementById('tabPlanBtn');
    var activeCls = 'bg-primary text-white shadow-sm';
    var idleCls = 'bg-surface-hover text-text-secondary hover:bg-primary-faint hover:text-primary';
    b1.className = 'tab-btn flex-1 sm:flex-none flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl text-sm font-bold transition-all ' + (isList ? activeCls : idleCls);
    b2.className = 'tab-btn flex-1 sm:flex-none flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl text-sm font-bold transition-all ' + (isList ? idleCls : activeCls);
    if (isList) {
      renderList();
    } else {
      if (!ccCurrentDept && departments.length) ccCurrentDept = departments[0].name;
      document.getElementById('ccPlanDeptSelect').value = ccCurrentDept || '';
      renderDeptGrid(departments.filter(function (d) { return !planSearchQuery() || d.name.indexOf(planSearchQuery()) !== -1; }));
      renderPlan();
    }
  }

  // ============ EVENTS ============
  try {
    fillListDeptFilter();
    var lSearch = document.getElementById('ccListSearch');
    var lClear = document.getElementById('ccListSearchClear');
    lSearch.addEventListener('input', function () {
      lClear.style.display = lSearch.value ? 'flex' : 'none';
      renderList();
    });
    lClear.addEventListener('click', function () { lSearch.value = ''; lClear.style.display = 'none'; renderList(); lSearch.focus(); });
    document.getElementById('ccListDeptFilter').addEventListener('change', renderList);
    document.getElementById('ccListStatusFilter').addEventListener('change', renderList);
    document.getElementById('ccPlanSearch').addEventListener('input', function () {
      renderDeptGrid(departments.filter(function (d) { return !planSearchQuery() || d.name.indexOf(planSearchQuery()) !== -1; }));
    });
    document.getElementById('ccPlanDeptSelect').addEventListener('change', function () {
      ccSelectDept(this.value, false);
    });

    window.ccSwitchView = ccSwitchView;
    renderList();
  } catch (e) {
    window.__ccInitError = String(e && e.message ? e.message : e);
  }
})();
