/* Faculty performance — in-page leave editor modal.
   Opens on [data-leave-manage]; loads one teacher's leaves via
   GET  /faculty-performance/api/teachers/<id>/leaves
   and saves via POST to the same URL (JSON). After a successful save it
   updates THAT same member's row summary and closes the modal — the page
   never navigates or reloads. Pages may set window.FACULTY_LEAVES_MODAL.onSaved
   to refresh extra UI after saving. */
(function () {
  'use strict';

  var API_BASE = '/faculty-performance';
  var state = { id: null, name: '', types: [], saving: false };

  function getContainer() {
    return document.getElementById('modal-leaves-container');
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

  function typesHtml(types, selected) {
    var html = '<option value="">— اختر —</option>';
    (types || []).forEach(function (t) {
      var sel = (String(t) === String(selected)) ? ' selected' : '';
      html += '<option value="' + esc(t) + '"' + sel + '">' + esc(t) + '</option>';
    });
    return html;
  }

  function rowHtml(lv) {
    lv = lv || {};
    var select =
      '<select name="leave_type[]" required ' +
      'class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm ' +
      'focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">' +
      typesHtml(state.types, lv.leave_type || '') + '</select>';
    var inputCls =
      'w-full border border-outline-variant rounded-lg px-3 py-2 text-sm ' +
      'focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none';
    return [
      '<div class="leave-row flex flex-wrap items-end gap-2 p-3 rounded-xl border border-outline-variant bg-surface-dim">',
      '<div class="flex-1 min-w-[160px]"><label class="block text-xs font-bold text-on-surface-variant mb-1">نوع القرار</label>',
      select + '</div>',
      '<div class="flex-1 min-w-[130px]"><label class="block text-xs font-bold text-on-surface-variant mb-1">رقم القرار</label>',
      '<input type="text" name="decision_number[]" value="' + esc(lv.decision_number || '') + '" class="' + inputCls + '"></div>',
      '<div class="flex-1 min-w-[130px]"><label class="block text-xs font-bold text-on-surface-variant mb-1">جهة الإصدار</label>',
      '<input type="text" name="decision_authority[]" value="' + esc(lv.decision_authority || '') + '" class="' + inputCls + '"></div>',
      '<div class="w-32"><label class="block text-xs font-bold text-on-surface-variant mb-1">تاريخ القرار</label>',
      '<input type="date" name="decision_date[]" value="' + esc(lv.decision_date || '') + '" class="' + inputCls + '"></div>',
      '<div class="w-32"><label class="block text-xs font-bold text-on-surface-variant mb-1">من تاريخ</label>',
      '<input type="date" name="start_date[]" required value="' + esc(lv.start_date || '') + '" class="' + inputCls + '"></div>',
      '<div class="w-32"><label class="block text-xs font-bold text-on-surface-variant mb-1">إلى تاريخ</label>',
      '<input type="date" name="end_date[]" value="' + esc(lv.end_date || '') + '" class="' + inputCls + '"></div>',
      '<div class="w-28"><label class="block text-xs font-bold text-on-surface-variant mb-1">الساعات</label>',
      '<input type="number" name="hours[]" value="' + esc(lv.hours || 0) + '" min="1" max="24" step="1" inputmode="numeric" class="' + inputCls + '"></div>',
      '<div class="flex-1 min-w-[100px]"><label class="block text-xs font-bold text-on-surface-variant mb-1">ملاحظات</label>',
      '<input type="text" name="notes[]" value="' + esc(lv.notes || '') + '" class="' + inputCls + '" placeholder="اختياري"></div>',
      '<button type="button" onclick="this.closest(\'.leave-row\').remove()" class="p-2 rounded-lg hover:bg-red-50 text-red-500 transition">',
      '<span class="material-symbols-outlined text-lg">delete</span></button>',
      '</div>'
    ].join('');
  }

  function setSummary(teacherId, count, hours) {
    document.querySelectorAll('.member-leaves-summary[data-teacher-id="' + teacherId + '"]')
      .forEach(function (el) {
        var txt = count > 0
          ? count + ' ' + (count === 1 ? 'إجازة' : 'إجازات') + (hours > 0 ? ' · ' + hours + ' ساعة' : '')
          : 'لا توجد إجازات';
        el.textContent = txt;
      });
  }

  function openForTeacher(teacherId, teacherName) {
    var container = getContainer();
    if (!container || !teacherId) return;
    container.innerHTML =
      '<p class="text-sm text-on-surface-variant py-4 text-center">جاري تحميل الإجازات...</p>';

    fetch(API_BASE + '/api/teachers/' + encodeURIComponent(teacherId) + '/leaves', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(function (r) {
        if (!r.ok) throw new Error('تعذر تحميل الإجازات (رمز ' + r.status + ')');
        return r.json();
      })
      .then(function (res) {
        if (!res.ok) throw new Error(res.message || 'تعذر تحميل الإجازات');
        state.id = String(teacherId);
        state.name = teacherName || res.teacher_name || '';
        state.types = res.leave_types || [];

        container.innerHTML = '';
        var leaves = res.leaves || [];
        if (!leaves.length) leaves = [{}];
        leaves.forEach(function (lv) {
          container.insertAdjacentHTML('beforeend', rowHtml(lv));
        });

        var totalHours = leaves.reduce(function (sum, lv) {
          return sum + (parseInt(lv.hours, 10) || 0);
        }, 0);
        setSummary(state.id, leaves.length, totalHours);

        var titleEl = document.getElementById('leavesModalTitle');
        var teacherEl = document.getElementById('leavesModalTeacher');
        if (titleEl) titleEl.textContent = 'إدارة الإجازات';
        if (teacherEl) teacherEl.textContent = 'إجازات ' + state.name + (res.dept_name ? ' — ' + res.dept_name : '');

        var printEl = document.getElementById('modalPrintLeaves');
        if (printEl) printEl.href = API_BASE + '/leaves/' + encodeURIComponent(state.id) + '/print';

        if (window.openModal) window.openModal('leavesModal');
      })
      .catch(function (err) {
        container.innerHTML = '';
        if (window.showToastError) {
          window.showToastError(err.message || 'تعذر تحميل الإجازات');
        }
      });
  }

  function collectRows() {
    var container = getContainer();
    var rows = [];
    if (!container) return rows;
    container.querySelectorAll('.leave-row').forEach(function (row) {
      rows.push({
        leave_type: rowVal(row, 'leave_type[]'),
        decision_number: rowVal(row, 'decision_number[]'),
        decision_authority: rowVal(row, 'decision_authority[]'),
        decision_date: rowVal(row, 'decision_date[]'),
        start_date: rowVal(row, 'start_date[]'),
        end_date: rowVal(row, 'end_date[]'),
        hours: parseInt(rowVal(row, 'hours[]'), 10) || 0,
        notes: rowVal(row, 'notes[]')
      });
    });
    return rows;
  }

  function save() {
    var container = getContainer();
    if (!container || !state.id || state.saving) return;
    state.saving = true;

    var btn = document.getElementById('modalSaveLeaves');
    var origText = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'حفظ...'; }

    fetch(API_BASE + '/api/teachers/' + encodeURIComponent(state.id) + '/leaves', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({ leaves: collectRows() })
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok || !res.success) {
          throw new Error(res.message || 'تعذر حفظ الإجازات');
        }
        setSummary(state.id, res.leaves_count, res.total_hours);

        var hook = window.FACULTY_LEAVES_MODAL.onSaved;
        if (typeof hook === 'function') {
          Promise.resolve(hook({
            teacher_id: state.id,
            leaves_count: res.leaves_count,
            total_hours: res.total_hours
          })).catch(function () {});
        }

        if (window.closeModal) window.closeModal('leavesModal');
        if (window.showToastSuccess) window.showToastSuccess('تم حفظ إجازات العضو بنجاح');
      })
      .catch(function (err) {
        if (window.showToastError) {
          window.showToastError(err.message || 'تعذر حفظ الإجازات');
        }
      })
      .then(function () {
        state.saving = false;
        if (btn) { btn.disabled = false; btn.textContent = origText; }
      });
  }

  document.addEventListener('click', function (e) {
    var opener = e.target.closest('[data-leave-manage]');
    if (opener) {
      e.preventDefault();
      openForTeacher(opener.getAttribute('data-teacher-id'),
                     opener.getAttribute('data-teacher-name'));
      return;
    }
    if (e.target.closest('#modalAddLeaveRow')) {
      var container = getContainer();
      if (container) container.insertAdjacentHTML('beforeend', rowHtml({}));
      return;
    }
    if (e.target.closest('#modalSaveLeaves')) {
      save();
    }
  });

  window.FACULTY_LEAVES_MODAL = { open: openForTeacher, onSaved: null };
})();