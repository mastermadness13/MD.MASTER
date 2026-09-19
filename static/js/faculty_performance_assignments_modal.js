/* Faculty performance — in-page admin-assignments editor modal.
   Opens on [data-assignments-manage]; loads one teacher's admin assignments
   via GET /faculty-performance/api/teachers/<id>/assignments and saves via
   POST to the same URL (JSON, no redirect). After a successful save it fires
   window.FACULTY_ASSIGNMENTS_MODAL.onSaved — the preview page uses it to
   re-render the "رابعاً" section and the grand total in place. */
(function () {
  'use strict';

  var API_BASE = '/faculty-performance';
  var state = { id: null, name: '', year: '', semester: '', taskTypes: [], taskHours: {}, saving: false };

  function getContainer() {
    return document.getElementById('modal-assignments-container');
  }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function rowVal(row, name) {
    var el = row.querySelector('[name="' + name + '"]');
    return el ? el.value : '';
  }

  function taskOptionsHtml(selected) {
    var html = '<option value="">— اختر —</option>';
    (state.taskTypes || []).forEach(function (t) {
      var name = t && t.name != null ? t.name : t;
      var sel = (String(name) === String(selected)) ? ' selected' : '';
      html += '<option value="' + esc(name) + '"' + sel + '">' + esc(name) + '</option>';
    });
    return html;
  }

  function rowHtml(a) {
    a = a || {};
    var select =
      '<select name="task_name[]" required ' +
      'class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm ' +
      'focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">' +
      taskOptionsHtml(a.task_name || '') + '</select>';
    var inputCls =
      'w-full border border-outline-variant rounded-lg px-3 py-2 text-sm ' +
      'focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none';
    var autoCls =
      'w-full border border-outline-variant rounded-lg px-3 py-2 text-sm ' +
      'bg-gray-50 text-on-surface-variant outline-none';
    return [
      '<div class="assignment-row flex flex-wrap items-end gap-2 p-3 rounded-xl border border-outline-variant bg-surface-dim">',
      '<div class="flex-1 min-w-[200px]"><label class="block text-xs font-bold text-on-surface-variant mb-1">المهمة الإدارية</label>',
      select + '</div>',
      '<div class="w-20"><label class="block text-xs font-bold text-on-surface-variant mb-1">الساعات (تلقائي)</label>',
      '<input type="number" name="auto_hours[]" min="0" value="' + esc(a.auto_hours || '') + '" readonly class="' + autoCls + '"></div>',
      '<div class="w-20"><label class="block text-xs font-bold text-on-surface-variant mb-1">ساعات يدوية</label>',
      '<input type="number" name="manual_hours[]" min="1" max="24" value="' + esc(a.manual_hours || 0) + '" class="' + inputCls + '"></div>',
      '<div class="w-32"><label class="block text-xs font-bold text-on-surface-variant mb-1">تاريخ التكليف</label>',
      '<input type="date" name="assignment_date[]" value="' + esc(a.assignment_date || '') + '" class="' + inputCls + '"></div>',
      '<div class="w-32"><label class="block text-xs font-bold text-on-surface-variant mb-1">من تاريخ</label>',
      '<input type="date" name="start_date[]" required value="' + esc(a.start_date || '') + '" class="' + inputCls + '"></div>',
      '<div class="w-32"><label class="block text-xs font-bold text-on-surface-variant mb-1">إلى تاريخ</label>',
      '<input type="date" name="end_date[]" value="' + esc(a.end_date || '') + '" class="' + inputCls + '" placeholder="لا يزال ساريًا"></div>',
      '<div class="flex-1 min-w-[120px]"><label class="block text-xs font-bold text-on-surface-variant mb-1">ملاحظات</label>',
      '<input type="text" name="notes[]" value="' + esc(a.notes || '') + '" class="' + inputCls + '" placeholder="اختياري"></div>',
      '<button type="button" onclick="this.closest(\'.assignment-row\').remove()" class="p-2 rounded-lg hover:bg-red-50 text-red-500 transition">',
      '<span class="material-symbols-outlined text-lg">delete</span></button>',
      '</div>'
    ].join('');
  }

  function autoFillHours(row) {
    var select = row.querySelector('[name="task_name[]"]');
    var auto = row.querySelector('[name="auto_hours[]"]');
    if (!select || !auto) return;
    var hours = state.taskHours[select.value];
    auto.value = (hours == null || hours === '') ? '' : hours;
  }

  function openForTeacher(teacherId, teacherName, year, semester) {
    var container = getContainer();
    if (!container || !teacherId) return;
    container.innerHTML =
      '<p class="text-sm text-on-surface-variant py-4 text-center">جاري تحميل التكليفات الإدارية...</p>';

    var url = API_BASE + '/api/teachers/' + encodeURIComponent(teacherId) + '/assignments';
    url += '?year=' + encodeURIComponent(year || '') + '&semester=' + encodeURIComponent(semester || '');
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) {
        if (!r.ok) throw new Error('تعذر تحميل التكليفات الإدارية (رمز ' + r.status + ')');
        return r.json();
      })
      .then(function (res) {
        if (!res.ok) throw new Error(res.message || 'تعذر تحميل التكليفات الإدارية');
        state.id = String(teacherId);
        state.name = teacherName || res.teacher_name || '';
        state.year = res.academic_year || '';
        state.semester = res.semester || '';
        state.taskTypes = res.admin_task_types || [];
        state.taskHours = res.admin_task_hours || {};

        container.innerHTML = '';
        var assignments = res.assignments || [];
        if (!assignments.length) assignments = [{}];
        assignments.forEach(function (a) {
          var row = rowHtml(a);
          container.insertAdjacentHTML('beforeend', row);
        });
        container.querySelectorAll('.assignment-row').forEach(autoFillHours);

        var titleEl = document.getElementById('assignmentsModalTitle');
        var teacherEl = document.getElementById('assignmentsModalTeacher');
        var periodEl = document.getElementById('assignmentsModalPeriodText');
        if (titleEl) titleEl.textContent = 'تعديل التكليفات الإدارية';
        if (teacherEl) teacherEl.textContent = 'التكليفات الإدارية لـ ' + state.name + (res.dept_name ? ' — ' + res.dept_name : '');
        if (periodEl && res.sem_start) {
          periodEl.textContent = 'التكليف ساري خلال الفترة: ' + res.sem_start + ' إلى ' + (res.sem_end || '...');
        }

        if (window.openModal) window.openModal('assignmentsModal');
      })
      .catch(function (err) {
        container.innerHTML = '';
        if (window.showToastError) {
          window.showToastError(err.message || 'تعذر تحميل التكليفات الإدارية');
        }
      });
  }

  function collectRows() {
    var container = getContainer();
    var rows = [];
    if (!container) return rows;
    container.querySelectorAll('.assignment-row').forEach(function (row) {
      var taskName = (rowVal(row, 'task_name[]') || '').trim();
      if (!taskName) return;
      var autoRaw = rowVal(row, 'auto_hours[]');
      rows.push({
        task_name: taskName,
        auto_hours: autoRaw === '' ? null : parseInt(autoRaw, 10),
        manual_hours: parseInt(rowVal(row, 'manual_hours[]'), 10) || 0,
        assignment_date: rowVal(row, 'assignment_date[]'),
        start_date: rowVal(row, 'start_date[]'),
        end_date: rowVal(row, 'end_date[]') || null,
        notes: rowVal(row, 'notes[]')
      });
    });
    return rows;
  }

  function save() {
    var container = getContainer();
    if (!container || !state.id || state.saving) return;
    state.saving = true;

    var btn = document.getElementById('modalSaveAssignments');
    var origText = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'حفظ...'; }

    fetch(API_BASE + '/api/teachers/' + encodeURIComponent(state.id) + '/assignments', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({
        assignments: collectRows(),
        academic_year: state.year,
        semester: state.semester
      })
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok || !res.success) {
          throw new Error(res.message || 'تعذر حفظ التكليفات الإدارية');
        }

        var hook = window.FACULTY_ASSIGNMENTS_MODAL.onSaved;
        if (typeof hook === 'function') {
          Promise.resolve(hook({
            teacher_id: state.id,
            assignments_count: res.assignments_count
          })).catch(function () {});
        }

        if (window.closeModal) window.closeModal('assignmentsModal');
        if (window.showToastSuccess) window.showToastSuccess('تم حفظ التكليفات الإدارية بنجاح');
      })
      .catch(function (err) {
        if (window.showToastError) {
          window.showToastError(err.message || 'تعذر حفظ التكليفات الإدارية');
        }
      })
      .then(function () {
        state.saving = false;
        if (btn) { btn.disabled = false; btn.textContent = origText; }
      });
  }

  function addRow() {
    var container = getContainer();
    if (container) container.insertAdjacentHTML('beforeend', rowHtml({}));
  }

  document.addEventListener('click', function (e) {
    var opener = e.target.closest('[data-assignments-manage]');
    if (opener) {
      e.preventDefault();
      openForTeacher(opener.getAttribute('data-teacher-id'),
                     opener.getAttribute('data-teacher-name'),
                     opener.getAttribute('data-year') || '',
                     opener.getAttribute('data-semester') || '');
      return;
    }
    if (e.target.closest('#modalAddAssignmentRow')) {
      addRow();
      return;
    }
    if (e.target.closest('#modalSaveAssignments')) {
      save();
    }
  });

  document.addEventListener('change', function (e) {
    if (!e.target || !e.target.closest) return;
    var row = e.target.closest('.assignment-row');
    var select = e.target.closest('[name="task_name[]"]');
    if (row && select) autoFillHours(row);
  });

  window.FACULTY_ASSIGNMENTS_MODAL = { open: openForTeacher, onSaved: null };
})();