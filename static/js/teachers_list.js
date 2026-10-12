var BOOT = window.TEACHERS_LIST_BOOT || {};
var URLS = BOOT.urls || {};
SearchComponent.init({
  formSelector: '#teachersSearchForm',
  inputSelector: '.search-input',
  tableSelector: '.search-table',
  countSelector: '.search-results-count',
  clearSelector: '.search-clear',
  spinnerSelector: '.search-spinner',
  paginationSelector: '.search-pagination',
  filterSelectors: { department_id: 'select[name=department_id]' },
  debounceMs: 300,
  resetSelector: '#resetFilters',
  formAction: (window.TEACHERS_LIST_BOOT || {}).listUrl || null,
  onComplete: function () {
    if (window.syncTeacherBulk) window.syncTeacherBulk();
  },
});

(function () {
var selectAll = document.getElementById('selectAllTeachers');
  var countEl = document.getElementById('selectedCount');
  var clearBtn = document.getElementById('clearSelectionBtn');
  var deleteBtn = document.getElementById('bulkDeleteBtn');
  var headerDeleteBtn = document.getElementById('headerDeleteBtn');
  var form = document.getElementById('bulkDeleteForm');
  var selectAllTotalBtn = document.getElementById('selectAllTotalBtn');
  var selectAllBar = document.getElementById('selectAllBar');
  var selectAllBarText = document.getElementById('selectAllBarText');
  var selectAllActive = false;
  var allIds = [];
  var total = BOOT.total || 0;

  function getFormParams() {
    var params = new URLSearchParams();
    var searchInput = document.querySelector('input[name=search]');
    var deptSelect = document.querySelector('select[name=department_id]');
    if (searchInput && searchInput.value) params.set('search', searchInput.value);
    if (deptSelect && deptSelect.value) params.set('department_id', deptSelect.value);
    return params.toString();
  }

  // /  البحث عبر AJAX يستبدل tbody، فالقائمة المخزّنة تصير عناصر يتيمة
  function getChecks() {
    return Array.prototype.slice.call(document.querySelectorAll('.teacher-check'));
  }

  function bindChecks() {
    getChecks().forEach(function (c) {
      if (c.dataset.bound) return;
      c.dataset.bound = '1';
      c.addEventListener('change', update);
    });
  }

  function update() {
    var checks = getChecks();
    var selected = checks.filter(function (c) { return c.checked; }).length;
    if (countEl) countEl.textContent = selectAllActive ? allIds.length : selected;
    if (clearBtn) clearBtn.disabled = (selectAllActive ? allIds.length : selected) === 0;
    if (deleteBtn) deleteBtn.disabled = (selectAllActive ? allIds.length : selected) === 0;
    if (headerDeleteBtn) headerDeleteBtn.style.display = (selectAllActive ? allIds.length : selected) > 0 ? 'inline-flex' : 'none';
    if (selectAll) {
      if (selectAllActive) {
        selectAll.checked = true;
        selectAll.indeterminate = false;
      } else {
        selectAll.checked = checks.length > 0 && selected === checks.length;
        selectAll.indeterminate = selected > 0 && selected < checks.length;
      }
    }
    if (selectAllTotalBtn) selectAllTotalBtn.disabled = total === 0;
    if (selectAllBar) {
      if (selectAllActive) {
        selectAllBar.style.display = 'flex';
        selectAllBarText.textContent = 'تم تحديد ' + allIds.length + ' من أصل ' + total + ' عبر جميع الصفحات — يمكنك الآن الحذف أو إلغاء التحديد';
      } else {
        selectAllBar.style.display = 'none';
      }
    }
  }

  function loadAllIds() {
    if (selectAllTotalBtn) selectAllTotalBtn.disabled = true;
    fetch(URLS.bulkIds + '?' + getFormParams(), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        allIds = data.ids || [];
        if (data.truncated) {
          alert('النتائج كبيرة جداً — تم تحميل ' + allIds.length + ' معرّف فقط. ضيّق البحث أو رشّح بالقسم لتحديد الكل.');
        }
        selectAllActive = true;
        getChecks().forEach(function (c) { c.checked = true; });
        update();
      })
      .catch(function () {
        alert('تعذر تحميل قائمة المعرفات، حاول مجدداً');
      })
      .finally(function () {
        if (selectAllTotalBtn) selectAllTotalBtn.disabled = false;
      });
  }

  if (selectAll) {
    selectAll.addEventListener('change', function () {
      var checks = getChecks();
      if (selectAll.checked) {
        checks.forEach(function (c) { c.checked = true; });
      } else {
        selectAllActive = false;
        allIds = [];
        checks.forEach(function (c) { c.checked = false; });
      }
      update();
    });
  }

  if (selectAllTotalBtn) {
    selectAllTotalBtn.addEventListener('click', function () {
      loadAllIds();
    });
  }

  bindChecks();

  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      selectAllActive = false;
      allIds = [];
      getChecks().forEach(function (c) { c.checked = false; });
      update();
    });
  }

  function buildSelectedIds() {
    if (selectAllActive) return allIds.slice();
    var ids = [];
    getChecks().forEach(function (c) {
      if (c.checked) ids.push(c.value);
    });
    return ids;
  }

  function appendHiddenIds(ids) {
    ids.forEach(function (id) {
      var hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'teacher_ids';
      hidden.value = id;
      form.appendChild(hidden);
    });
  }

  if (headerDeleteBtn) {
    headerDeleteBtn.addEventListener('click', function () {
      var ids = buildSelectedIds();
      if (ids.length === 0) return;
      appendHiddenIds(ids);
      window.askConfirm({
        message: 'حذف الأعضاء المحددين؟',
        onConfirm: function () {
          if (form.dataset.submitted) return;
          form.dataset.submitted = '1';
          form.submit();
        }
      });
    });
  }

  if (deleteBtn) {
    deleteBtn.addEventListener('click', function (e) {
      e.preventDefault();
      var ids = buildSelectedIds();
      if (ids.length === 0) return;
      appendHiddenIds(ids);
      window.askConfirm({
        message: 'حذف الأعضاء المحددين؟',
        onConfirm: function () {
          if (form.dataset.submitted) return;
          form.dataset.submitted = '1';
          form.submit();
        }
      });
    });
  }

  if (form) {
    form.addEventListener('submit', function (e) {
      var selectedIds = buildSelectedIds();
      if (selectedIds.length === 0) {
        e.preventDefault();
        return false;
      }
      appendHiddenIds(selectedIds);
    });
  }

  // /  بعد كل بحث AJAX: مجموعة نتائج جديدة تُبطل التحديد السابق
  window.syncTeacherBulk = function () {
    selectAllActive = false;
    allIds = [];
    bindChecks();
    update();
  };

  bindChecks();
  update();
})();
