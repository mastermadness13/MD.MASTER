
(function () {
  var BOOT = window.TEACHERS_SUPER_ADMIN_COURSE_CONTENT_BOOT || {};
  'use strict';
  var H = window.CourseHelpers || {};
  var esc = H.esc || function (s) { return String(s == null ? '' : s); };
  var COURSES = BOOT.courses || [];
  var SYLLABUS_BY_COURSE = BOOT.syllabusByCourse || {};
  var FORM_BY_COURSE = BOOT.formByCourse || {};
  var VOCAB_BY_COURSE = BOOT.vocabByCourse || {};
  var selectedIds = {};

  var deptNames = [];
  (BOOT.departmentNames || []).forEach(function (n) { deptNames.push(n); });
  COURSES.forEach(function (c) {
    (c.dept_names || []).forEach(function (d) {
      if (deptNames.indexOf(d) === -1) deptNames.push(d);
    });
  });
  var departments = deptNames.filter(Boolean).map(function (name) { return { name: name }; });

  function semLabel(s) {
    var n = parseInt(s, 10);
    if (!n) return '—';
    var ord = ['الأول','الثاني','الثالث','الرابع','الخامس','السادس','السابع','الثامن'];
    return ord[n - 1] || ('الفصل ' + n);
  }

  function hoursBadge(c) {
    var total = c.total_hours || ((c.theoretical_hours || 0) + (c.practical_hours || 0));
    var th = c.theoretical_hours || 0;
    var ph = c.practical_hours || 0;
    var detail = th + ' نظري · ' + ph + ' عملي';
    return '<div class="text-center"><span class="font-bold text-text-primary text-sm">' + total + '</span><div class="cc-hours-detail">' + detail + '</div></div>';
  }

  function materialCell(c) {
    return '<div class="font-bold text-on-surface text-sm">' + esc(c.name) + '</div>' +
      '<div class="font-mono text-xs text-on-surface-variant mt-0.5" dir="ltr">' + esc(c.code) + '</div>';
  }

  function deptCell(c) {
    if (!c.dept_names || !c.dept_names.length) return '<span class="text-xs text-text-faint">—</span>';
    return '<div class="flex flex-wrap gap-1">' + c.dept_names.map(function (d) {
      return '<span class="text-xs font-semibold text-text-secondary">' + esc(d) + '</span>';
    }).join('<span class="text-text-faint mx-0.5">·</span>') + '</div>';
  }

  function formStatusBadge(c) {
    return H.formStatusBadge ? H.formStatusBadge(c.form_status) : '';
  }

  function pdfBadge(c) {
    return H.pdfStateBadge ? H.pdfStateBadge(c.pdf_state) : '';
  }

  function pdfHasFile(c) {
    return H.pdfStateHasFile ? H.pdfStateHasFile(c.pdf_state) : false;
  }

  // Layer 2: زر أساسي واحد يتبع pdf_state — الملف عمود لا قائمة منسدلة.
  function pdfPrimaryAction(c) {
    var state = c.pdf_state || 'none';
    var form = FORM_BY_COURSE[c.id];
    if (state === 'available' || state === 'approved') {
      var href = form && form.download_url
        ? form.download_url
        : ((form && form.id) ? '/course-file/' + form.id + '?download=1' : '#');
      return '<a href="' + href + '" class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-green-100 text-green-700 hover:bg-green-200 text-xs font-bold transition-colors cursor-pointer" title="تحميل الملف">' +
        '<span class="material-symbols-outlined text-base">download</span>تحميل</a>';
    }
    if (state === 'pending_review') {
      return '<span class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-blue-100 text-blue-700 text-xs font-bold whitespace-nowrap"><span class="material-symbols-outlined text-base">hourglass_top</span>قيد المراجعة</span>';
    }
    if (state === 'draft') {
      var editUrl = c.latest_form_submission_id
        ? '/teacher/super-admin/course-content/create?course_id=' + c.id + '&submission_id=' + c.latest_form_submission_id
        : '/teacher/super-admin/course-content/create?course_id=' + c.id;
      return '<a href="' + editUrl + '" class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-yellow-100 text-yellow-800 hover:bg-yellow-200 text-xs font-bold transition-colors cursor-pointer" title="متابعة التعديل">' +
        '<span class="material-symbols-outlined text-base">edit_document</span>متابعة</a>';
    }
    if (state === 'rejected') {
      var editUrl2 = c.latest_form_submission_id
        ? '/teacher/super-admin/course-content/create?course_id=' + c.id + '&submission_id=' + c.latest_form_submission_id
        : '/teacher/super-admin/course-content/create?course_id=' + c.id;
      return '<a href="' + editUrl2 + '" class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-red-100 text-red-700 hover:bg-red-200 text-xs font-bold transition-colors cursor-pointer" title="إعادة التسليم">' +
        '<span class="material-symbols-outlined text-base">refresh</span>إعادة</a>';
    }
    var newUrl = '/teacher/super-admin/course-content/create?course_id=' + c.id;
    return '<a href="' + newUrl + '" class="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-primary-faint text-primary hover:bg-primary/15 text-xs font-bold transition-colors cursor-pointer" title="إنشاء نموذج المقرر">' +
      '<span class="material-symbols-outlined text-base">add_circle</span>إنشاء</a>';
  }

  function teachersCell(c) {
    return H.teachersCell ? H.teachersCell(c.teachers) : '';
  }

  var openDropdown = null;
  var floatingMenu = null;

  function onViewportChange() {
    closeAllDropdowns();
  }

  function closeAllDropdowns() {
    if (floatingMenu && floatingMenu.parentNode) {
      floatingMenu.parentNode.removeChild(floatingMenu);
    }
    floatingMenu = null;
    openDropdown = null;
    window.removeEventListener('scroll', onViewportChange, true);
    window.removeEventListener('resize', onViewportChange);
  }

  document.addEventListener('click', function (e) {
    if (e.target.closest('.cc-actions-dropdown')) return;
    if (floatingMenu && floatingMenu.contains(e.target)) return;
    closeAllDropdowns();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' || e.key === 'Esc') closeAllDropdowns();
  });

  // Cells الأعمدة الملخصة (النموذج/المادة): شارة الحالة + زر تحميل بجانبها (قائمة المقررات)
  function pdfCell(c) {
    var badge = pdfBadge(c);
    var state = c.pdf_state || 'none';
    var form = FORM_BY_COURSE[c.id];
    var dl = '';
    if ((state === 'available' || state === 'approved') && form && form.id) {
      var formUrl = form.download_url || ('/course-file/' + form.id + '?download=1');
      dl = '<a href="' + formUrl + '" title="تحميل النموذج" aria-label="تحميل النموذج" ' +
        'class="inline-flex items-center justify-center w-6 h-6 rounded-lg bg-green-100 text-green-700 hover:bg-green-200 transition-colors cursor-pointer">' +
        '<span class="material-symbols-outlined text-sm">download</span></a>';
    } else if ((state === 'available' || state === 'approved') && !form) {
      dl = '<span title="النموذج معتمد لكن الملف غير مربوط (مفقود/محذوف)" aria-label="الملف غير مربوط" ' +
        'class="inline-flex items-center justify-center w-6 h-6 rounded-lg bg-amber-100 text-amber-700 cursor-help">' +
        '<span class="material-symbols-outlined text-sm">link_off</span></span>';
    }
    return badge ? '<div class="flex items-center justify-center gap-1.5">' + badge + dl + '</div>' : dl;
  }

  function actionsCell(c) {
    var syl = SYLLABUS_BY_COURSE[c.id];
    var form = FORM_BY_COURSE[c.id];
    var formEditUrl = c.latest_form_submission_id
      ? '/teacher/super-admin/course-content/create?course_id=' + c.id + '&submission_id=' + c.latest_form_submission_id
      : '/teacher/super-admin/course-content/create?course_id=' + c.id;
    var sylHref = (syl && syl.id)
      ? '/course-file/' + syl.id + '?download=1'
      : formEditUrl;

    var items = '';
    if (form && form.id) {
      var formUrl = form.download_url || ('/course-file/' + form.id + '?download=1');
      items += '<a href="' + formUrl + '"><span class="material-symbols-outlined text-base">description</span>تحميل المقرر</a>';
    }
    if (syl && syl.id) {
      items += '<a href="' + sylHref + '"><span class="material-symbols-outlined text-base">download</span>تحميل المنهج</a>';
    }
    var vocab = VOCAB_BY_COURSE[c.id];
    if (vocab && vocab.id) {
      items += '<a href="/course-file/' + vocab.id + '?download=1"><span class="material-symbols-outlined text-base">menu_book</span>تحميل المفردات</a>';
    }
    items += '<a href="/teacher/super-admin/course-content/vocabulary/' + c.id + '"><span class="material-symbols-outlined text-base">upload_file</span>رفع/إدارة المفردات</a>';
    items += '<button type="button" onclick="ccPreparePrint(this)" data-cid="' + c.id + '" data-sid="' + (c.latest_form_submission_id || '') + '"><span class="material-symbols-outlined text-base">print</span>طباعة المقرر</button>';
    items += '<a href="' + formEditUrl + '"><span class="material-symbols-outlined text-base">edit</span>إنشاء/تعديل المقرر</a>';

    var uid = 'cc-drop-' + c.id;
    return '<div class="flex items-center justify-center gap-2">' +
      pdfPrimaryAction(c) +
      '<div class="cc-actions-dropdown">' +
      '<button type="button" onclick="ccToggleDropdown(\'' + uid + '\', event)" class="flex items-center gap-1 px-2 py-1.5 rounded-lg border border-border bg-white hover:bg-primary-faint text-text-secondary text-xs font-bold transition-all cursor-pointer">' +
        '<span class="material-symbols-outlined text-base">more_vert</span>' +
      '</button>' +
      '<div id="' + uid + '" class="cc-actions-menu">' + items + '</div>' +
      '</div>' +
    '</div>';
  }

  window.ccToggleDropdown = function (id, e) {
    e.stopPropagation();
    var source = document.getElementById(id);
    if (!source) return;
    var wasOpen = !!(openDropdown && openDropdown === id);
    closeAllDropdowns();
    if (wasOpen) return;

    // قائمة عائمة في body — خارج أي حاوية مقتطعة (overflow)
    var menu = document.createElement('div');
    menu.className = 'cc-actions-menu open cc-menu-floating';
    menu.innerHTML = source.innerHTML;
    document.body.appendChild(menu);
    floatingMenu = menu;
    openDropdown = id;

    var btn = e.currentTarget || e.target;
    var rect = btn.getBoundingClientRect();
    var menuH = menu.offsetHeight;
    var spaceBelow = window.innerHeight - rect.bottom;
    if (spaceBelow < menuH + 8) {
      menu.style.bottom = (window.innerHeight - rect.top + 4) + 'px';
    } else {
      menu.style.top = (rect.bottom + 4) + 'px';
    }
    menu.style.right = Math.max(8, window.innerWidth - rect.right) + 'px';
    menu.style.left = 'auto';
    menu.style.position = 'fixed';

    window.addEventListener('scroll', onViewportChange, true);
    window.addEventListener('resize', onViewportChange);
  };

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
        if (win) { win.focus(); win.print(); }
        window.setTimeout(function () { if (frame.parentNode) frame.parentNode.removeChild(frame); }, 1000);
      };
      document.body.appendChild(frame);
    }
    frame.src = '/teacher/super-admin/course-content/' + sid + '?print=1';
  }
  window.ccPreparePrint = ccPreparePrint;

  // ============ BULK SELECT ============
  function updateBulkUI() {
    var keys = Object.keys(selectedIds);
    var count = keys.length;
    var headerBtn = document.getElementById('courseHeaderDeleteBtn');
    if (headerBtn) headerBtn.style.display = count > 0 ? 'inline' : 'none';
    document.querySelectorAll('.cc-row-cb').forEach(function (cb) {
      cb.closest('tr').classList.toggle('bg-primary/5', !!selectedIds[cb.value]);
    });
  }

  function toggleSelect(id) {
    if (selectedIds[id]) delete selectedIds[id]; else selectedIds[id] = true;
    updateBulkUI();
  }
  window.ccToggleSelect = toggleSelect;

  function toggleSelectAll() {
    var all = listRows();
    var allSelected = all.every(function (c) { return selectedIds[c.id]; });
    if (allSelected) { selectedIds = {}; } else { all.forEach(function (c) { selectedIds[c.id] = true; }); }
    renderList();
    updateBulkUI();
  }

  function bulkDelete() {
    var ids = Object.keys(selectedIds);
    if (!ids.length) return;
    if (!confirm('هل تريد حذف ' + ids.length + ' مقرر محدد؟')) return;
    var csrf = BOOT.csrfToken || '';
    fetch('/teacher/super-admin/course-content/bulk-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': csrf },
      body: 'course_ids=' + ids.join(',') + '&_csrf_token=' + encodeURIComponent(csrf)
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.success) {
        COURSES = COURSES.filter(function (c) { return !selectedIds[c.id]; });
        selectedIds = {};
        renderList();
        updateBulkUI();
      } else {
        alert(d && d.error ? d.error : 'حدث خطأ أثناء الحذف');
      }
    }).catch(function () { alert('حدث خطأ أثناء الحذف'); });
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
        if (st === '__has_file__') {
          if (!pdfHasFile(c)) return false;
        } else {
          var status = c.form_status || '';
          if (status !== st) return false;
        }
      }
      if (!q) return true;
      var hay = ((c.name || '') + ' ' + (c.code || '') + ' ' + (c.dept_names || []).join(' ') + ' ' + (c.teachers || []).join(' ') + ' ' + semLabel(c.semester)).toLowerCase();
      return hay.indexOf(q) !== -1;
    });
  }

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
      tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-12 text-center"><div class="flex flex-col items-center gap-2"><span class="material-symbols-outlined text-4xl text-text-faint">search_off</span><p class="text-text-muted text-sm">لا توجد مقررات مطابقة</p></div></td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(function (c, i) {
      return '<tr class="hover:bg-surface-hover transition-colors">' +
        '<td class="px-2 py-2 text-center"><input type="checkbox" value="' + c.id + '" class="cc-row-cb rounded border-gray-300 text-primary focus:ring-primary cursor-pointer" onchange="ccToggleSelect(' + c.id + ')"' + (selectedIds[c.id] ? ' checked' : '') + '></td>' +
        '<td class="px-2 py-2 text-center text-text-muted text-xs font-semibold">' + (i + 1) + '</td>' +
        '<td class="px-3 py-2">' + materialCell(c) + '</td>' +
        '<td class="px-3 py-2">' + deptCell(c) + '</td>' +
        '<td class="px-2 py-2 text-center text-xs font-semibold text-text-secondary">' + semLabel(c.semester) + '</td>' +
        '<td class="px-3 py-2">' + teachersCell(c) + '</td>' +
        '<td class="px-2 py-2 text-center whitespace-nowrap">' + pdfCell(c) + '</td>' +
        '<td class="px-2 py-2">' + hoursBadge(c) + '</td>' +
        '<td class="px-2 py-2">' + actionsCell(c) + '</td>' +
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

  function planActionsCell(c) {
    var syl = SYLLABUS_BY_COURSE[c.id];
    var form = FORM_BY_COURSE[c.id];
    var formEditUrl = c.latest_form_submission_id
      ? '/teacher/super-admin/course-content/create?course_id=' + c.id + '&submission_id=' + c.latest_form_submission_id
      : '/teacher/super-admin/course-content/create?course_id=' + c.id;
    var sylHref = (syl && syl.id)
      ? '/teacher/super-admin/course-content/course-file/' + syl.id + '?download=1'
      : formEditUrl;

    var items = '';
    if (form && form.id) {
      items += '<a href="/course-file/' + form.id + '?download=1"><span class="material-symbols-outlined text-base">description</span>تحميل المقرر</a>';
    }
    if (syl && syl.id) {
      items += '<a href="' + sylHref + '"><span class="material-symbols-outlined text-base">download</span>تحميل المنهج</a>';
    }
    items += '<button type="button" onclick="ccPreparePrint(this)" data-cid="' + c.id + '" data-sid="' + (c.latest_form_submission_id || '') + '"><span class="material-symbols-outlined text-base">print</span>طباعة المقرر</button>';
    items += '<a href="' + formEditUrl + '"><span class="material-symbols-outlined text-base">edit</span>إنشاء/تعديل المقرر</a>';

    var uid = 'ccp-drop-' + c.id;
    return '<div class="flex items-center justify-center gap-2 no-print">' +
      pdfPrimaryAction(c) +
      '<div class="cc-actions-dropdown">' +
      '<button type="button" onclick="ccToggleDropdown(\'' + uid + '\', event)" class="flex items-center gap-1 px-2 py-1.5 rounded-lg border border-border bg-white hover:bg-primary-faint text-text-secondary text-xs font-bold transition-all cursor-pointer">' +
        '<span class="material-symbols-outlined text-base">more_vert</span>' +
      '</button>' +
      '<div id="' + uid + '" class="cc-actions-menu">' + items + '</div>' +
      '</div>' +
    '</div>';
  }

  function planDeptCell(c) {
    if (!c.dept_names || !c.dept_names.length) return '<span class="text-xs text-text-faint">—</span>';
    return c.dept_names.map(function (d) {
      return '<span class="text-xs font-semibold text-text-secondary">' + esc(d) + '</span>';
    }).join('<span class="text-text-faint mx-0.5">·</span>');
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
          '<td class="px-3 py-2">' + materialCell(c) + '</td>' +
          '<td class="px-3 py-2">' + planDeptCell(c) + '</td>' +
          '<td class="px-2 py-2 text-center text-xs font-semibold text-text-secondary">' + semLabel(c.semester) + '</td>' +
          '<td class="px-3 py-2">' + teachersCell(c) + '</td>' +
          '<td class="px-2 py-2 text-center whitespace-nowrap">' + pdfCell(c) + '</td>' +
          '<td class="px-2 py-2">' + hoursBadge(c) + '</td>' +
          '<td class="no-print px-2 py-2">' + planActionsCell(c) + '</td>' +
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
        '<div class="overflow-x-auto"><table class="w-full min-w-[750px]">' +
          '<thead class="bg-surface-zebra"><tr>' +
            '<th class="px-3 py-2 text-right font-semibold text-text-secondary text-xs">المادة</th>' +
            '<th class="px-3 py-2 text-right font-semibold text-text-secondary text-xs">القسم</th>' +
            '<th class="px-2 py-2 text-center font-semibold text-text-secondary text-xs">الفصل</th>' +
            '<th class="px-3 py-2 text-right font-semibold text-text-secondary text-xs">المدرّس</th>' +
            '<th class="px-2 py-2 text-center font-semibold text-text-secondary text-xs">النموذج</th>' +
            '<th class="px-2 py-2 text-center font-semibold text-text-secondary text-xs">الساعات</th>' +
            '<th class="no-print px-2 py-2 text-center font-semibold text-text-secondary text-xs">الإجراءات</th>' +
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
      if (!ccCurrentDept && departments.length) {
        var defaultDept = departments.filter(function (d) { return d.name.indexOf('بحث') !== -1 || d.name.indexOf('تطوير') !== -1; });
        ccCurrentDept = defaultDept.length ? defaultDept[0].name : departments[0].name;
      }
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

    var selectAllCb = document.getElementById('courseSelectAll');
    if (selectAllCb) selectAllCb.addEventListener('change', toggleSelectAll);
    var headerDelBtn = document.getElementById('courseHeaderDeleteBtn');
    if (headerDelBtn) headerDelBtn.addEventListener('click', bulkDelete);

    window.ccSwitchView = ccSwitchView;
    renderList();
  } catch (e) {
    window.__ccInitError = String(e && e.message ? e.message : e);
  }
})();
