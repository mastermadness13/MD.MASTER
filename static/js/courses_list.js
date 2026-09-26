(function () {
  var BOOT = window.COURSES_LIST_BOOT || {};
  var URLS = BOOT.urls || {};
  // ===== DATA (server-rendered) =====
  var DEPT_PLANS = BOOT.plans || [];
  var PREREQ_OPTIONS = BOOT.prereqOptions || {};
  var STATUS_META = BOOT.statusMeta || {};
  var CAN_MANAGE = BOOT.canManage;

  var COURSE_DEPT_MAP = {};
  var COURSE_CONTENT = {};
  var COURSE_DEPT_PLACEMENTS = {};
  (BOOT.courses || []).forEach(function (c) {
    COURSE_DEPT_MAP[c.id] = c.dept_ids || [];
    COURSE_DEPT_PLACEMENTS[c.id] = (c.dept_semesters || []).reduce(function (m, p) {
      m[p.dept_id] = { department_id: p.dept_id, semester: p.semester || 1, dept_name: p.dept_name };
      return m;
    }, {});
    COURSE_CONTENT[c.id] = { form: c.form || null, syllabus: c.syllabus || null, syllabusCount: c.syllabusCount || 0 };
    c.teachers = c.teachers || [];
    c.form_status = c.form_status || '';
  });
  var IS_RD = BOOT.isRd;
  var IS_TEACHER = BOOT.isTeacher;

  var departments = DEPT_PLANS.map(function (d) {
    return {
      id: d.department.id,
      name: d.department.name,
      icon: d.department.icon,
      semesters: d.department.semesters,
      tables: d.semesters.map(function (s) {
        return { semester: s.semester, title: s.title, courses: s.courses || [] };
      })
    };
  });

  // ===== STATE =====
  var activeView = BOOT.view === 'plan' ? 'plan' : 'list';
  var currentDeptId = null;
  var ITEMS_PER_PAGE = 10;
  var currentPage = BOOT.page || 1;

  // ===== ICON PICKER =====
  var iconPicker = null;
  var iconPickerEl = document.getElementById('mIconPicker');
  if (iconPickerEl && window.CourseIconPicker) {
    iconPicker = window.CourseIconPicker.create(iconPickerEl, { value: '💻' });
  }

  // ===== HELPERS =====
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function deptById(id) {
    var found = null;
    departments.forEach(function (d) { if (d.id === id) found = d; });
    return found;
  }
  function tableCount(dept) { return dept.tables.length; }
  function totalCourses(dept) {
    var n = 0;
    dept.tables.forEach(function (t) { n += t.courses.length; });
    return n;
  }
  function totalUnits(dept) {
    var n = 0;
    dept.tables.forEach(function (t) {
      t.courses.forEach(function (c) { n += (c.units || 0); });
    });
    return n;
  }
  function courseHours(c) {
    return { theory: c.theory || 0, practical: c.practical || 0, hours: c.weekly_hours || ((c.theory || 0) + (c.practical || 0)) };
  }
  function courseIcon(c) {
    var ic = esc(c.icon || '📖');
    return '<span class="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-surface-zebra text-base shrink-0 align-middle">' + ic + '</span>';
  }
  function courseCodeLink(c) {
    return '<a href="/courses/' + (c.id || 0) + '" class="inline-flex items-center gap-1 font-mono font-bold text-primary text-sm no-underline hover:text-primary/80 transition-colors" title="' + esc(c.name || c.code || '') + '">' + esc(c.code || '') + '</a>';
  }
  function prereqOf(c) {
    return c.requires || '';
  }
  function prereqName(code) {
    var found = '';
    departments.forEach(function (d) {
      d.tables.forEach(function (t) {
        t.courses.forEach(function (c) {
          if (c.code === code && !found) found = c.name;
        });
      });
    });
    return found;
  }
  function courseByCode(code) {
    var match = null;
    departments.forEach(function (d) {
      if (match) return;
      d.tables.forEach(function (t) {
        if (match) return;
        t.courses.forEach(function (c) {
          if (!match && String(c.code).trim() === String(code).trim()) {
            match = c;
          }
        });
      });
    });
    return match;
  }
  function prereqBadges(c) {
    var r = prereqOf(c);
    if (!r || (r.length && r.length === 0)) return '<span class="text-text-faint font-semibold">—</span>';
    var codes = Object.prototype.toString.call(r) === '[object Array]' ? r : [r];
    var html = '';
    codes.forEach(function (x) {
      var nm = prereqName(x);
      var matchedCourse = courseByCode(x);
      var tag = matchedCourse ? 'a' : 'span';
      var href = matchedCourse ? ' href="/courses/' + matchedCourse.id + '"' : '';
      var pointerClass = matchedCourse ? ' cursor-pointer hover:bg-primary/10' : '';
      html += '<' + tag + href + ' class="inline-flex items-center gap-1 font-mono text-[11px] font-bold text-primary bg-primary-faint px-1.5 py-0.5 rounded border border-primary/20 mx-0.5 no-underline transition-all ' + pointerClass + '" title="' + esc(nm || x) + '">' +
        '<span class="material-symbols-outlined text-[12px]">arrow_back</span>' + esc(x) +
      '</' + tag + '>';
    });
    return html;
  }

  function contentBtns(c) {
    var cc = COURSE_CONTENT[c.id] || {};
    var html = '';
    if (cc.form) {
      html += '<a href="/course-file/' + cc.form.id + '?download=1" class="inline-flex items-center gap-1 rounded-lg border border-primary/30 text-primary px-2 py-1.5 text-xs font-bold no-underline hover:bg-primary-faint transition-all" data-tip="تحميل المقرر" aria-label="تحميل المقرر"><span class="material-symbols-outlined text-sm">description</span>تحميل المقرر</a>';
    }
    if (cc.syllabus) {
      html += '<a href="/course-file/' + cc.syllabus.id + '?download=1" class="inline-flex items-center gap-1 rounded-lg border border-primary/30 text-primary px-2 py-1.5 text-xs font-bold no-underline hover:bg-primary-faint transition-all" data-tip="تحميل المنهج" aria-label="تحميل المنهج"><span class="material-symbols-outlined text-sm">download</span>تحميل المنهج</a>';
    }
    if (IS_RD) {
      var href = cc.form ? '/teacher/super-admin/course-content/' + cc.form.id : '/teacher/super-admin/course-content/create?course_id=' + c.id;
      html += '<a href="' + href + '" class="w-7 h-7 inline-flex items-center justify-center rounded-lg hover:bg-primary-faint text-primary transition-all" data-tip="إنشاء/تعديل المقرر" aria-label="إنشاء/تعديل المقرر"><span class="material-symbols-outlined text-base">upload_file</span></a>';
    }
    return html;
  }

  // ===== FLAT COURSE LIST (deduplicated by course ID) =====
  function flatCourses() {
    var map = {};
    var order = [];
    departments.forEach(function (d) {
      d.tables.forEach(function (t, ti) {
        t.courses.forEach(function (c, ci) {
          var key = c.id;
          if (!map[key]) {
            map[key] = { course: c, depts: [], semesters: [] };
            order.push(key);
          }
          map[key].depts.push({
            deptId: d.id, deptName: d.name, deptIcon: d.icon,
            tableIdx: ti, courseIdx: ci, tableTitle: t.title, semester: t.semester
          });
          if (map[key].semesters.indexOf(t.title) === -1) {
            map[key].semesters.push(t.title);
          }
        });
      });
    });
    return order.map(function (k) { return map[k]; });
  }

  function filteredFlat() {
    var q = (document.getElementById('listSearch').value || '').trim().toLowerCase();
    var did = document.getElementById('listDeptFilter').value;
    return flatCourses().filter(function (r) {
      if (did) {
        var hasDept = r.depts.some(function (de) { return String(de.deptId) === did; });
        if (!hasDept) return false;
      }
      if (!q) return true;
      return r.course.code.toLowerCase().indexOf(q) !== -1 || r.course.name.toLowerCase().indexOf(q) !== -1;
    });
  }

  // ===== LIST VIEW =====
  function deptBadge(d) {
    return '<span class="inline-flex items-center gap-1 text-xs font-semibold text-text-secondary bg-surface-zebra px-2 py-0.5 rounded-full"><span class="material-symbols-outlined text-[14px] text-text-muted">' + d.deptIcon + '</span>' + esc(d.deptName) + '</span>';
  }

  function formStatusBadge(status) {
    if (!status || !STATUS_META[status]) {
      return '<span class="text-xs text-text-faint">لا يوجد نموذج بعد</span>';
    }
    var meta = STATUS_META[status];
    return '<span class="inline-block px-2.5 py-1 rounded-full text-xs font-bold whitespace-nowrap ' + meta['class'] + '">' + esc(meta.label) + '</span>';
  }

  function teachersCell(c) {
    var H = window.CourseHelpers;
    return H && H.teachersCell ? H.teachersCell(c.teachers) : '';
  }

  // ===== NEW: Compact table helpers =====
  var _openClDrop = null;
  var _clFloating = null;
  function clOnViewportChange() {
    clCloseAllDropdowns();
  }
  function clCloseAllDropdowns() {
    if (_clFloating && _clFloating.parentNode) {
      _clFloating.parentNode.removeChild(_clFloating);
    }
    _clFloating = null;
    _openClDrop = null;
    window.removeEventListener('scroll', clOnViewportChange, true);
    window.removeEventListener('resize', clOnViewportChange);
  }
  document.addEventListener('click', function (e) {
    if (e.target.closest('.cl-actions-dropdown')) return;
    if (_clFloating && _clFloating.contains(e.target)) return;
    clCloseAllDropdowns();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' || e.key === 'Esc') clCloseAllDropdowns();
  });

  window.clToggleDropdown = function (id, e) {
    e.stopPropagation();
    var source = document.getElementById(id);
    if (!source) return;
    var wasOpen = !!(_openClDrop && _openClDrop === id);
    clCloseAllDropdowns();
    if (wasOpen) return;

    // قائمة عائمة في body — خارج أي حاوية مقتطعة (overflow)
    var menu = document.createElement('div');
    menu.className = 'cl-actions-menu open cl-menu-floating';
    menu.innerHTML = source.innerHTML;
    document.body.appendChild(menu);
    _clFloating = menu;
    _openClDrop = id;

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

    window.addEventListener('scroll', clOnViewportChange, true);
    window.addEventListener('resize', clOnViewportChange);
  };

  function clMaterialCell(c) {
    return '<div class="font-bold text-on-surface text-sm">' + esc(c.name) + '</div>' +
      '<div class="font-mono text-xs text-on-surface-variant mt-0.5" dir="ltr">' + esc(c.code) + '</div>';
  }

  function clDeptCell(r) {
    if (!r.depts || !r.depts.length) return '<span class="text-xs text-text-faint">—</span>';
    return r.depts.map(function (d) {
      return '<span class="text-xs font-semibold text-text-secondary">' + esc(d.deptName || '') + '</span>';
    }).join('<span class="text-text-faint mx-0.5">·</span>');
  }

  function clDeptSemCell(r) {
    if (!r.depts || !r.depts.length) return '<span class="text-text-faint">—</span>';
    return r.depts.map(function (de) {
      return '<span class="px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 text-xs font-bold">' + esc(de.deptName || '') + ' — ف' + (de.semester || 1) + '</span>';
    }).join(' ');
  }

  function clHoursBadge(c) {
    var h = courseHours(c);
    return '<div class="text-center"><span class="font-bold text-text-primary text-sm">' + h.hours + '</span><div class="cl-hours-detail">' + h.theory + ' نظري · ' + h.practical + ' عملي</div></div>';
  }

  function clPlanHoursBadge(c) {
    var h = courseHours(c);
    return '<div class="text-center"><span class="font-bold text-text-secondary text-sm">' + h.hours + '</span><div class="cl-hours-detail">' + h.theory + ' نظري · ' + h.practical + ' عملي</div></div>';
  }

  function clActionsDropdown(deptId, tableIdx, courseIdx, c) {
    var uid = 'cld-' + c.id + '-' + deptId;
    var items = '';
    items += '<button onclick="openDetails(' + deptId + ',' + tableIdx + ',' + courseIdx + ')"><span class="material-symbols-outlined text-base">visibility</span>عرض التفاصيل</button>';
    var cc = COURSE_CONTENT[c.id] || {};
    if (IS_RD) {
      var href = cc.form ? '/teacher/super-admin/course-content/' + cc.form.id : '/teacher/super-admin/course-content/create?course_id=' + c.id;
      items += '<a href="' + href + '"><span class="material-symbols-outlined text-base">upload_file</span>إنشاء/تعديل المقرر</a>';
    }
    if (CAN_MANAGE) {
      items += '<button onclick="openEditModal(' + deptId + ',' + tableIdx + ',' + courseIdx + ')"><span class="material-symbols-outlined text-base">edit</span>تعديل المادة</button>';
      items += '<button class="cl-danger" onclick="deleteCourse(' + deptId + ',' + tableIdx + ',' + courseIdx + ')"><span class="material-symbols-outlined text-base">delete</span>حذف المادة</button>';
    }
    return '<div class="cl-actions-dropdown">' +
      '<button type="button" onclick="clToggleDropdown(\'' + uid + '\', event)" class="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border bg-white hover:bg-primary-faint text-primary text-xs font-bold transition-all cursor-pointer">' +
        '<span class="material-symbols-outlined text-base">more_vert</span>الإجراءات' +
      '</button>' +
      '<div id="' + uid + '" class="cl-actions-menu">' + items + '</div>' +
    '</div>';
  }

  function clPlanActionsDropdown(deptId, tableIdx, courseIdx, c) {
    var uid = 'clpd-' + c.id + '-' + deptId;
    var items = '';
    items += '<button onclick="openDetails(' + deptId + ',' + tableIdx + ',' + courseIdx + ')"><span class="material-symbols-outlined text-base">visibility</span>عرض التفاصيل</button>';
    var cc = COURSE_CONTENT[c.id] || {};
    if (IS_RD) {
      var href = cc.form ? '/teacher/super-admin/course-content/' + cc.form.id : '/teacher/super-admin/course-content/create?course_id=' + c.id;
      items += '<a href="' + href + '"><span class="material-symbols-outlined text-base">upload_file</span>إنشاء/تعديل المقرر</a>';
    }
    if (CAN_MANAGE) {
      items += '<button onclick="openEditModal(' + deptId + ',' + tableIdx + ',' + courseIdx + ')"><span class="material-symbols-outlined text-base">edit</span>تعديل المادة</button>';
      items += '<button class="cl-danger" onclick="deleteCourse(' + deptId + ',' + tableIdx + ',' + courseIdx + ')"><span class="material-symbols-outlined text-base">delete</span>حذف المادة</button>';
    }
    return '<div class="cl-actions-dropdown">' +
      '<button type="button" onclick="clToggleDropdown(\'' + uid + '\', event)" class="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border bg-white hover:bg-primary-faint text-primary text-xs font-bold transition-all cursor-pointer">' +
        '<span class="material-symbols-outlined text-base">more_vert</span>الإجراءات' +
      '</button>' +
      '<div id="' + uid + '" class="cl-actions-menu">' + items + '</div>' +
    '</div>';
  }

  function renderList() {
    var tbody = document.getElementById('courseTableBody');
    var rows = filteredFlat();
    var total = rows.length;
    var totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));
    if (currentPage > totalPages) currentPage = totalPages;

    document.getElementById('courseCount').textContent = total;

    var start = (currentPage - 1) * ITEMS_PER_PAGE;
    var end = Math.min(start + ITEMS_PER_PAGE, total);
    var page = rows.slice(start, end);

    if (page.length === 0) {
      tbody.innerHTML = '<tr><td colspan="' + (CAN_MANAGE ? 8 : 7) + '" class="px-4 py-12 text-center"><div class="flex flex-col items-center gap-2"><span class="material-symbols-outlined text-4xl text-text-faint">search_off</span><p class="text-text-muted text-sm">لا توجد مقررات مطابقة للبحث</p></div></td></tr>';
    } else {
      var html = '';
      page.forEach(function (r, i) {
        var c = r.course;
        var first = r.depts[0];
        html += '<tr class="hover:bg-surface-hover transition-colors">' +
          (CAN_MANAGE ? '<td class="px-2 py-2 text-center"><input type="checkbox" class="course-delete-cb rounded border-gray-300 text-primary focus:ring-primary cursor-pointer" value="' + c.id + '" onchange="onCourseDeleteCheck()" /></td>' : '') +
          '<td class="px-2 py-2 text-center text-text-muted text-xs font-semibold">' + (start + i + 1) + '</td>' +
          '<td class="px-3 py-2">' + clMaterialCell(c) + '</td>' +
          '<td class="px-2 py-2 w-56 min-w-[170px] max-w-[280px]"><div class="flex flex-wrap gap-1 min-w-0">' + clDeptSemCell(r) + '</div></td>' +
          '<td class="px-3 py-2">' + teachersCell(c) + '</td>' +
          '<td class="px-2 py-2 text-center whitespace-nowrap">' + formStatusBadge(c.form_status) + '</td>' +
          '<td class="px-2 py-2">' + clHoursBadge(c) + '</td>' +
          '<td class="px-2 py-2">' + clActionsDropdown(first.deptId, first.tableIdx, first.courseIdx, c) + '</td>' +
        '</tr>';
      });
      tbody.innerHTML = html;
    }

    document.getElementById('paginationInfo').textContent = total === 0
      ? 'لا توجد نتائج'
      : 'عرض ' + (start + 1) + ' إلى ' + end + ' من ' + total + ' مقرر';

    var pager = document.getElementById('pagination');
    var phtml = '';
    phtml += '<button onclick="goPage(' + (currentPage - 1) + ')" ' + (currentPage <= 1 ? 'disabled' : '') + ' class="w-8 h-8 flex items-center justify-center rounded-lg border border-border bg-white text-text-secondary hover:bg-surface-hover transition-all disabled:opacity-40 disabled:cursor-not-allowed"><span class="material-symbols-outlined text-lg">chevron_right</span></button>';
    for (var p = 1; p <= totalPages; p++) {
      phtml += '<button onclick="goPage(' + p + ')" class="w-8 h-8 flex items-center justify-center rounded-lg text-xs font-bold transition-all ' + (p === currentPage ? 'border border-primary bg-primary text-white' : 'border border-border bg-white text-text-secondary hover:bg-surface-hover') + '">' + p + '</button>';
    }
    phtml += '<button onclick="goPage(' + (currentPage + 1) + ')" ' + (currentPage >= totalPages ? 'disabled' : '') + ' class="w-8 h-8 flex items-center justify-center rounded-lg border border-border bg-white text-text-secondary hover:bg-surface-hover transition-all disabled:opacity-40 disabled:cursor-not-allowed"><span class="material-symbols-outlined text-lg">chevron_left</span></button>';
    pager.innerHTML = phtml;
  }

  function goPage(p) {
    var rows = filteredFlat();
    var totalPages = Math.max(1, Math.ceil(rows.length / ITEMS_PER_PAGE));
    if (p < 1) p = 1;
    if (p > totalPages) p = totalPages;
    currentPage = p;
    syncUrl();
    renderList();
  }

  function syncUrl() {
    if (!window.history || !window.history.replaceState) return;
    var q = '?view=' + activeView + '&page=' + currentPage;
    window.history.replaceState(null, '', q);
  }

  // ===== PLAN VIEW =====
  function fillSelects() {
    var selList = document.getElementById('listDeptFilter');
    selList.innerHTML = '';
    var optAll = document.createElement('option');
    optAll.value = '';
    optAll.textContent = 'جميع الأقسام';
    selList.appendChild(optAll);
    var selPlan = document.getElementById('planDeptSelect');
    selPlan.innerHTML = '';
    departments.forEach(function (d) {
      var label = d.name + ' — ' + tableCount(d) + ' جداول';
      var o1 = document.createElement('option');
      o1.value = d.id;
      o1.textContent = label;
      selList.appendChild(o1);
      var o2 = document.createElement('option');
      o2.value = d.id;
      o2.textContent = label;
      selPlan.appendChild(o2);
    });
  }

  function planSearchQuery() {
    return (document.getElementById('planSearch').value || '').trim();
  }

  function renderDeptGrid(filtered) {
    var grid = document.getElementById('planDeptGrid');
    grid.innerHTML = '';
    if (filtered.length === 0) {
      grid.innerHTML = '<p class="text-sm text-text-muted w-full py-2">لا يوجد قسم مطابق للبحث</p>';
      return;
    }
    filtered.forEach(function (d) {
      var btn = document.createElement('button');
      var count = tableCount(d);
      var countLabel = count === 1 ? 'جدول واحد' : count + ' جداول';
      btn.className = 'dept-card flex items-center gap-2 px-4 py-2.5 rounded-xl border text-sm font-semibold transition-all cursor-pointer ' +
        (d.id === currentDeptId ? 'active border-primary bg-primary-faint text-primary' : 'border-border bg-white text-text-secondary hover:bg-surface-hover hover:text-primary');
      btn.innerHTML =
        '<span class="material-symbols-outlined text-lg">' + d.icon + '</span>' +
        '<span>' + esc(d.name) + '</span>' +
        '<span class="text-[11px] font-bold px-2 py-0.5 rounded-full ' + (d.id === currentDeptId ? 'bg-white text-primary' : 'bg-surface-zebra text-text-muted') + '">' + countLabel + '</span>';
      btn.onclick = function () { selectDept(d.id, true); };
      grid.appendChild(btn);
    });
  }

  function selectDept(id, scroll) {
    currentDeptId = id;
    document.getElementById('planDeptSelect').value = id;
    renderDeptGrid(departments.filter(function (d) { return !planSearchQuery() || d.name.indexOf(planSearchQuery()) !== -1; }));
    renderPlan();
    if (scroll) {
      var el = document.getElementById('planTablesContainer');
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  function tableCard(dept, t, tableIdx) {
    var units = 0;
    t.courses.forEach(function (c) { units += (c.units || 0); });
    var rows = '';
    t.courses.forEach(function (c, i) {
      var h = courseHours(c);
      var dragAttrs = CAN_MANAGE
        ? ' draggable="true" data-course-id="' + c.id + '" data-dept-id="' + dept.id + '" data-semester="' + t.semester + '" ondragstart="dragStartCourse(event)" ondragend="dragEndCourse(event)"'
        : '';
      rows += '<tr class="course-row hover:bg-surface-hover transition-colors' + (CAN_MANAGE ? ' cursor-grab' : '') + '"' + dragAttrs + '>' +
        (CAN_MANAGE ? '<td class="px-3 py-2 text-center"><input type="checkbox" class="ws-course-cb rounded border-gray-300 text-primary focus:ring-primary cursor-pointer" data-course-id="' + c.id + '" data-dept-id="' + dept.id + '" data-semester="' + t.semester + '" onchange="onCourseCheck()" /></td>' : '') +
        '<td class="px-3 py-2">' + clMaterialCell(c) + '</td>' +
        '<td class="px-3 py-2 text-center text-xs font-semibold text-text-secondary">' + esc(c.requires || '—') + '</td>' +
        '<td class="px-3 py-2">' + teachersCell(c) + '</td>' +
        '<td class="px-2 py-2">' + clPlanHoursBadge(c) + '</td>' +
        '<td class="no-print px-2 py-2">' + clPlanActionsDropdown(dept.id, tableIdx, i, c) + '</td>' +
      '</tr>';
    });
    var addBtn = CAN_MANAGE
      ? '<button onclick="openAddModal(' + dept.id + ',' + tableIdx + ')" class="no-print w-8 h-8 rounded-lg bg-primary text-white hover:bg-primary-light inline-flex items-center justify-center transition-all shadow-sm" title="إضافة مادة لهذا الجدول">' +
        '<span class="material-symbols-outlined text-lg">add</span></button>'
      : '';
    var zoneAttrs = CAN_MANAGE
      ? ' data-dept-id="' + dept.id + '" data-semester="' + t.semester + '" ondragover="dragOverZone(event)" ondragleave="dragLeaveZone(event)" ondrop="dropCourse(event)"'
      : '';
    return '<div class="print-block ' + (CAN_MANAGE ? 'drop-zone ' : '') + 'bg-white rounded-xl border border-border shadow-sm overflow-hidden print-sheet"' + zoneAttrs + '>' +
      '<div class="px-4 py-3 border-b border-border-subtle flex items-center justify-between bg-gradient-to-l from-primary/5 to-transparent">' +
        '<div class="flex items-center gap-2.5">' +
          '<span class="w-8 h-8 rounded-lg bg-primary-faint text-primary flex items-center justify-center"><span class="material-symbols-outlined text-lg">table_chart</span></span>' +
          '<div>' +
            '<h3 class="text-sm font-bold text-text-primary m-0 leading-tight">' + esc(dept.name) + ' — ' + esc(t.title) + '</h3>' +
            '<span class="text-[11px] text-text-muted">' + esc(t.subtitle || '') + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="flex items-center gap-2">' +
          '<span class="text-xs font-bold text-primary bg-primary-faint px-2.5 py-1 rounded-full whitespace-nowrap">' + units + ' وحدة</span>' +
          addBtn +
        '</div>' +
      '</div>' +
      '<div class="overflow-x-auto">' +
      '<table class="w-full min-w-[700px]">' +
        '<thead class="bg-surface-zebra">' +
          '<tr>' +
            (CAN_MANAGE ? '<th class="px-3 py-2 text-center font-semibold text-text-secondary text-xs w-10"><div class="flex items-center justify-center gap-1"><input type="checkbox" class="ws-select-all rounded border-gray-300 text-primary focus:ring-primary cursor-pointer" data-dept-id="' + dept.id + '" data-semester="' + t.semester + '" onchange="toggleSelectAll(this)" /><button type="button" class="ws-header-delete material-symbols-outlined text-red-600 hover:text-red-700 transition-colors bg-transparent border-0 cursor-pointer" data-dept-id="' + dept.id + '" data-semester="' + t.semester + '" style="display:none" title="حذف المحدد">delete</button></div></th>' : '') +
            '<th class="px-3 py-2 text-right font-semibold text-text-secondary text-xs">المادة</th>' +
            '<th class="px-2 py-2 text-center font-semibold text-text-secondary text-xs">المتطلب</th>' +
            '<th class="px-3 py-2 text-right font-semibold text-text-secondary text-xs">المدرّس</th>' +
            '<th class="px-2 py-2 text-center font-semibold text-text-secondary text-xs">الساعات</th>' +
            '<th class="no-print px-2 py-2 text-center font-semibold text-text-secondary text-xs">إجراءات</th>' +
          '</tr>' +
        '</thead>' +
        '<tbody class="divide-y divide-border-subtle">' + rows + '</tbody>' +
      '</table>' +
      '</div>' +
    '</div>';
  }

  function renderPlan() {
    var container = document.getElementById('planTablesContainer');
    container.innerHTML = '';
    var dept = deptById(currentDeptId);
    if (!dept) {
      container.innerHTML =
        '<div class="bg-white rounded-2xl border border-dashed border-border py-16 text-center">' +
          '<span class="material-symbols-outlined text-[44px] text-text-faint">search</span>' +
          '<p class="text-text-secondary font-semibold mt-3">اختر قسماً من الأعلى لعرض جداول الخطة الدراسية</p>' +
        '</div>';
      return;
    }

    var count = tableCount(dept);
    var html = '';

    html += '<div class="bg-gradient-to-l from-primary to-purple-800 rounded-2xl px-5 py-4 text-white shadow-sm mb-5 flex items-center justify-between flex-wrap gap-3">' +
      '<div class="flex items-center gap-3">' +
        '<span class="w-10 h-10 rounded-xl bg-white/15 flex items-center justify-center"><span class="material-symbols-outlined text-2xl">' + dept.icon + '</span></span>' +
        '<div>' +
          '<h2 class="text-base font-bold m-0 leading-tight text-white">' + esc(dept.name) + '</h2>' +
          '<span class="text-xs text-white/70">' + (count === 1 ? 'جدول واحد' : count + ' جداول') + ' للخطة الدراسية</span>' +
        '</div>' +
      '</div>' +
      '<div class="flex items-center gap-2">' +
        '<div class="bg-white/15 rounded-xl px-4 py-2 text-center">' +
          '<div class="text-lg font-bold leading-none">' + count + '</div>' +
          '<div class="text-[11px] text-white/70 mt-1">جداول</div>' +
        '</div>' +
        '<div class="bg-white/15 rounded-xl px-4 py-2 text-center">' +
          '<div class="text-lg font-bold leading-none">' + totalCourses(dept) + '</div>' +
          '<div class="text-[11px] text-white/70 mt-1">مادة</div>' +
        '</div>' +
        '<div class="bg-white/15 rounded-xl px-4 py-2 text-center">' +
          '<div class="text-lg font-bold leading-none">' + totalUnits(dept) + '</div>' +
          '<div class="text-[11px] text-white/70 mt-1">وحدة</div>' +
        '</div>' +
      '</div>' +
    '</div>';

    html += '<div class="grid grid-cols-1 gap-4">';
    dept.tables.forEach(function (t, ti) {
      html += tableCard(dept, t, ti);
    });
    html += '</div>';

    container.innerHTML = html;
  }

  // ===== VIEW SWITCHING =====
  function tabBtnClasses(active) {
    return 'tab-btn flex-1 sm:flex-none flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl text-sm font-bold transition-all ' +
      (active ? 'bg-primary text-white shadow-sm' : 'bg-surface-hover text-text-secondary hover:bg-primary-faint hover:text-primary');
  }

  function switchView(view) {
    var activeViewChanged = activeView !== view;
    activeView = view;
    var isList = view === 'list';
    var isPlan = view === 'plan';

    var vList = document.getElementById('viewList');
    var vPlan = document.getElementById('viewPlan');
    if (vList) vList.classList.toggle('hidden', !isList);
    if (vPlan) vPlan.classList.toggle('hidden', !isPlan);

    var b1 = document.getElementById('tabListBtn');
    var b2 = document.getElementById('tabPlanBtn');
    if (b1) b1.className = tabBtnClasses(isList);
    if (b2) b2.className = tabBtnClasses(isPlan);

    if (isList) {
      if (activeViewChanged) currentPage = 1;
      renderList();
    } else if (isPlan) {
      if (!currentDeptId && departments.length) currentDeptId = departments[0].id;
      document.getElementById('planDeptSelect').value = currentDeptId || '';
      renderDeptGrid(departments.filter(function (d) { return !planSearchQuery() || d.name.indexOf(planSearchQuery()) !== -1; }));
      renderPlan();
    }
    syncUrl();
  }

  // ===== COURSE MODAL =====
  var modalMode = 'add';
  var modalDeptId = null;
  var modalTableIdx = 0;
  var modalCourseIdx = null;
  var modalCourseId = null;
  var modalPlacements = {};
  var modalPlacementBase = {}; // semester to keep when toggling a dept on
  var modalInitSem = {}; // saved per-dept semester, restored when a dept is re-checked

  function semesterCount(dept) {
    var n = parseInt(dept.semesters || 1);
    return (n >= 1) ? n : 1;
  }

  function semesterOptionsFor(dept, selected) {
    var n = semesterCount(dept);
    var html = '';
    for (var s = 1; s <= n; s++) {
      html += '<option value="' + s + '"' + (s === selected ? ' selected' : '') + '>الفصل ' + s + '</option>';
    }
    return html;
  }

  function renderModalDeptGrid(checkMap) {
    var grid = document.getElementById('mDeptGrid');
    if (!grid) return;
    grid.innerHTML = '';
    checkMap = checkMap || {};
    departments.forEach(function (d) {
      var row = document.createElement('div');
      row.className = 'mdept-row border border-outline-variant rounded-xl p-2.5 transition-all ' + (checkMap[d.id] ? 'bg-primary/5 border-primary/30' : '');

      var main = document.createElement('label');
      main.className = 'flex items-center gap-2.5 cursor-pointer select-none';

      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.name = 'mDept[]';
      cb.value = String(d.id);
      cb.className = 'w-4 h-4 rounded border-outline-variant text-primary focus:ring-primary';
      cb.checked = !!checkMap[d.id];
      cb.onchange = function () {
        var rowEl = this.closest('.mdept-row');
        var wrap = rowEl.querySelector('.mdept-sem-wrap');
        var sel = rowEl.querySelector('.mdept-sem');
        if (this.checked) {
          rowEl.classList.add('bg-primary/5', 'border-primary/30');
          var stored = modalPlacements[d.id];
          var val = stored ? stored.semester : (modalInitSem[d.id] || semesterCount(d));
          sel.value = String(val);
          modalPlacements[d.id] = { department_id: d.id, semester: val };
          wrap.classList.remove('hidden');
          wrap.style.display = 'flex';
          sel.style.display = 'inline-flex';
        } else {
          rowEl.classList.remove('bg-primary/5', 'border-primary/30');
          var keep = parseInt(sel.value, 10);
          if (keep >= 1) modalInitSem[d.id] = keep;
          delete modalPlacements[d.id];
          wrap.classList.add('hidden');
          wrap.style.display = 'none';
          sel.style.display = 'none';
        }
      };

      var icon = document.createElement('span');
      icon.className = 'material-symbols-outlined text-primary text-[18px]';
      icon.textContent = d.icon || 'domain';

      var name = document.createElement('span');
      name.className = 'flex-1 text-sm font-semibold text-on-surface';
      name.textContent = d.name;

      main.appendChild(cb);
      main.appendChild(icon);
      main.appendChild(name);

      var semWrap = document.createElement('label');
      semWrap.className = 'mdept-sem-wrap flex items-center gap-2 mt-2' + (checkMap[d.id] ? '' : ' hidden');
      semWrap.style.display = checkMap[d.id] ? 'flex' : 'none';
      var semLabel = document.createElement('span');
      semLabel.className = 'text-xs text-on-surface-variant font-semibold';
      semLabel.textContent = 'الفصل الدراسي:';
      var semSel = document.createElement('select');
      semSel.className = 'mdept-sem w-auto min-w-[120px] bg-surface border border-outline-variant rounded-lg px-2 py-1 text-sm focus:ring-2 focus:ring-primary focus:border-primary outline-none';
      var cur = checkMap[d.id] ? checkMap[d.id].semester : semesterCount(d);
      semSel.innerHTML = semesterOptionsFor(d, cur);
      semSel.onchange = function () {
        modalPlacements[d.id] = {
          department_id: d.id,
          semester: parseInt(this.value)
        };
        modalInitSem[d.id] = parseInt(this.value);
      };

      semWrap.appendChild(semLabel);
      semWrap.appendChild(semSel);

      row.appendChild(main);
      row.appendChild(semWrap);
      grid.appendChild(row);
    });
  }

  function checkedDeptIds() {
    var ids = [];
    var boxes = document.querySelectorAll('#mDeptGrid input[name="mDept[]"]:checked');
    for (var i = 0; i < boxes.length; i++) {
      ids.push(parseInt(boxes[i].value));
    }
    return ids;
  }

  function collectPlacements() {
    var placements = [];
    var boxes = document.querySelectorAll('#mDeptGrid input[name="mDept[]"]:checked');
    for (var i = 0; i < boxes.length; i++) {
      var id = parseInt(boxes[i].value);
      var rowEl = boxes[i].closest('.mdept-row');
      var sel = rowEl ? rowEl.querySelector('.mdept-sem') : null;
      var sem = sel ? parseInt(sel.value) : 1;
      if (sem < 1) sem = 1;
      placements.push({ department_id: id, semester: sem });
    }
    return placements;
  }

  function primaryDept() {
    var ids = checkedDeptIds();
    if (!ids.length) return null;
    return deptById(ids[0]);
  }

  function fillPrereqOptions() {
    var sel = document.getElementById('mPrereq');
    if (!sel) return;
    sel.innerHTML = '<option value="">بدون متطلب سابق</option>';
    PREREQ_OPTIONS.forEach(function (o) {
      var opt = document.createElement('option');
      opt.value = o.id;
      opt.textContent = o.code + ' - ' + o.name;
      sel.appendChild(opt);
    });
  }

  var prereqTom = null;
  function initPrereqSelect() {
    var sel = document.getElementById('mPrereq');
    if (!sel) return;
    if (typeof TomSelect === 'undefined') {
      if (!window.__prereqRetries) window.__prereqRetries = 0;
      if (window.__prereqRetries < 12) {
        window.__prereqRetries++;
        setTimeout(initPrereqSelect, 500);
      }
      return;
    }
    if (prereqTom) return;
    prereqTom = new TomSelect(sel, {
      create: false,
      sortField: { field: 'text', direction: 'asc' },
      maxOptions: null,
      placeholder: sel.getAttribute('placeholder') || 'ابحث...'
    });
  }
  function prereqValue() {
    if (prereqTom) return prereqTom.getValue() || '';
    return document.getElementById('mPrereq').value;
  }
  function prereqSet(value) {
    if (prereqTom) { prereqTom.clear(); prereqTom.setValue(value ? String(value) : ''); }
    else { document.getElementById('mPrereq').value = value ? String(value) : ''; }
  }
  function syncUnitsFromHours() {
    var t = parseInt(document.getElementById('mTheory').value) || 0;
    var p = parseInt(document.getElementById('mPractical').value) || 0;
    document.getElementById('mTotal').value = t + p;
    document.getElementById('mUnits').value = t + p;
  }

  function showModal() { document.getElementById('courseModal').classList.remove('hidden'); }
  function closeModal() { document.getElementById('courseModal').classList.add('hidden'); }

  function openAddModalFromList() {
    var did = document.getElementById('listDeptFilter').value || (departments.length ? departments[0].id : '');
    openAddModal(parseInt(did), 0);
  }

  function openAddModal(deptId, tableIdx) {
    if (deptId != null && !deptById(deptId)) { alert('اختر قسماً أولاً'); return; }
    modalMode = 'add';
    modalDeptId = deptId;
    modalTableIdx = (tableIdx != null) ? tableIdx : 0;
    modalCourseIdx = null;
    modalCourseId = null;
    modalPlacements = {};
    modalPlacementBase = {};
    modalInitSem = {};
    var tIdx = modalTableIdx;
    var baseSem = 1;
    if (deptId != null) {
      var t = deptById(deptId);
      var tables = t ? t.tables : [];
      if (tables.length && tIdx < tables.length && tables[tIdx]) baseSem = tables[tIdx].semester || 1;
    }
    if (deptId != null) modalPlacementBase[deptId] = baseSem;
    document.getElementById('modalTitleText').textContent = 'إضافة مادة جديدة';
    document.getElementById('modalTitleIcon').textContent = 'add';
    document.getElementById('mCode').value = '';
    document.getElementById('mName').value = '';
    document.getElementById('mUnits').value = 3;
    document.getElementById('mTheory').value = '';
    document.getElementById('mPractical').value = '';
    document.getElementById('mTotal').value = 0;
    document.getElementById('mNotes').value = '';
    if (iconPicker) iconPicker.setValue('💻');
    prereqSet('');
    var checkMap = {};
    if (deptId != null) checkMap[deptId] = { semester: baseSem };
    Object.keys(checkMap).forEach(function (id) {
      modalInitSem[parseInt(id, 10)] = checkMap[id].semester;
    });
    renderModalDeptGrid(checkMap);
    showModal();
    document.getElementById('mCode').focus();
  }

  function openEditModal(deptId, tableIdx, courseIdx) {
    var dept = deptById(deptId);
    var c = dept.tables[tableIdx].courses[courseIdx];
    modalMode = 'edit';
    modalDeptId = deptId;
    modalTableIdx = tableIdx;
    modalCourseIdx = courseIdx;
    modalCourseId = c.id;
    modalPlacements = {};
    modalPlacementBase = {};
    modalInitSem = {};
    document.getElementById('modalTitleText').textContent = 'تعديل المادة';
    document.getElementById('modalTitleIcon').textContent = 'edit';
    document.getElementById('mCode').value = c.code;
    document.getElementById('mName').value = c.name;
    document.getElementById('mUnits').value = c.units;
    var h = courseHours(c);
    document.getElementById('mTheory').value = (h.theory || '');
    document.getElementById('mPractical').value = (h.practical || '');
    document.getElementById('mTotal').value = (h.theory || 0) + (h.practical || 0);
    document.getElementById('mNotes').value = c.notes || '';
    if (iconPicker) iconPicker.setValue(c.icon || '📖');
    var r = prereqOf(c);
    var rc = (Object.prototype.toString.call(r) === '[object Array]' ? (r[0] || '') : r);
    prereqSet(prereqIdByCode(rc));

    // Build per-department placements, preferring the loaded payload map.
    var pre = (COURSE_DEPT_MAP[c.id] || []).slice();
    if (pre.indexOf(deptId) === -1) pre.push(deptId);
    var saved = COURSE_DEPT_PLACEMENTS[c.id] || {};
    var checkMap = {};
    var activeSem = parseInt(c.semester) || 1;
    var tableSem = (dept.tables[tableIdx] && dept.tables[tableIdx].semester) || activeSem;
    pre.forEach(function (id) {
      var sem = saved[id] ? saved[id].semester : (id === deptId ? tableSem : semesterCount(deptById(id)));
      checkMap[id] = { semester: sem };
      if (id === deptId) modalPlacementBase[id] = tableSem;
      else modalPlacementBase[id] = semesterCount(deptById(id));
    });
    Object.keys(checkMap).forEach(function (id) {
      modalInitSem[parseInt(id, 10)] = checkMap[id].semester;
    });
    renderModalDeptGrid(checkMap);
    showModal();
  }

  function prereqIdByCode(code) {
    if (!code) return '';
    var found = '';
    PREREQ_OPTIONS.forEach(function (o) { if (o.code === code && !found) found = o.id; });
    return found;
  }

  function submitCourseForm(url, fields) {
    var form = document.createElement('form');
    form.method = 'POST';
    form.action = url;
    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    var csrf = csrfMeta ? csrfMeta.content : '';
    var csrfInput = document.createElement('input');
    csrfInput.type = 'hidden';
    csrfInput.name = '_csrf_token';
    csrfInput.value = csrf || '';
    form.appendChild(csrfInput);
    Object.keys(fields).forEach(function (k) {
      var val = fields[k];
      if (Array.isArray(val)) {
        val.forEach(function (v) {
          var inp = document.createElement('input');
          inp.type = 'hidden';
          inp.name = k;
          inp.value = String(v);
          form.appendChild(inp);
        });
      } else {
        var inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = k;
        inp.value = String(val == null ? '' : val);
        form.appendChild(inp);
      }
    });
    document.body.appendChild(form);
    form.submit();
  }

  function saveCourse() {
    var code = document.getElementById('mCode').value.trim();
    var name = document.getElementById('mName').value.trim();
    var theory = parseInt(document.getElementById('mTheory').value) || 0;
    var practical = parseInt(document.getElementById('mPractical').value) || 0;
    var unitsInput = document.getElementById('mUnits').value.trim();
    var units = unitsInput !== '' ? (parseInt(unitsInput) || 0) : (theory + practical);
    if (!code || !name || units <= 0) {
      alert('يرجى تعبئة رمز المادة واسم المادة والوحدات بشكل صحيح');
      return;
    }
    var placements = collectPlacements();
    if (!placements.length) { alert('اختر قسماً واحداً على الأقل'); return; }
    var primary = deptById(placements[0].department_id);
    var sem = placements[0].semester;
    var year = (primary && primary.semesters > 1) ? (sem - 1) : 1;
    var icon = iconPicker ? iconPicker.getValue() : '';
    var notes = document.getElementById('mNotes').value.trim();

    var fields = {
      'code': code,
      'name': name,
      'total_hours': String(units),
      'theoretical_hours': String(theory),
      'practical_hours': String(practical),
      'year': String(year),
      'semester': String(sem),
      'department_ids': placements.map(function (p) { return p.department_id; }),
      'dept_semester': placements.map(function (p) { return p.semester; }),
      'placements': JSON.stringify(placements),
      'prerequisite_id': prereqValue(),
      'icon': icon || '📖',
      'notes': notes
    };

    if (modalMode === 'add') {
      submitCourseForm(URLS.create, fields);
    } else {
      submitCourseForm(URLS.edit.replace('0', String(modalCourseId || '')), fields);
    }
  }

  function deleteCourse(deptId, tableIdx, courseIdx) {
    var dept = deptById(deptId);
    var c = dept.tables[tableIdx].courses[courseIdx];
    if (!confirm('هل أنت متأكد من حذف المادة "' + c.name + '" (' + c.code + ')؟')) return;
    submitCourseForm(URLS.delete.replace('0', c.id), {});
  }

  // ===== DETAILS DRAWER =====
  function openDetails(deptId, tableIdx, courseIdx) {
    var dept = deptById(deptId);
    var t = dept.tables[tableIdx];
    var c = t.courses[courseIdx];
    var h = courseHours(c);
    var prereq = prereqOf(c);

    var prereqHtml = '<div class="bg-surface-container rounded-lg p-3"><div class="flex items-center gap-2 mb-1">' +
      '<span class="material-symbols-outlined text-primary text-lg">link</span><span class="text-xs text-gray-500">المتطلب السابق</span></div>';
    if (!prereq || (prereq.length === 0)) {
      prereqHtml += '<div class="text-sm font-semibold text-gray-900">—</div>';
    } else {
      var codes = Object.prototype.toString.call(prereq) === '[object Array]' ? prereq : [prereq];
      prereqHtml += '<div class="flex flex-wrap gap-1.5">';
      codes.forEach(function (x) {
        var nm = prereqName(x);
        prereqHtml += '<span class="inline-flex items-center gap-1.5 font-mono text-xs font-bold text-primary bg-primary-faint px-2 py-1 rounded border border-primary/20">' +
          '<span class="material-symbols-outlined text-[14px]">arrow_back</span>' + esc(x) + '</span>' +
          (nm ? '<span class="text-xs text-gray-600 mt-1">' + esc(nm) + '</span>' : '');
      });
      prereqHtml += '</div>';
    }
    prereqHtml += '</div>';

    document.getElementById('drawerContent').innerHTML =
      '<div class="bg-primary/5 rounded-xl p-4">' +
        '<div class="flex items-center justify-between">' +
          '<span class="font-mono font-bold text-primary text-sm">' + esc(c.code) + '</span>' +
          '<span class="text-xs font-bold text-primary bg-white px-2 py-0.5 rounded-full border border-primary/20">' + (c.units || 0) + ' وحدات</span>' +
        '</div>' +
        '<div class="text-lg font-bold text-gray-900 mt-2 flex items-center gap-2">' +
          '<span class="text-2xl">' + esc(c.icon || '📖') + '</span>' +
          '<span>' + esc(c.name) + '</span>' +
        '</div>' +
      '</div>' +
      '<div class="grid grid-cols-2 gap-4">' +
        '<div class="bg-surface-container rounded-lg p-3">' +
          '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-lg">domain</span><span class="text-xs text-gray-500">القسم</span></div>' +
          '<div class="text-sm font-semibold text-gray-900">' + esc(dept.name) + '</div>' +
        '</div>' +
        '<div class="bg-surface-container rounded-lg p-3">' +
          '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-lg">today</span><span class="text-xs text-gray-500">الفصل الدراسي</span></div>' +
          '<div class="text-sm font-semibold text-gray-900">' + esc(t.title) + '</div>' +
        '</div>' +
        '<div class="bg-surface-container rounded-lg p-3">' +
          '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-lg">schedule</span><span class="text-xs text-gray-500">نظري</span></div>' +
          '<div class="text-sm font-semibold text-gray-900">' + h.theory + ' ساعات</div>' +
        '</div>' +
        '<div class="bg-surface-container rounded-lg p-3">' +
          '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-lg">build</span><span class="text-xs text-gray-500">عملي</span></div>' +
          '<div class="text-sm font-semibold text-gray-900">' + h.practical + ' ساعات</div>' +
        '</div>' +
        '<div class="bg-surface-container rounded-lg p-3">' +
          '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-lg">timer</span><span class="text-xs text-gray-500">إجمالي الساعات</span></div>' +
          '<div class="text-sm font-semibold text-gray-900">' + h.hours + ' ساعات</div>' +
        '</div>' +
        '<div class="bg-surface-container rounded-lg p-3">' +
          '<div class="flex items-center gap-2 mb-1"><span class="material-symbols-outlined text-primary text-lg">school</span><span class="text-xs text-gray-500">الوحدات</span></div>' +
          '<div class="text-sm font-semibold text-gray-900">' + (c.units || 0) + ' وحدة</div>' +
        '</div>' +
      '</div>' +
      '<div class="bg-surface-container rounded-lg p-3">' +
        '<div class="flex items-center gap-2 mb-2"><span class="material-symbols-outlined text-primary text-lg">folder</span><span class="text-xs text-gray-500">ملفات المقرر</span></div>' +
        '<div class="flex flex-wrap gap-1.5">' + (contentBtns(c) || '<span class="text-xs text-gray-500">لا توجد ملفات منشورة لهذا المقرر</span>') + '</div>' +
      '</div>' +
      prereqHtml;

    document.getElementById('drawerOverlay').classList.remove('hidden');
    document.getElementById('drawerPanel').classList.add('open');
  }

  function closeDrawer() {
    document.getElementById('drawerOverlay').classList.add('hidden');
    document.getElementById('drawerPanel').classList.remove('open');
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeDrawer(); closeModal(); }
  });

  // ===== DRAG & DROP (same department only) =====
  var draggedCourse = null;

  function dragStartCourse(e) {
    if (!CAN_MANAGE) { e.preventDefault(); return; }
    var row = e.currentTarget;
    draggedCourse = {
      courseId: parseInt(row.getAttribute('data-course-id')),
      deptId: parseInt(row.getAttribute('data-dept-id')),
      semester: parseInt(row.getAttribute('data-semester'))
    };
    row.classList.add('opacity-50');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(draggedCourse.courseId));
  }

  function dragEndCourse(e) {
    e.currentTarget.classList.remove('opacity-50');
    draggedCourse = null;
  }

  function dragOverZone(e) {
    if (!draggedCourse) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    e.currentTarget.classList.add('ring-2', 'ring-primary', 'bg-primary-faint');
  }

  function dragLeaveZone(e) {
    e.currentTarget.classList.remove('ring-2', 'ring-primary', 'bg-primary-faint');
  }

  function dropCourse(e) {
    e.preventDefault();
    e.currentTarget.classList.remove('ring-2', 'ring-primary', 'bg-primary-faint');
    if (!draggedCourse) return;

    var targetDeptId = parseInt(e.currentTarget.getAttribute('data-dept-id'));
    var targetSemester = parseInt(e.currentTarget.getAttribute('data-semester'));

    // Same department only — cross-department drops are rejected.
    if (targetDeptId !== draggedCourse.deptId) {
      alert('لا يمكن نقل المادة إلى قسم آخر');
      return;
    }
    if (targetSemester === draggedCourse.semester) return;

    moveCourse(draggedCourse.courseId, targetDeptId, targetSemester);
  }

  function applyLocalMove(courseId, deptId, semester) {
    var moved = false;
    // Move only within the target department — the course keeps its
    // (possibly different) semester in other departments.
    var d = deptById(deptId);
    if (!d) return false;
    var isGeneral = Number(d.semesters) <= 1;
    var targetSem = isGeneral ? 1 : semester;
    d.tables.forEach(function (t) {
      for (var i = 0; i < t.courses.length; i++) {
        if (t.courses[i].id !== courseId) continue;
        var course = t.courses[i];
        t.courses.splice(i, 1);
        var target = null;
        for (var j = 0; j < d.tables.length; j++) {
          if (d.tables[j].semester === targetSem) { target = d.tables[j]; break; }
        }
        if (!target) {
          target = { semester: targetSem, title: 'الفصل ' + targetSem, courses: [] };
          d.tables.push(target);
          d.tables.sort(function (a, b) { return a.semester - b.semester; });
        }
        course.semester = targetSem;
        target.courses.push(course);
        moved = true;
        break;
      }
    });
    return moved;
  }

  function moveCourse(courseId, deptId, semester) {
    var csrf = document.querySelector('meta[name="csrf-token"]').content;
    fetch(URLS.move, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({ course_id: courseId, department_id: deptId, semester: semester })
    })
    .then(function (r) { return r.json(); })
    .then(function (res) {
      if (res.ok) {
        applyLocalMove(courseId, deptId, semester);
        renderPlan();
        renderList();
      } else {
        alert(res.message || 'تعذر نقل المادة');
      }
    })
    .catch(function () { alert('تعذر الاتصال بالخادم'); });
  }

  // ===== BULK MOVE (checkbox-based) =====
  function onCourseCheck() {
    updateBulkBar();
    document.querySelectorAll('.ws-select-all').forEach(function (cb) {
      var sem = parseInt(cb.getAttribute('data-semester'), 10);
      var all = document.querySelectorAll('.ws-course-cb[data-semester="' + sem + '"]');
      var checked = document.querySelectorAll('.ws-course-cb[data-semester="' + sem + '"]:checked');
      cb.checked = all.length > 0 && all.length === checked.length;
      cb.indeterminate = checked.length > 0 && checked.length < all.length;
    });
    updatePlanHeaderDeleteBtns();
  }

  function toggleSelectAll(cb) {
    var sem = parseInt(cb.getAttribute('data-semester'), 10);
    document.querySelectorAll('.ws-course-cb[data-semester="' + sem + '"]').forEach(function (c) {
      c.checked = cb.checked;
    });
    updateBulkBar();
    updatePlanHeaderDeleteBtns();
  }

  function updatePlanHeaderDeleteBtns() {
    document.querySelectorAll('.ws-header-delete').forEach(function (btn) {
      var sem = parseInt(btn.getAttribute('data-semester'), 10);
      var checked = document.querySelectorAll('.ws-course-cb[data-semester="' + sem + '"]:checked');
      btn.style.display = checked.length > 0 ? 'inline-flex' : 'none';
    });
  }

  function executePlanBulkDelete() {
    var cbs = Array.prototype.slice.call(document.querySelectorAll('.ws-course-cb:checked'));
    if (!cbs.length) return;
    if (!confirm('حذف المقررات المحددة؟')) return;
    var ids = [];
    var seen = {};
    cbs.forEach(function (cb) {
      var id = cb.getAttribute('data-course-id');
      if (!seen[id]) { seen[id] = true; ids.push(id); }
    });
    var csrf = document.querySelector('meta[name="csrf-token"]');
    var form = document.createElement('form');
    form.method = 'POST';
    form.action = URLS.bulkDelete;
    var c = document.createElement('input');
    c.type = 'hidden';
    c.name = '_csrf_token';
    c.value = csrf ? csrf.content : '';
    form.appendChild(c);
    function addHidden(name, value) {
      var h = document.createElement('input');
      h.type = 'hidden';
      h.name = name;
      h.value = value;
      form.appendChild(h);
    }
    addHidden('view', activeView);
    addHidden('page', currentPage);
    ids.forEach(function (id) {
      addHidden('course_ids', id);
    });
    document.body.appendChild(form);
    form.submit();
  }

  function updateBulkBar() {
    var bar = document.getElementById('bulkMoveBar');
    if (!bar) return;
    var checked = document.querySelectorAll('.ws-course-cb:checked');
    var count = checked.length;
    document.getElementById('bulkCount').textContent = count + ' مقرر محدد';
    bar.classList.toggle('hidden', count === 0);

    var dept = deptById(currentDeptId);
    var semSel = document.getElementById('bulkTargetSem');
    semSel.innerHTML = '<option value="">اختر الفصل الهدف…</option>';
    if (dept) {
      var currentSems = [];
      checked.forEach(function (cb) {
        var s = parseInt(cb.getAttribute('data-semester'), 10);
        if (currentSems.indexOf(s) === -1) currentSems.push(s);
      });
      dept.tables.forEach(function (t) {
        if (currentSems.indexOf(t.semester) === -1) {
          var opt = document.createElement('option');
          opt.value = t.semester;
          opt.textContent = t.title;
          semSel.appendChild(opt);
        }
      });
    }
  }

  function executeBulkMove() {
    var semSel = document.getElementById('bulkTargetSem');
    var targetSem = parseInt(semSel.value, 10);
    if (!targetSem) { alert('يرجى اختيار الفصل الهدف'); return; }
    var checked = document.querySelectorAll('.ws-course-cb:checked');
    if (!checked.length) return;
    var items = [];
    checked.forEach(function (cb) {
      items.push({
        courseId: parseInt(cb.getAttribute('data-course-id'), 10),
        deptId: parseInt(cb.getAttribute('data-dept-id'), 10)
      });
    });
    if (!items.length) return;
    var deptId = items[0].deptId;
    var csrf = document.querySelector('meta[name="csrf-token"]').content;
    var done = 0;
    var errors = [];
    var total = items.length;
    items.forEach(function (item) {
      fetch(URLS.move, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ course_id: item.courseId, department_id: item.deptId, semester: targetSem })
      })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (res.ok) {
          applyLocalMove(item.courseId, item.deptId, targetSem);
        } else {
          errors.push(res.message || 'تعذر نقل مقرر');
        }
        done++;
        if (done === total) {
          clearSelection();
          renderPlan();
          renderList();
          if (errors.length) alert('تعذر نقل ' + errors.length + ' من ' + total + ' مقرر:\n' + errors.join('\n'));
        }
      })
      .catch(function () {
        errors.push('تعذر الاتصال بالخادم');
        done++;
        if (done === total) {
          clearSelection();
          renderPlan();
          renderList();
          if (errors.length) alert(errors.join('\n'));
        }
      });
    });
  }

  function clearSelection() {
    document.querySelectorAll('.ws-course-cb:checked, .ws-select-all:checked').forEach(function (cb) {
      cb.checked = false;
      cb.indeterminate = false;
    });
    updateBulkBar();
    updatePlanHeaderDeleteBtns();
  }

  // ===== BULK DELETE (list view) =====
  function onCourseDeleteCheck() {
    updateCourseDeleteHeader();
  }

  function updateCourseDeleteHeader() {
    var cbs = Array.prototype.slice.call(document.querySelectorAll('.course-delete-cb'));
    var selectAll = document.getElementById('courseSelectAll');
    var deleteBtn = document.getElementById('courseHeaderDeleteBtn');
    var selected = cbs.filter(function (cb) { return cb.checked; }).length;
    if (selectAll) {
      selectAll.checked = cbs.length > 0 && selected === cbs.length;
      selectAll.indeterminate = selected > 0 && selected < cbs.length;
    }
    if (deleteBtn) deleteBtn.style.display = selected > 0 ? 'inline-flex' : 'none';
  }

  function executeCourseBulkDelete() {
    var cbs = Array.prototype.slice.call(document.querySelectorAll('.course-delete-cb:checked'));
    if (!cbs.length) return;
    if (!confirm('حذف المقررات المحددة؟')) return;
    var ids = cbs.map(function (cb) { return cb.value; });
    var csrf = document.querySelector('meta[name="csrf-token"]');
    var form = document.createElement('form');
    form.method = 'POST';
    form.action = URLS.bulkDelete;
    var c = document.createElement('input');
    c.type = 'hidden';
    c.name = '_csrf_token';
    c.value = csrf ? csrf.content : '';
    form.appendChild(c);
    var vh = document.createElement('input');
    vh.type = 'hidden';
    vh.name = 'view';
    vh.value = activeView;
    form.appendChild(vh);
    var ph = document.createElement('input');
    ph.type = 'hidden';
    ph.name = 'page';
    ph.value = currentPage;
    form.appendChild(ph);
    ids.forEach(function (id) {
      var inp = document.createElement('input');
      inp.type = 'hidden';
      inp.name = 'course_ids';
      inp.value = id;
      form.appendChild(inp);
    });
    document.body.appendChild(form);
    form.submit();
  }

  function toggleCourseSelectAll(cb) {
    document.querySelectorAll('.course-delete-cb').forEach(function (c) { c.checked = cb.checked; });
    updateCourseDeleteHeader();
  }

  // ===== RENDER ALL =====
  function renderAll() {
    if (activeView === 'list') {
      renderList();
    } else if (activeView === 'plan') {
      renderDeptGrid(departments.filter(function (d) { return !planSearchQuery() || d.name.indexOf(planSearchQuery()) !== -1; }));
      renderPlan();
    }
  }

  // ===== EXPOSE GLOBAL HANDLERS =====
  // قبل INIT لضمان عمل أزرار الإضافة/التعديل/الحذف حتى لو فشلت خطوة تهيئة لاحقة
  window.switchView = switchView;
  window.goPage = goPage;
  window.selectDept = selectDept;
  window.openAddModalFromList = openAddModalFromList;
  window.openAddModal = openAddModal;
  window.openEditModal = openEditModal;
  window.openDetails = openDetails;
  window.saveCourse = saveCourse;
  window.deleteCourse = deleteCourse;
  window.closeModal = closeModal;
  window.closeDrawer = closeDrawer;
  window.dragStartCourse = dragStartCourse;
  window.dragEndCourse = dragEndCourse;
  window.dragOverZone = dragOverZone;
  window.dragLeaveZone = dragLeaveZone;
  window.dropCourse = dropCourse;
  window.onCourseCheck = onCourseCheck;
  window.toggleSelectAll = toggleSelectAll;
  window.onCourseDeleteCheck = onCourseDeleteCheck;
  window.toggleCourseSelectAll = toggleCourseSelectAll;
  window.executeCourseBulkDelete = executeCourseBulkDelete;
  window.executePlanBulkDelete = executePlanBulkDelete;

  // ===== EVENTS + INIT (view) =====
  // عرض القائمة والخطة لا يعتمد على المودال: أي فشل فيه لا يوقف عرض الجدول.
  try {
    document.getElementById('listSearch').addEventListener('input', function () { currentPage = 1; renderList(); });
    document.getElementById('listDeptFilter').addEventListener('change', function () { currentPage = 1; renderList(); });

    var courseSelectAll = document.getElementById('courseSelectAll');
    if (courseSelectAll) {
      courseSelectAll.addEventListener('change', function () { toggleCourseSelectAll(courseSelectAll); });
    }
    var courseHeaderDeleteBtn = document.getElementById('courseHeaderDeleteBtn');
    if (courseHeaderDeleteBtn) {
      courseHeaderDeleteBtn.addEventListener('click', executeCourseBulkDelete);
    }
    document.addEventListener('click', function (e) {
      var t = e.target;
      if (t && t.classList && t.classList.contains('ws-header-delete')) {
        executePlanBulkDelete();
      }
    });
    document.getElementById('planSearch').addEventListener('input', function () {
      renderDeptGrid(departments.filter(function (d) { return !planSearchQuery() || d.name.indexOf(planSearchQuery()) !== -1; }));
    });
    document.getElementById('planDeptSelect').addEventListener('change', function () {
      selectDept(parseInt(this.value), false);
    });

    // ===== INIT =====
    fillSelects();
    if (departments.length) {
      currentDeptId = departments[0].id;
      document.getElementById('planDeptSelect').value = currentDeptId;
    }
    renderDeptGrid(departments);
    switchView(activeView);
  } catch (e) {
    window.__listInitError = String(e && e.message ? e.message : e);
  }

  // ===== INIT (modal) =====
  // إعداد المودال مستقل عن عرض القائمة حتى لا يعطّله أي خطأ في ترتيب العناصر.
  try {
    fillPrereqOptions();
    var mTheory = document.getElementById('mTheory');
    var mPractical = document.getElementById('mPractical');
    if (mTheory) mTheory.addEventListener('input', syncUnitsFromHours);
    if (mPractical) mPractical.addEventListener('input', syncUnitsFromHours);
  } catch (e) {
    window.__modalInitError = String(e && e.message ? e.message : e);
  }

  // يبدأ Tom Select بعد تحميل سكربت CDN في base.html
  window.addEventListener('load', initPrereqSelect);
})();
