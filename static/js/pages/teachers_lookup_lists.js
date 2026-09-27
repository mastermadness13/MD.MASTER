(function () {
  var values = document.getElementById('lookup-values');
  if (!values) return;

  var categorySelect = document.getElementById('lookupCategorySelect');
  var search = document.getElementById('lookupSearch');
  var statusFilter = document.getElementById('lookupStatusFilter');
  var feedback = document.getElementById('lookupFeedback');

  if (categorySelect) {
    categorySelect.addEventListener('change', function () {
      var url = new URL(window.location.href);
      url.searchParams.set('category', categorySelect.value);
      window.location.assign(url.toString());
    });
  }

  function editRow(form) {
    if (!form || form.dataset.editing === 'true') return;
    var name = form.querySelector('[data-lookup-name]');
    var input = form.querySelector('[name="name"]');
    var edit = form.querySelector('[data-lookup-edit]');
    var save = form.querySelector('[data-lookup-save]');
    var cancel = form.querySelector('[data-lookup-cancel]');
    if (!name || !input || !save || !cancel) return;
    input.dataset.originalValue = input.value;
    form.dataset.editing = 'true';
    name.classList.add('hidden');
    input.classList.remove('hidden');
    if (edit) edit.classList.add('hidden');
    save.classList.remove('hidden');
    cancel.classList.remove('hidden');
    input.focus();
    input.select();
  }

  function cancelRowEdit(form) {
    if (!form) return;
    var name = form.querySelector('[data-lookup-name]');
    var input = form.querySelector('[name="name"]');
    var edit = form.querySelector('[data-lookup-edit]');
    var save = form.querySelector('[data-lookup-save]');
    var cancel = form.querySelector('[data-lookup-cancel]');
    if (!name || !input || !save || !cancel) return;
    input.value = input.dataset.originalValue || '';
    form.dataset.editing = 'false';
    name.classList.remove('hidden');
    input.classList.add('hidden');
    if (edit) edit.classList.remove('hidden');
    save.classList.add('hidden');
    cancel.classList.add('hidden');
  }

  document.addEventListener('click', function (event) {
    var target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    var editButton = target.closest('[data-lookup-edit]');
    if (editButton) {
      editRow(editButton.closest('form[data-lookup-rename]'));
      return;
    }
    var cancelButton = target.closest('[data-lookup-cancel]');
    if (cancelButton) cancelRowEdit(cancelButton.closest('form[data-lookup-rename]'));
  });

  document.addEventListener('dblclick', function (event) {
    var target = event.target instanceof Element ? event.target : null;
    if (target && target.matches('[data-lookup-name]')) {
      editRow(target.closest('form[data-lookup-rename]'));
    }
  });

  document.addEventListener('keydown', function (event) {
    var target = event.target;
    if (!(target instanceof HTMLInputElement) || !target.closest('[data-lookup-rename]')) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      var form = target.closest('form[data-lookup-rename]');
      cancelRowEdit(form);
      form.querySelector('[data-lookup-name]').focus();
    }
  });

  function filterRows() {
    var query = search ? search.value.trim().toLocaleLowerCase() : '';
    var status = statusFilter ? statusFilter.value : 'all';
    var rows = values.querySelectorAll('[data-lookup-row]');
    var count = values.querySelector('#lookupResultCount');
    var emptyState = values.querySelector('#lookupEmptyState');
    var visibleCount = 0;

    rows.forEach(function (row) {
      var matchesQuery = !query || (row.dataset.search || '').toLocaleLowerCase().includes(query);
      var matchesStatus = status === 'all' ||
        (status === 'active' && row.dataset.active === '1') ||
        (status === 'inactive' && row.dataset.active === '0') ||
        (status === 'system' && row.dataset.system === '1') ||
        (status === 'general' && row.dataset.system === '0');
      var visible = matchesQuery && matchesStatus;
      row.classList.toggle('hidden', !visible);
      if (visible) visibleCount += 1;
    });

    if (count) count.textContent = visibleCount + ' من ' + rows.length + ' قيمة';
    if (emptyState) emptyState.classList.toggle('hidden', visibleCount > 0 || rows.length === 0);
  }

  async function refreshValues(focusId) {
    var searchValue = search ? search.value : '';
    var statusValue = statusFilter ? statusFilter.value : 'all';
    var response = await fetch(window.location.href, {
      headers: { 'Accept': 'text/html' },
      credentials: 'same-origin'
    });
    if (!response.ok) throw new Error('تعذر تحديث قائمة التكليفات.');
    var page = new DOMParser().parseFromString(await response.text(), 'text/html');
    var refreshedValues = page.getElementById('lookup-values');
    if (!refreshedValues) throw new Error('لم تصل قائمة التكليفات من الخادم.');
    values.replaceWith(refreshedValues);
    values = refreshedValues;
    search = document.getElementById('lookupSearch');
    statusFilter = document.getElementById('lookupStatusFilter');
    if (search) search.value = searchValue;
    if (statusFilter) statusFilter.value = statusValue;
    filterRows();
    if (focusId) {
      var refreshedRow = values.querySelector('[data-id="' + focusId + '"]');
      var refreshedEditButton = refreshedRow && refreshedRow.querySelector('[data-lookup-edit]');
      if (refreshedEditButton) refreshedEditButton.focus();
    }
  }

  document.addEventListener('input', function (event) {
    if (event.target === search) filterRows();
  });

  document.addEventListener('change', function (event) {
    if (event.target === statusFilter) filterRows();
  });

  document.addEventListener('submit', async function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute('data-lookup-ajax')) return;

    event.preventDefault();
    var submitButton = form.querySelector('button[type="submit"]');
    if (submitButton && submitButton.disabled) return;
    if (submitButton) submitButton.disabled = true;
    if (feedback) {
      feedback.textContent = 'جارٍ الحفظ...';
      feedback.className = 'text-sm text-on-surface-variant';
    }

    try {
      var response = await fetch(form.action || window.location.href, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
        body: new FormData(form),
        credentials: 'same-origin'
      });
      var result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.message || 'تعذر حفظ التغيير.');
      }

      if (form.id === 'lookupAddForm') form.reset();
      var row = form.closest('[data-lookup-row]');
      var focusId = row ? row.dataset.id : '';
      await refreshValues(focusId);
      if (feedback) {
        feedback.textContent = result.message || 'تم الحفظ بنجاح.';
        feedback.className = 'text-sm font-semibold text-success';
      }
    } catch (error) {
      if (feedback) {
        feedback.textContent = error.message || 'تعذر الاتصال بالخادم. حاول مجددًا.';
        feedback.className = 'text-sm font-semibold text-error';
      }
    } finally {
      if (submitButton && submitButton.isConnected) submitButton.disabled = false;
    }
  });

  filterRows();
})();
