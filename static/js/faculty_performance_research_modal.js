/* Faculty performance — in-page research-hours editor modal.
   Opens on [data-research-manage]; loads one teacher's research activities
   via GET /faculty-performance/api/teachers/<id>/research and saves via POST
   to the same URL (JSON, no redirect). After a successful save it fires
   window.FACULTY_RESEARCH_MODAL.onSaved — the preview page uses it to
   re-render the "ثانياً" section and the grand total in place. */
(function () {
  'use strict';

  var API_BASE = '/faculty-performance';
  var state = { id: null, name: '', year: '', semester: '', types: [], max: 0, saving: false };

  function getContainer() {
    return document.getElementById('modal-research-container');
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

  function researchMap(list) {
    var map = {};
    (list || []).forEach(function (r) {
      map[String(r.activity_type).trim()] = r;
    });
    return map;
  }

  function rowHtml(type, existing) {
    existing = existing || {};
    var inputCls =
      'w-full border border-outline-variant rounded-lg px-3 py-2 text-sm ' +
      'focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none';
    return [
      '<div class="research-row flex flex-wrap items-center gap-2 p-3 rounded-xl border border-outline-variant bg-surface-dim">',
      '<input type="hidden" name="activity_type[]" value="' + esc(type.name) + '">',
      '<span class="flex-1 min-w-[180px] text-sm font-bold text-on-surface">' + esc(type.name) + '</span>',
      '<label class="block text-xs font-bold text-on-surface-variant mb-1">الساعات</label>',
      '<input type="number" name="hours[]" min="1" max="24" step="1" inputmode="numeric" pattern="[0-9]*" ' +
      'value="' + esc(existing.hours || 0) + '" class="w-24 ' + inputCls + '">',
      '<label class="block text-xs font-bold text-on-surface-variant mb-1">ملاحظات</label>',
      '<input type="text" name="notes[]" value="' + esc(existing.notes || '') + '" ' +
      'class="flex-1 min-w-[150px] ' + inputCls + '" placeholder="اختياري">',
      '</div>'
    ].join('');
  }

  function openForTeacher(teacherId, teacherName, year, semester) {
    var container = getContainer();
    if (!container || !teacherId) return;
    container.innerHTML =
      '<p class="text-sm text-on-surface-variant py-4 text-center">جاري تحميل الساعات البحثية...</p>';

    var url = API_BASE + '/api/teachers/' + encodeURIComponent(teacherId) + '/research';
    url += '?year=' + encodeURIComponent(year || '') + '&semester=' + encodeURIComponent(semester || '');
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) {
        if (!r.ok) throw new Error('تعذر تحميل الساعات البحثية (رمز ' + r.status + ')');
        return r.json();
      })
      .then(function (res) {
        if (!res.ok) throw new Error(res.message || 'تعذر تحميل الساعات البحثية');
        state.id = String(teacherId);
        state.name = teacherName || res.teacher_name || '';
        state.year = res.academic_year || '';
        state.semester = res.semester || '';
        state.types = res.research_types || [];
        state.max = res.max_research || 0;

        var byType = researchMap(res.research || []);
        container.innerHTML = '';
        state.types.forEach(function (t) {
          container.insertAdjacentHTML('beforeend', rowHtml(t, byType[String(t.name).trim()]));
        });

        var maxEl = document.getElementById('researchModalMax');
        if (maxEl) maxEl.textContent = state.max;

        var titleEl = document.getElementById('researchModalTitle');
        var teacherEl = document.getElementById('researchModalTeacher');
        var periodEl = document.getElementById('researchModalPeriod');
        if (titleEl) titleEl.textContent = 'تعديل الساعات البحثية';
        if (teacherEl) teacherEl.textContent = 'الساعات البحثية لـ ' + state.name + (res.dept_name ? ' — ' + res.dept_name : '');
        if (periodEl) periodEl.textContent = res.academic_year ? (res.academic_year + ' / الفصل ' + (res.semester || 1)) : '';

        if (window.openModal) window.openModal('researchModal');
      })
      .catch(function (err) {
        container.innerHTML = '';
        if (window.showToastError) {
          window.showToastError(err.message || 'تعذر تحميل الساعات البحثية');
        }
      });
  }

  function collectRows() {
    var container = getContainer();
    var rows = [];
    if (!container) return rows;
    container.querySelectorAll('.research-row').forEach(function (row) {
      var atype = (rowVal(row, 'activity_type[]') || '').trim();
      if (!atype) return;
      var raw = rowVal(row, 'hours[]');
      rows.push({
        activity_type: atype,
        hours: parseInt(raw, 10) || 0,
        notes: rowVal(row, 'notes[]')
      });
    });
    return rows;
  }

  function save() {
    var container = getContainer();
    if (!container || !state.id || state.saving) return;
    state.saving = true;

    var btn = document.getElementById('modalSaveResearch');
    var origText = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'حفظ...'; }

    fetch(API_BASE + '/api/teachers/' + encodeURIComponent(state.id) + '/research', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({
        activities: collectRows(),
        academic_year: state.year,
        semester: state.semester
      })
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok || !res.success) {
          throw new Error(res.message || 'تعذر حفظ الساعات البحثية');
        }

        var hook = window.FACULTY_RESEARCH_MODAL.onSaved;
        if (typeof hook === 'function') {
          Promise.resolve(hook({
            teacher_id: state.id,
            total_hours: res.total_hours
          })).catch(function () {});
        }

        if (window.closeModal) window.closeModal('researchModal');
        if (window.showToastSuccess) window.showToastSuccess('تم حفظ الساعات البحثية بنجاح');
      })
      .catch(function (err) {
        if (window.showToastError) {
          window.showToastError(err.message || 'تعذر حفظ الساعات البحثية');
        }
      })
      .then(function () {
        state.saving = false;
        if (btn) { btn.disabled = false; btn.textContent = origText; }
      });
  }

  document.addEventListener('click', function (e) {
    var opener = e.target.closest('[data-research-manage]');
    if (opener) {
      e.preventDefault();
      openForTeacher(opener.getAttribute('data-teacher-id'),
                     opener.getAttribute('data-teacher-name'),
                     opener.getAttribute('data-year') || '',
                     opener.getAttribute('data-semester') || '');
      return;
    }
    if (e.target.closest('#modalSaveResearch')) {
      save();
    }
  });

  window.FACULTY_RESEARCH_MODAL = { open: openForTeacher, onSaved: null };
})();