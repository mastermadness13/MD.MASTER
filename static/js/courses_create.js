
(function () {
  var BOOT = window.COURSES_CREATE_BOOT || {};
  var COURSE_OPTIONS = BOOT.courses || [];
  var DEPT_MAP = BOOT.deptMap || {};

  var deptIcons = {
    'القسم العام': '🏗️', 'قسم الاتصالات': '📡', 'قسم الحاسوب': '💻',
    'قسم المدني': '🏢', 'قسم المعماري': '🏛️', 'قسم النفط': '⛽'
  };

  // ===== department icons =====
  var deptGrid = document.getElementById('dept-grid');
  if (deptGrid) {
    deptGrid.querySelectorAll('[data-dept-name]').forEach(function (span) {
      var icon = deptIcons[span.getAttribute('data-dept-name')] || '📚';
      span.textContent = icon + ' ' + span.textContent;
    });
  }

  // ===== auto total hours =====
  var theoryEl = document.getElementById('theoryHours');
  var practicalEl = document.getElementById('practicalHours');
  var totalEl = document.getElementById('totalHours');
  var totalTouched = false;
  if (theoryEl && practicalEl && totalEl) {
    function recalc() {
      if (totalTouched) return;
      totalEl.value = (parseInt(theoryEl.value || 0, 10) || 0) + (parseInt(practicalEl.value || 0, 10) || 0);
    }
    theoryEl.addEventListener('input', recalc);
    practicalEl.addEventListener('input', recalc);
    totalEl.addEventListener('input', function () { totalTouched = true; });
  }

  // ===== searchable prerequisite select =====
  var searchEl = document.getElementById('prereqSearch');
  var valueEl = document.getElementById('prereqValue');
  var listEl = document.getElementById('prereqList');
  if (searchEl && valueEl && listEl) {
    function selectedDepts() {
      var out = [];
      document.querySelectorAll('input[name="department_ids"]:checked').forEach(function (cb) {
        out.push(parseInt(cb.value, 10));
      });
      return out;
    }
    /* Course code and name are free-text columns (only .strip() on write), so
     * they must be escaped before being shown in the prerequisite picker. */
    function esc(s) {
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function displayText(c) {
      return esc(c.code || '') + ' - ' + esc(c.name || '');
    }
    function currentSelection() {
      var v = valueEl.value;
      if (!v) return null;
      for (var i = 0; i < COURSE_OPTIONS.length; i++) {
        if (String(COURSE_OPTIONS[i].id) === String(v)) return COURSE_OPTIONS[i];
      }
      return null;
    }
    function renderList() {
      var q = (searchEl.value || '').trim().toLowerCase();
      var depts = selectedDepts();
      var matched = COURSE_OPTIONS.filter(function (c) {
        var cDepts = DEPT_MAP[c.id] || [];
        if (depts.length && !cDepts.some(function (d) { return depts.indexOf(d) !== -1; })) return false;
        if (!q) return true;
        return (c.name || '').toLowerCase().indexOf(q) !== -1 || (c.code || '').toLowerCase().indexOf(q) !== -1;
      });
      var html = '';
      html += '<div class="px-4 py-2.5 cursor-pointer hover:bg-surface-container transition-colors text-sm text-on-surface-variant" data-val="">— بدون متطلب سابق —</div>';
      matched.forEach(function (c) {
        html += '<div class="px-4 py-2.5 cursor-pointer hover:bg-surface-container transition-colors text-sm text-on-surface flex items-center justify-between gap-2" data-val="' + c.id + '">' +
          '<span>' + displayText(c) + '</span>' +
          '<span class="material-symbols-outlined text-[16px] text-primary">arrow_back</span>' +
        '</div>';
      });
      listEl.innerHTML = html;
      listEl.querySelectorAll('[data-val]').forEach(function (opt) {
        opt.addEventListener('mousedown', function (e) {
          e.preventDefault();
          var v = opt.getAttribute('data-val');
          valueEl.value = v;
          var c = null;
          for (var i = 0; i < COURSE_OPTIONS.length; i++) {
            if (String(COURSE_OPTIONS[i].id) === String(v)) { c = COURSE_OPTIONS[i]; break; }
          }
          searchEl.value = c ? displayText(c) : '';
          listEl.classList.add('hidden');
          searchEl.classList.remove('border-primary');
        });
      });
    }
    searchEl.addEventListener('focus', function () {
      renderList();
      listEl.classList.remove('hidden');
    });
    searchEl.addEventListener('input', renderList);
    document.addEventListener('click', function (e) {
      if (!listEl.classList.contains('hidden') && !listEl.contains(e.target) && e.target !== searchEl) {
        listEl.classList.add('hidden');
        var c = currentSelection();
        searchEl.value = c ? displayText(c) : '';
      }
    });
    var sel = currentSelection();
    if (sel) searchEl.value = displayText(sel);
  }
})();
