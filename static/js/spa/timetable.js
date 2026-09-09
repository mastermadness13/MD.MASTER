/* SPA.timetable — timetable grid view + entry creation/editing. */
(function () {
  'use strict';

  var S = window.SPA;
  var E = S.escapeHtml;

  function fmtTime12(v) {
    if (!v) return v || '';
    var m = String(v).match(/^(\d{1,2}):(\d{2})$/);
    if (!m) return v;
    var h = parseInt(m[1], 10), min = m[2];
    var period = h < 12 ? 'ص' : 'م';
    var h12 = h % 12; if (h12 === 0) h12 = 12;
    return h12 + ':' + min + ' ' + period;
  }

  var DAYS = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس'];
  var PERIODS = [
    { start: '08:00', end: '09:30', label: '08:00 - 09:30' },
    { start: '09:30', end: '11:00', label: '09:30 - 11:00' },
    { start: '11:00', end: '12:30', label: '11:00 - 12:30' },
    { start: '12:30', end: '14:00', label: '12:30 - 14:00' },
    { start: '14:00', end: '15:30', label: '14:00 - 15:30' },
    { start: '15:30', end: '17:00', label: '15:30 - 17:00' }
  ];

  function renderTimetable(el) {
    el.innerHTML =
      '<div class="flex items-center justify-between mb-5">' +
      '<div><h1 class="text-2xl font-bold text-on-surface">الجدول الدراسي</h1>' +
      '<p class="text-sm text-on-surface-variant mt-1">عرض وإدارة الجدول الأسبوعي</p></div>' +
      '<div id="spa-tt-actions" class="flex items-center gap-2"></div></div>' +
      '<div id="spa-tt-filters" class="bg-white rounded-xl border border-outline shadow-sm p-3 mb-4 flex flex-wrap items-center gap-3">' +
      '<select id="spa-tt-dept" class="px-3 py-2 rounded-lg border border-outline text-sm"><option value="">جميع الأقسام</option></select>' +
      '<select id="spa-tt-teacher" class="px-3 py-2 rounded-lg border border-outline text-sm"><option value="">جميع أعضاء هيئة التدريس</option></select>' +
      '<select id="spa-tt-semester" class="px-3 py-2 rounded-lg border border-outline text-sm">' +
      '<option value="">جميع الفصول</option><option value="1">الفصل الأول</option><option value="2">الفصل الثاني</option></select>' +
      '</div>' +
      '<div class="bg-white rounded-xl border border-outline shadow-sm overflow-x-auto">' +
      '<div id="spa-tt-grid" class="p-4">جاري التحميل…</div></div>';

    if (can('timetable.edit')) {
      document.getElementById('spa-tt-actions').innerHTML =
        '<button id="spa-tt-add" class="inline-flex items-center gap-2 bg-primary text-on-primary px-4 py-2 rounded-lg font-bold text-sm hover:opacity-90">' +
        '<span class="material-symbols-outlined text-lg">add</span> إضافة حصة</button>';
      document.getElementById('spa-tt-add').addEventListener('click', function () { openEntryForm(); });
    }

    loadFilters().then(function () { loadGrid(); });

    ['spa-tt-dept', 'spa-tt-teacher', 'spa-tt-semester'].forEach(function (id) {
      var el2 = document.getElementById(id);
      if (el2) el2.addEventListener('change', function () { loadGrid(); });
    });
  }

  function loadFilters() {
    return S.api.get('/api/timetable').then(function (data) {
      var departments = {};
      var teachers = {};
      var entries = data.entries || data.items || [];
      entries.forEach(function (e) {
        if (e.department) departments[e.department] = e.department;
        if (e.teacher_name) teachers[e.teacher_name] = e.teacher_name;
      });
      var deptSel = document.getElementById('spa-tt-dept');
      Object.keys(departments).sort().forEach(function (d) {
        var opt = document.createElement('option');
        opt.value = d; opt.textContent = d;
        deptSel.appendChild(opt);
      });
    }).catch(function () {});
  }

  function loadGrid() {
    var dept = (document.getElementById('spa-tt-dept') || {}).value || '';
    var teacher = (document.getElementById('spa-tt-teacher') || {}).value || '';
    var semester = (document.getElementById('spa-tt-semester') || {}).value || '';

    var url = '/api/timetable';
    var params = [];
    if (dept) params.push('department=' + encodeURIComponent(dept));
    if (semester) params.push('semester=' + encodeURIComponent(semester));
    if (params.length) url += '?' + params.join('&');

    var grid = document.getElementById('spa-tt-grid');
    grid.innerHTML = '<div class="text-center py-10 text-sm">جاري التحميل…</div>';

    S.api.get(url).then(function (data) {
      var entries = data.entries || data.items || [];
      renderGrid(grid, entries, teacher);
    }).catch(function (err) {
      grid.innerHTML = '<div class="text-center py-10 text-error text-sm font-bold">' + E(err.message) + '</div>';
    });
  }

  function renderGrid(grid, entries, teacherFilter) {
    var cellMap = {};
    entries.forEach(function (e) {
      if (teacherFilter && e.teacher_name !== teacherFilter) return;
      var key = e.day + '_' + e.start_time;
      cellMap[key] = e;
    });

    var html = '<table class="w-full text-sm border-collapse">';
    html += '<thead><tr><th class="p-2 border border-outline-variant bg-surface font-bold text-on-surface-variant w-24">الوقت</th>';
    DAYS.forEach(function (d) {
      html += '<th class="p-2 border border-outline-variant bg-surface font-bold text-on-surface-variant text-center">' + E(d) + '</th>';
    });
    html += '</tr></thead><tbody>';

    PERIODS.forEach(function (p) {
      html += '<tr>';
      html += '<td class="p-2 border border-outline-variant bg-surface text-xs font-bold text-on-surface-variant text-center whitespace-nowrap">' + E(p.label) + '</td>';
      DAYS.forEach(function (d, di) {
        var key = di + '_' + p.start;
        var entry = cellMap[key];
        if (entry) {
          var bg = 'bg-primary/10 border-primary/30';
          html += '<td class="p-2 border border-outline-variant ' + bg + ' text-center cursor-pointer hover:opacity-80 transition" data-entry-id="' + (entry.id || '') + '">' +
            '<div class="font-bold text-on-surface text-xs">' + E(entry.course_name || entry.course || '') + '</div>' +
            '<div class="text-xs text-on-surface-variant mt-1">' + E(entry.teacher_name || '') + '</div>' +
            '<div class="text-xs text-on-surface-variant">' + E(entry.room_name || entry.room || '') + '</div>' +
            '</td>';
        } else {
          html += '<td class="p-2 border border-outline-variant text-center hover:bg-surface-hover transition cursor-pointer" data-day="' + di + '" data-start="' + p.start + '" data-end="' + p.end + '">' +
            '<span class="text-xs text-on-surface-variant/40">—</span></td>';
        }
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    grid.innerHTML = html;

    if (can('timetable.edit')) {
      grid.querySelectorAll('[data-day]').forEach(function (td) {
        td.addEventListener('click', function () {
          openEntryForm(null, { day: +td.dataset.day, start: td.dataset.start, end: td.dataset.end });
        });
      });
    }
    grid.querySelectorAll('[data-entry-id]').forEach(function (td) {
      td.addEventListener('click', function () {
        openEntryDetail(+td.dataset.entryId);
      });
    });
  }

  function openEntryDetail(id) {
    S.api.get('/api/timetable').then(function (data) {
      var entries = data.entries || data.items || [];
      var entry = entries.find(function (e) { return e.id === id; });
      if (!entry) { showToastError('الحصة غير موجودة'); return; }
      var body = document.createElement('div');
      body.className = 'space-y-3';
      body.innerHTML = '<dl class="grid grid-cols-2 gap-3 text-sm">' +
        f('المقرر', entry.course_name || entry.course) +
        f('عضو هيئة التدريس', entry.teacher_name) +
        f('القاعة', entry.room_name || entry.room) +
        f('اليوم', DAYS[entry.day] || '—') +
        f('الوقت', (fmtTime12(entry.start_time) || '') + ' - ' + (fmtTime12(entry.end_time) || '')) +
        f('القسم', entry.department || '—') +
        '</dl>';
      if (can('timetable.edit')) {
        var footer = document.createElement('div');
        footer.className = 'mt-4 flex items-center justify-end gap-3';
        footer.innerHTML = '<button type="button" class="px-4 py-2 rounded-lg border border-outline text-sm font-bold" data-spa-modal-close>إغلاق</button>' +
          '<button type="button" class="px-4 py-2 rounded-lg bg-error text-on-primary text-sm font-bold" id="spa-tt-del-entry">حذف</button>' +
          '<button type="button" class="px-4 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold" id="spa-tt-edit-entry">تعديل</button>';
        body.appendChild(footer);
      }
      var modal = S.modal.open({ title: 'تفاصيل الحصة', body: body });
      var delBtn = document.getElementById('spa-tt-del-entry');
      var editBtn = document.getElementById('spa-tt-edit-entry');
      if (delBtn) delBtn.addEventListener('click', function () {
        S.api.del('/api/timetable/entries/' + id).then(function () {
          S.modal.close(); showToastSuccess('تم الحذف'); loadGrid();
        }).catch(function (err) { S.modal.showError(err.message); });
      });
      if (editBtn) editBtn.addEventListener('click', function () {
        S.modal.close();
        openEntryForm(entry);
      });
    });
  }

  function openEntryForm(entry, defaults) {
    entry = entry || {};
    defaults = defaults || {};
    var isEdit = !!entry.id;

    var metaReqs = [
      S.api.get('/api/departments'),
      S.api.get('/api/teachers'),
      S.api.get('/api/rooms')
    ];
    Promise.all(metaReqs).then(function (results) {
      var depts = (results[0].items || results[0] || []);
      var teachers = (results[1].items || results[1] || []);
      var rooms = (results[2].items || results[2] || []);

      var dayVal = entry.day != null ? entry.day : (defaults.day != null ? defaults.day : 0);
      var startVal = entry.start_time || defaults.start || '08:00';
      var endVal = entry.end_time || defaults.end || '09:30';

      var dayOpts = DAYS.map(function (d, i) {
        return '<option value="' + i + '"' + (i == dayVal ? ' selected' : '') + '>' + E(d) + '</option>';
      }).join('');

      var teacherOpts = '<option value="">— اختر عضو هيئة التدريس —</option>' + teachers.map(function (t) {
        return '<option value="' + t.id + '"' + (t.id == entry.teacher_id ? ' selected' : '') + '>' + E(t.name || '') + '</option>';
      }).join('');

      var roomOpts = '<option value="">— اختر القاعة —</option>' + rooms.map(function (r) {
        return '<option value="' + r.id + '"' + (r.id == entry.room_id ? ' selected' : '') + '>' + E(r.name || '') + '</option>';
      }).join('');

      var deptOpts = '<option value="">— اختر القسم —</option>' + depts.map(function (d) {
        return '<option value="' + d.id + '"' + (d.id == entry.department_id ? ' selected' : '') + '>' + E(d.name) + '</option>';
      }).join('');

      var body = document.createElement('div');
      body.innerHTML = '<form id="spa-tt-entry-form"><div class="grid grid-cols-1 sm:grid-cols-2 gap-4">' +
        '<div><label class="block text-sm font-bold mb-1">اليوم</label><select name="day" class="w-full px-3 py-2 rounded-lg border border-outline text-sm">' + dayOpts + '</select></div>' +
        '<div><label class="block text-sm font-bold mb-1">القسم</label><select name="department_id" class="w-full px-3 py-2 rounded-lg border border-outline text-sm">' + deptOpts + '</select></div>' +
        '<div><label class="block text-sm font-bold mb-1">عضو هيئة التدريس</label><select name="teacher_id" class="w-full px-3 py-2 rounded-lg border border-outline text-sm">' + teacherOpts + '</select></div>' +
        '<div><label class="block text-sm font-bold mb-1">القاعة</label><select name="room_id" class="w-full px-3 py-2 rounded-lg border border-outline text-sm">' + roomOpts + '</select></div>' +
        '<div><label class="block text-sm font-bold mb-1">من</label><input name="start_time" type="time" value="' + E(startVal) + '" class="w-full px-3 py-2 rounded-lg border border-outline text-sm"></div>' +
        '<div><label class="block text-sm font-bold mb-1">إلى</label><input name="end_time" type="time" value="' + E(endVal) + '" class="w-full px-3 py-2 rounded-lg border border-outline text-sm"></div>' +
        ff('course_name', 'اسم المقرر', 'text', entry.course_name) +
        ff('section', 'الشعبة', 'text', entry.section) +
        '</div>' +
        '<div class="mt-6 flex items-center justify-end gap-3">' +
        '<button type="button" class="px-4 py-2 rounded-lg border border-outline text-sm font-bold" data-spa-modal-close>إلغاء</button>' +
        '<button type="submit" class="px-5 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold hover:opacity-90"><span class="material-symbols-outlined text-lg align-middle">save</span> حفظ</button></div></form>';

      S.modal.open({ title: isEdit ? 'تعديل حصة' : 'إضافة حصة', body: body });
      body.querySelector('#spa-tt-entry-form').addEventListener('submit', function (e) {
        e.preventDefault();
        var fd = new FormData(e.target);
        var payload = {};
        fd.forEach(function (v, k) { payload[k] = v; });
        payload.department_id = payload.department_id || null;
        payload.teacher_id = payload.teacher_id || null;
        payload.room_id = payload.room_id || null;
        var promise = isEdit ? S.api.put('/api/timetable/entries/' + entry.id, payload) : S.api.post('/api/timetable/entries', payload);
        promise.then(function () { S.modal.close(); showToastSuccess(isEdit ? 'تم التحديث' : 'تمت الإضافة'); loadGrid(); })
          .catch(function (err) { S.modal.showError(err.message); });
      });
    }).catch(function (err) { S.modal.open({ title: 'خطأ', body: makeErr(err.message) }); });
  }

  function ff(name, label, type, value) {
    return '<div><label class="block text-sm font-bold mb-1">' + label + '</label>' +
      '<input name="' + name + '" type="' + type + '" value="' + E(value || '') + '" class="w-full px-3 py-2 rounded-lg border border-outline text-sm"></div>';
  }

  function f(label, value) {
    return '<div><dt class="text-xs text-on-surface-variant font-bold">' + label + '</dt><dd class="font-semibold text-on-surface mt-0.5">' + E(value || '—') + '</dd></div>';
  }

  function makeErr(msg) { var el = document.createElement('div'); el.className = 'text-error font-bold text-sm'; el.textContent = msg; return el; }
  function can(p) { return ((S.session && S.session.permissions) || []).indexOf(p) !== -1; }

  window.SPA.VIEWS.timetable = renderTimetable;
  window.SPA.VIEWS.timetable_rnd = renderTimetable;
  window.SPA.VIEWS.timetable_teacher = renderTimetable;
  window.SPA.VIEWS.timetable_archive_hod = renderTimetable;
})();
