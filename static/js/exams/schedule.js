/**
 * Schedule — exam matrix (design: days × semesters).
 *
 * Rows are exam days (السبت…الخميس) with their concrete dates, columns are the
 * department semesters.  The data itself comes from the head of department:
 * only a scoped head_of_department can add/edit/delete exams here — every
 * other role renders the submitted schedule read-only.  Weeks are independent
 * tabs (1–5) — every exam stores its week number.
 */
(function () {
  'use strict';

  var MAX_WEEKS = 5;
  var WEEK_ORDINALS = ['الأول', 'الثاني', 'الثالث', 'الرابع', 'الخامس'];
  var DAYS_ORDER = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس'];

  var AR_MONTHS = {
    '01': 'يناير', '02': 'فبراير', '03': 'مارس', '04': 'أبريل',
    '05': 'مايو', '06': 'يونيو', '07': 'يوليو', '08': 'أغسطس',
    '09': 'سبتمبر', '10': 'أكتوبر', '11': 'نوفمبر', '12': 'ديسمبر'
  };

  var EXAM_TYPES = {
    written:   { label: 'تحريري', border: '#10b981' },
    practical: { label: 'عملي',   border: '#3b82f6' },
    lab:       { label: 'معمل',   border: '#a855f7' },
    field:     { label: 'ميداني', border: '#f97316' }
  };
  var TYPE_ORDER = ['written', 'practical', 'lab', 'field'];

  var stateHolder = {
    deptId: null, deptKey: null, name: '', week: null,
    dept: null, period: null,
    semesterExamStart: '', semesterExamEnd: ''
  };

  function esc(s) { return window.ExamEsc ? window.ExamEsc(s) : String(s == null ? '' : s); }
  function weekLabel(w) { return 'الأسبوع ' + (WEEK_ORDINALS[w - 1] || w); }
  function normDay(d) { return String(d || '').replace('الإثنين', 'الاثنين'); }

  /** "2025-12-09" → "9 ديسمبر" */
  function dateChip(dateStr) {
    var p = String(dateStr || '').split('-');
    if (p.length < 3) return '';
    var m = AR_MONTHS[p[1]];
    return m ? (parseInt(p[2], 10) + ' ' + m) : '';
  }

  function render(panel, data, opts) {
    opts = opts || {};
    var DEPTS = data.departments || [];
    var role = opts.role || '';
    // Rendering page: exams are entered by the head of department only.
    var canEdit = role === 'head_of_department';
    var scoped = !!opts.scoped;

    var switchers = document.getElementById('exam-controls') || document.getElementById('exam-switchers');
    var deptTabsEl = document.getElementById('exam-dept-tabs');
    var weekTabsEl = document.getElementById('exam-week-tabs');
    var titleEl = document.getElementById('exam-matrix-title');

    function setSwitchersVisible(v) {
      if (!switchers) return;
      if (v) switchers.classList.remove('hidden');
      else switchers.classList.add('hidden');
    }

    if (!DEPTS.length) {
      setSwitchersVisible(false);
      panel.innerHTML =
        '<div class="bg-surface-container-lowest rounded-2xl p-lg ambient-shadow border border-outline-variant py-16 text-center">' +
        '<span class="material-symbols-outlined block text-[40px] text-gray-300 mb-2">grading</span>' +
        '<p class="text-on-surface-variant font-bold">لا توجد بيانات امتحانات لعرضها</p>' +
        '<p class="text-sm text-on-surface-variant mt-1">' +
        (canEdit ? 'أضف امتحانات من جدول قسمك لتظهر هنا.' : 'ستظهر الامتحانات هنا بعد إدخالها من رؤساء الأقسام.') +
        '</p>' +
        '</div>';
      return;
    }

    // Order departments so the general department (القسم العام) is shown last —
    // the exam department should land on a real academic department by default.
    var deptOrder = DEPTS.slice().sort(function (a, b) {
      return (a.isGeneral ? 1 : 0) - (b.isGeneral ? 1 : 0);
    });
    var currentDeptKey = opts.deptKey || null;
    if (!currentDeptKey) {
      for (var i = 0; i < deptOrder.length; i++) {
        if (!deptOrder[i].isGeneral) { currentDeptKey = deptOrder[i].key; break; }
      }
      if (!currentDeptKey && deptOrder.length) currentDeptKey = deptOrder[0].key;
    }
    var currentWeek = opts.week || null;
    var weeksByDept = {};
    var examById = {};

    function getDept() {
      for (var i = 0; i < DEPTS.length; i++) if (DEPTS[i].key === currentDeptKey) return DEPTS[i];
      return DEPTS[0];
    }

    function getWeeks(dept) {
      if (!weeksByDept[dept.key]) {
        weeksByDept[dept.key] = (dept.weeks && dept.weeks.length) ? dept.weeks.slice() : [1];
      }
      return weeksByDept[dept.key];
    }

    // ── Static shell: A4 card + matrix container + legend ──
    panel.innerHTML =
      '<div class="ws-a4 bg-surface-container-lowest rounded-xl p-lg ambient-shadow border border-outline-variant mx-auto max-w-full overflow-hidden flex flex-col">' +
        '<div class="matrix-container overflow-x-auto pb-2"><div class="matrix-grid min-w-[900px]"></div></div>' +
        '<div class="mt-6 pt-4 border-t border-outline-variant flex flex-wrap gap-6 text-body-md text-on-surface font-medium">' +
          TYPE_ORDER.map(function (k) {
            return '<span class="flex items-center gap-2">' +
              '<span class="w-4 h-4 rounded-sm shadow-sm" style="background:' + EXAM_TYPES[k].border + '"></span>' +
              '<span>' + EXAM_TYPES[k].label + '</span></span>';
          }).join('') +
        '</div>' +
      '</div>';

    var grid = panel.querySelector('.matrix-grid');

    // ── Exam card inside a matrix cell ──
    function renderCard(exam, sem, day) {
      examById[exam.id] = { exam: exam, semester: sem, day: day };
      var t = EXAM_TYPES[exam.type] || EXAM_TYPES.written;
      return '<div class="mx-card" style="border-right:4px solid ' + t.border + '"' +
        (canEdit ? ' data-clickable="1" title="تعديل الامتحان"' : '') +
        ' data-schedule-id="' + esc(exam.id) + '" data-day="' + esc(day) + '" data-sem="' + sem + '">' +
          '<div class="font-bold text-on-surface text-[15px] mb-1 truncate" title="' + esc(exam.course) + '">' + esc(exam.course || '—') + '</div>' +
          '<div><span style="display:inline-block;direction:ltr;background:#eef1f5;color:#3f3a46;border:1px solid #d9dfe7;border-radius:4px;padding:2px 6px;font-size:12px;font-weight:500;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;">' + esc(exam.code || '—') + '</span></div>' +
          '<div class="mt-auto pt-2 flex flex-col gap-1 text-xs text-on-surface-variant border-t border-outline-variant/30">' +
            (exam.hall ? '<span class="flex items-center gap-1"><span class="material-symbols-outlined text-[16px]" style="color:var(--color-primary,#320058)">meeting_room</span>' + esc(exam.hall) + '</span>' : '') +
            (exam.time ? '<span class="flex items-center gap-1"><span class="material-symbols-outlined text-[16px]" style="color:var(--color-primary,#320058)">schedule</span><span dir="ltr">' + esc(exam.time) + '</span></span>' : '') +
          '</div>' +
        '</div>';
    }

    // ── Matrix grid ──
    function renderTable() {
      var dept = getDept();
      var week = currentWeek;
      var semLabels = dept.semesterLabels;
      var all = dept.exams.filter(function (e) { return e.week === week; });

      var days = [];
      var deptDays = dept.days || [];
      DAYS_ORDER.forEach(function (d) {
        for (var i = 0; i < deptDays.length; i++) {
          if (normDay(deptDays[i]) === d) { days.push(d); break; }
        }
      });
      if (!days.length) days = DAYS_ORDER.slice();

      grid.style.setProperty('--matrix-cols', String(semLabels.length));

      var html = '<div class="matrix-header day-col">اليوم / الفصل</div>';
      semLabels.forEach(function (s) { html += '<div class="matrix-header">' + esc(s) + '</div>'; });

      days.forEach(function (day) {
        var dayExams = all.filter(function (e) { return normDay(e.day) === day; });
        var dayDate = (dept.dateMap && dept.dateMap[String(week)] && dept.dateMap[String(week)][day]) || '';
        var chip = dateChip(dayDate);
        html += '<div class="matrix-row-header">' +
          '<span class="text-lg text-on-surface">' + esc(day) + '</span>' +
          (chip ? '<span class="matrix-date-chip">' + esc(chip) + '</span>' : '') +
        '</div>';

        semLabels.forEach(function (s, si) {
          var sem = dept.semStart + si;
          var semExams = dayExams.filter(function (e) { return e.semester === sem; });
          if (!semExams.length) {
            if (canEdit) {
              html += '<div class="matrix-cell items-center justify-center">' +
                '<button type="button" class="mx-add no-print" data-add-day="' + esc(day) + '" data-add-sem="' + sem + '" ' +
                'title="إضافة امتحان في ' + esc(day) + ' — ' + esc(s) + '">' +
                '<span class="material-symbols-outlined text-[20px]">add</span></button></div>';
            } else {
              html += '<div class="matrix-cell"></div>';
            }
            return;
          }
          html += '<div class="matrix-cell">' + renderCard(semExams[0], sem, day) + '</div>';
        });
      });

      grid.innerHTML = html;
    }

    // ── Week tabs (gray pill, active tab is white) ──
    function renderWeekTabs() {
      if (!weekTabsEl) return;
      var dept = getDept();
      var ws = getWeeks(dept);
      if (currentWeek === null || ws.indexOf(currentWeek) === -1) currentWeek = ws[0];
      var html = '';
      ws.forEach(function (w) {
        var active = w === currentWeek;
        html += '<button type="button" data-week="' + w + '" class="px-4 py-1.5 rounded font-bold transition-colors whitespace-nowrap ' +
          (active ? 'bg-surface-container-lowest shadow-sm text-primary' : 'text-on-surface-variant hover:text-on-surface') +
          '">' + weekLabel(w) + '</button>';
      });
      var maxW = Math.max.apply(null, ws);
      if (maxW < MAX_WEEKS && canEdit) {
        html += '<button type="button" id="exam-week-add" class="px-3 py-1.5 rounded text-on-surface-variant hover:text-primary transition-colors flex items-center gap-1">' +
          '<span class="material-symbols-outlined text-[16px]">add</span><span class="text-xs font-bold">أسبوع</span></button>';
      }
      weekTabsEl.innerHTML = html;
      weekTabsEl.querySelectorAll('[data-week]').forEach(function (b) {
        b.addEventListener('click', function () {
          currentWeek = parseInt(b.getAttribute('data-week'), 10);
          renderAll();
        });
      });
      var addBtn = weekTabsEl.querySelector('#exam-week-add');
      if (addBtn) addBtn.addEventListener('click', function () {
        ws.push(maxW + 1);
        currentWeek = maxW + 1;
        renderAll();
      });

      var showPill = ws.length > 1 || maxW < MAX_WEEKS;
      weekTabsEl.style.display = showPill ? '' : 'none';
    }

    // ── Department tabs ──
    function renderDeptTabs() {
      if (!deptTabsEl) return;
      var showDeptTabs = !scoped && deptOrder.length > 1;
      if (!showDeptTabs) { deptTabsEl.style.display = 'none'; return; }
      deptTabsEl.style.display = '';
      deptTabsEl.innerHTML = deptOrder.map(function (d) {
        var active = d.key === currentDeptKey;
        return '<button type="button" data-dept-key="' + esc(d.key) + '" class="px-5 py-2 rounded-lg font-bold whitespace-nowrap transition-colors ' +
          (active ? 'bg-primary text-on-primary shadow-sm' : 'border border-outline-variant text-on-surface-variant hover:bg-surface-container hover:text-on-surface bg-surface') +
          '">' + esc(d.name) + '</button>';
      }).join('');
      deptTabsEl.querySelectorAll('[data-dept-key]').forEach(function (b) {
        b.addEventListener('click', function () {
          currentDeptKey = b.getAttribute('data-dept-key');
          var ws = getWeeks(getDept());
          if (ws.indexOf(currentWeek) === -1) currentWeek = ws[0];
          renderAll();
        });
      });
    }

    function updateTitle() {
      if (!titleEl) return;
      var dept = getDept();
      titleEl.textContent = 'جدول الامتحانات — ' + dept.name + ' — ' + weekLabel(currentWeek);
    }

    function renderAll() {
      renderWeekTabs();
      renderDeptTabs();
      updateTitle();
      renderTable();
      var deptTabsShown = deptTabsEl && deptTabsEl.style.display !== 'none';
      var pillShown = weekTabsEl && weekTabsEl.style.display !== 'none';
      setSwitchersVisible(!!(deptTabsShown || pillShown));
      var cur = getDept();
      stateHolder.deptId = cur ? cur.id : null;
      stateHolder.deptKey = cur ? cur.key : null;
      stateHolder.name = cur ? cur.name : '';
      stateHolder.week = currentWeek;
      stateHolder.dept = cur || null;
      stateHolder.period = data.period || null;
      stateHolder.semesterExamStart = data.semesterExamStart || '';
      stateHolder.semesterExamEnd = data.semesterExamEnd || '';
    }

    // ── CSV export (current week) ──
    var csvBtn = document.getElementById('ws-csv') || panel.querySelector('.ws-csv');
    if (csvBtn) csvBtn.addEventListener('click', function () {
      var dept = getDept();
      var exams = dept.exams.filter(function (e) { return e.week === currentWeek; });
      var csv = '\uFEFFاليوم,المقرر,الرمز,النوع,الوقت,القاعة,الفصل\n';
      exams.forEach(function (e) {
        var typeLabel = EXAM_TYPES[e.type] ? EXAM_TYPES[e.type].label : (e.type || '');
        csv += e.day + ',' + (e.course || '') + ',' + (e.code || '') + ',' + typeLabel + ',' +
               (e.time || '') + ',' + (e.hall || '') + ',' + e.semester + '\n';
      });
      var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'exam_schedule_' + dept.key + '_week' + currentWeek + '.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    });

    // ── Cell clicks: open edit / add modals (HOD only) ──
    panel.addEventListener('click', function (ev) {
      if (!canEdit) return;
      var card = ev.target.closest ? ev.target.closest('[data-schedule-id]') : null;
      if (card) {
        if (!card.getAttribute('data-clickable')) return;
        openExamModal(parseInt(card.getAttribute('data-sem'), 10), card.getAttribute('data-day'), card.getAttribute('data-schedule-id'));
        return;
      }
      var addCell = ev.target.closest ? ev.target.closest('[data-add-day]') : null;
      if (addCell) {
        openExamModal(parseInt(addCell.getAttribute('data-add-sem'), 10), addCell.getAttribute('data-add-day'), null);
      }
    });

    // ── Modal: add/edit exam (course, room, start, end) ──
    var modal = null;

    function timeOptions() {
      var startT = data.period && data.period.startTime ? data.period.startTime : '09:00';
      var endT = data.period && data.period.endTime ? data.period.endTime : '17:00';
      var opts = [];
      var cur = startT;
      while (cur <= endT) {
        opts.push(cur);
        var parts = cur.split(':');
        var h = parseInt(parts[0], 10);
        var m = parseInt(parts[1], 10) || 0;
        m += 60;
        h += Math.floor(m / 60);
        m = m % 60;
        cur = (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
      }
      return opts;
    }

    function closeModal() {
      if (modal) {
        modal.remove();
        modal = null;
        var bd = document.querySelector('body');
        if (bd) bd.style.overflow = '';
      }
    }

    function reloadTable() {
      var dept = getDept();
      window.ExamSchedule.init(panel, { role: role, scoped: scoped, week: currentWeek, deptKey: dept.key });
    }

    function openExamModal(semester, day, scheduleId) {
      var dept = getDept();
      var existing = scheduleId ? (examById[scheduleId] || null) : null;
      var url = '/api/exams/department-schedule/cell-options?dept_id=' + encodeURIComponent(dept.id) + '&semester=' + encodeURIComponent(semester);
      window.Exams.api.get(url).then(function (opt) {
        buildExamModal(dept, semester, day, existing, opt);
      }).catch(function (err) {
        window.ExamToast(err.message, true);
      });
    }

    function buildExamModal(dept, semester, day, existing, opt) {
      closeModal();
      var courses = opt.courses || [];
      var rooms = opt.rooms || [];
      var times = timeOptions();

      var isEdit = !!existing;
      var selectedCourse = existing ? existing.exam.course_id : (courses.length ? courses[0].id : '');
      var selectedRoom = existing ? existing.exam.room_id : (rooms.length ? rooms[0].id : '');
      var defaultStart = existing && existing.exam.start_time ? existing.exam.start_time
        : (data.period && data.period.startTime ? data.period.startTime : '09:00');
      var defaultEnd = existing && existing.exam.end_time ? existing.exam.end_time : (times[1] || times[0]);

      modal = document.createElement('div');
      modal.className = 'ws-modal-overlay';
      modal.innerHTML =
        '<div class="ws-modal-card bg-surface-container-lowest rounded-2xl p-lg ambient-shadow border border-outline-variant w-full max-w-md" style="max-height:92vh;overflow-y:auto;">' +
          '<div class="flex items-center justify-between mb-md">' +
            '<div>' +
              '<h3 class="text-headline-md font-bold text-on-surface">' + (isEdit ? 'تعديل الامتحان' : 'إضافة امتحان') + '</h3>' +
              '<p class="text-body-md text-on-surface-variant">' + esc(day) + ' × ' + esc(dept.semesterLabels[semester - dept.semStart]) + ' — ' + esc(weekLabel(currentWeek)) + '</p>' +
            '</div>' +
            '<button type="button" class="ws-modal-close bg-surface border border-outline-variant hover:bg-gray-50 w-9 h-9 rounded-lg flex items-center justify-center" aria-label="إغلاق">' +
              '<span class="material-symbols-outlined text-on-surface">close</span>' +
            '</button>' +
          '</div>' +
          '<div class="space-y-md">' +
            '<div class="ws-course-picker relative">' +
              '<label class="text-label-md text-on-surface-variant block mb-xs font-bold">المادة</label>' +
              '<input type="text" class="ws-course-search w-full bg-surface border border-outline-variant rounded-lg py-2 px-4 text-body-md focus:ring-2 focus:ring-primary/20 focus:border-primary" placeholder="ابحث عن مقرر..." autocomplete="off" />' +
              '<input type="hidden" class="ws-f-course" value="' + esc(selectedCourse) + '" />' +
              '<div class="ws-course-list searchable-list" style="display:none;"></div>' +
            '</div>' +
            '<div>' +
              '<label class="text-label-md text-on-surface-variant block mb-xs font-bold">القاعة</label>' +
              '<select class="ws-f-room w-full bg-surface border border-outline-variant rounded-lg py-2 px-4 text-body-md focus:ring-2 focus:ring-primary/20 focus:border-primary">' +
                rooms.map(function (r) {
                  return '<option value="' + esc(r.id) + '"' + (r.id === selectedRoom ? ' selected' : '') + '>' + esc(r.name) + '</option>';
                }).join('') +
              '</select>' +
            '</div>' +
            '<div class="grid grid-cols-2 gap-md">' +
              '<div>' +
                '<label class="text-label-md text-on-surface-variant block mb-xs font-bold">وقت البداية</label>' +
                '<select class="ws-f-start w-full bg-surface border border-outline-variant rounded-lg py-2 px-4 text-body-md focus:ring-2 focus:ring-primary/20 focus:border-primary">' +
                  times.map(function (t) { return '<option value="' + esc(t) + '"' + (t === defaultStart ? ' selected' : '') + '>' + esc(t) + '</option>'; }).join('') +
                '</select>' +
              '</div>' +
              '<div>' +
                '<label class="text-label-md text-on-surface-variant block mb-xs font-bold">وقت النهاية</label>' +
                '<select class="ws-f-end w-full bg-surface border border-outline-variant rounded-lg py-2 px-4 text-body-md focus:ring-2 focus:ring-primary/20 focus:border-primary">' +
                  times.map(function (t) { return '<option value="' + esc(t) + '"' + (t === defaultEnd ? ' selected' : '') + '>' + esc(t) + '</option>'; }).join('') +
                '</select>' +
              '</div>' +
            '</div>' +
          '</div>' +
          '<div class="ws-f-conflicts hidden mt-md rounded-lg border border-red-200 bg-red-50 p-md"></div>' +
          '<div class="flex flex-wrap items-center justify-end gap-sm mt-lg pt-md border-t border-outline-variant">' +
            (isEdit ?
              '<button type="button" class="ws-f-delete bg-red-50 border border-red-300 text-red-700 hover:bg-red-100 py-2 px-4 rounded-lg text-body-md font-bold transition-colors">حذف الامتحان</button>'
              : '') +
            '<button type="button" class="ws-modal-cancel bg-surface border border-outline-variant text-on-surface hover:bg-gray-50 py-2 px-4 rounded-lg text-body-md font-bold transition-colors">إلغاء</button>' +
            '<button type="button" class="ws-f-save bg-primary text-on-primary hover:bg-primary/90 py-2 px-4 rounded-lg text-body-md font-bold transition-colors shadow-sm">' + (isEdit ? 'حفظ التعديل' : 'إضافة الامتحان') + '</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(modal);
      document.body.style.overflow = 'hidden';

      var courseSearch = modal.querySelector('.ws-course-search');
      var courseHidden = modal.querySelector('.ws-f-course');
      var courseList = modal.querySelector('.ws-course-list');

      function renderCourseList(filter) {
        var q = (filter || '').toLowerCase();
        var html = '';
        for (var i = 0; i < courses.length; i++) {
          var c = courses[i];
          var label = c.name + (c.code ? ' (' + c.code + ')' : '');
          if (q && label.toLowerCase().indexOf(q) === -1) continue;
          var sel = String(c.id) === String(courseHidden.value);
          html += '<div class="searchable-item' + (sel ? ' searchable-item-active' : '') + '" data-course-id="' + esc(c.id) + '">' + esc(label) + '</div>';
        }
        if (!html) {
          html = '<div class="searchable-item" style="cursor:default;opacity:.5;">لا توجد نتائج</div>';
        }
        courseList.innerHTML = html;
      }

      renderCourseList('');
      courseList.style.display = 'block';

      courseSearch.addEventListener('input', function () {
        renderCourseList(courseSearch.value);
        courseList.style.display = 'block';
      });

      courseSearch.addEventListener('focus', function () {
        renderCourseList(courseSearch.value);
        courseList.style.display = 'block';
      });

      courseList.addEventListener('click', function (ev) {
        var item = ev.target.closest ? ev.target.closest('.searchable-item[data-course-id]') : null;
        if (!item) return;
        var cid = item.getAttribute('data-course-id');
        courseHidden.value = cid;
        courseSearch.value = item.textContent;
        courseList.style.display = 'none';
      });

      if (selectedCourse) {
        for (var ci = 0; ci < courses.length; ci++) {
          if (String(courses[ci].id) === String(selectedCourse)) {
            courseSearch.value = courses[ci].name + (courses[ci].code ? ' (' + courses[ci].code + ')' : '');
            break;
          }
        }
      }

      document.addEventListener('mousedown', function coursePickerOutside(ev) {
        if (!modal) { document.removeEventListener('mousedown', coursePickerOutside); return; }
        if (!modal.querySelector('.ws-course-picker').contains(ev.target)) {
          courseList.style.display = 'none';
        }
      });
      var roomSel = modal.querySelector('.ws-f-room');
      var startSel = modal.querySelector('.ws-f-start');
      var endSel = modal.querySelector('.ws-f-end');
      var conflictsEl = modal.querySelector('.ws-f-conflicts');

      startSel.addEventListener('change', function () {
        if (startSel.value >= endSel.value) {
          endSel.value = times[times.indexOf(startSel.value) + 1] || startSel.value;
        }
      });

      modal.querySelector('.ws-modal-close').addEventListener('click', closeModal);
      modal.querySelector('.ws-modal-cancel').addEventListener('click', closeModal);
      modal.addEventListener('click', function (ev) {
        if (ev.target === modal) closeModal();
      });

      function currentExamType() {
        if (isEdit && existing.exam.type) return existing.exam.type;
        var cid = courseHidden.value;
        var course = null;
        for (var i = 0; i < courses.length; i++) {
          if (String(courses[i].id) === String(cid)) { course = courses[i]; break; }
        }
        return course && course.practical_hours ? 'practical' : 'written';
      }

      var saveBtn = modal.querySelector('.ws-f-save');
      saveBtn.addEventListener('click', function () {
        if (!courseHidden.value) { window.ExamToast('يرجى اختيار المادة', true); return; }
        if (!roomSel.value) { window.ExamToast('يرجى اختيار القاعة', true); return; }
        if (startSel.value >= endSel.value) { window.ExamToast('وقت النهاية يجب أن يكون بعد وقت البداية', true); return; }
        saveBtn.disabled = true;
        var payload = {
          dept_id: dept.id,
          semester: semester,
          week: currentWeek,
          day: day,
          course_id: courseHidden.value,
          room_id: roomSel.value,
          start_time: startSel.value,
          end_time: endSel.value,
          exam_type: currentExamType()
        };
        if (isEdit) payload.schedule_id = existing.exam.id;
        window.Exams.api.post('/api/exams/department-schedule/cell', payload).then(function (res) {
          if (res && res.has_conflicts) {
            saveBtn.disabled = false;
            conflictsEl.classList.remove('hidden');
            conflictsEl.innerHTML = '<div class="flex items-center gap-1 mb-sm text-red-700 font-bold"><span class="material-symbols-outlined text-[18px]">warning</span>تعارض في الجدول:</div>' +
              '<ul class="list-disc pr-5 space-y-1 text-body-md text-red-700">' +
              (res.conflicts || []).map(function (c) { return '<li>' + esc(c.message) + '</li>'; }).join('') +
              '</ul>';
            return;
          }
          window.ExamToast(isEdit ? 'تم تحديث الامتحان' : 'تمت إضافة الامتحان');
          closeModal();
          reloadTable();
        }).catch(function (err) {
          saveBtn.disabled = false;
          window.ExamToast(err.message, true);
        });
      });

      var delBtn = modal.querySelector('.ws-f-delete');
      if (delBtn) delBtn.addEventListener('click', function () {
        if (!window.confirm('هل تريد حذف هذا الامتحان؟')) return;
        delBtn.disabled = true;
        window.Exams.api.del('/api/exams/department-schedule/cell/' + existing.exam.id).then(function () {
          window.ExamToast('تم حذف الامتحان');
          closeModal();
          reloadTable();
        }).catch(function (err) {
          delBtn.disabled = false;
          window.ExamToast(err.message, true);
        });
      });
    }

    renderAll();
  }

  function init(panel, opts) {
    opts = opts || {};
    if (opts.data) {
      render(panel, opts.data, opts);
      return;
    }
    panel.innerHTML = '<div class="ws-loading">جارٍ تحميل جدول الامتحانات…</div>';
    window.Exams.api.get('/api/exams/schedule').then(function (data) {
      render(panel, data || {}, opts);
    }).catch(function (err) {
      panel.innerHTML = '<div class="ws-error">' + (window.ExamEsc ? window.ExamEsc(err.message) : err.message) + '</div>';
    });
  }

  window.ExamSchedule = {
    init: init,
    getState: function () { return stateHolder; }
  };
})();
