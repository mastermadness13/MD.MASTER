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

  var CSRF_FIELD = '[name="_csrf_token"]';

  function csrfTokenOf(form) {
    var field = form ? form.querySelector(CSRF_FIELD) : null;
    return field ? field.value : '';
  }

  function setFeedback(text, tone) {
    if (!feedback) return;
    feedback.textContent = text;
    feedback.className = tone === 'error'
      ? 'text-sm font-semibold text-error'
      : 'text-sm font-semibold text-success';
  }

  // A server-side HTML answer (login page, error page, redirect target) must
  // never reach JSON.parse: that raises "Unexpected token '<'" in the console
  // and hides the real reason from the user.
  function looksLikeHtml(text) {
    return /^\s*(<!doctype|<html)/i.test(text);
  }

  function wantsLogin(text) {
    if (looksLikeHtml(text)) {
      return /name=["']?(password|username)/i.test(text) ||
        /تسجيل الدخول|auth\/login/i.test(text);
    }
    return false;
  }

  async function readJsonResponse(response) {
    var contentType = (response.headers.get('content-type') || '').toLowerCase();
    var text = await response.text();
    if (!contentType.includes('application/json')) {
      throw new Error(
        wantsLogin(text)
          ? 'انتهت جلسة الدخول. أعد تحميل الصفحة وسجّل الدخول مجدداً.'
          : 'استجابة غير صالحة من الخادم (' + response.status + '). أعد تحميل الصفحة وحاول مجدداً.'
      );
    }
    try {
      return JSON.parse(text);
    } catch (error) {
      throw new Error('تعذر قراءة استجابة الخادم. حاول مجدداً.');
    }
  }

  async function refreshValues(focusId) {
    var searchValue = search ? search.value : '';
    var statusValue = statusFilter ? statusFilter.value : 'all';
    var response = await fetch(window.location.href, {
      headers: { 'Accept': 'text/html' },
      credentials: 'same-origin'
    });
    if (!response.ok) throw new Error('تعذر تحديث قائمة القيم (' + response.status + ').');
    var pageHtml = await response.text();
    var page = new DOMParser().parseFromString(pageHtml, 'text/html');
    var refreshedValues = page.getElementById('lookup-values');
    if (!refreshedValues) {
      throw new Error(
        wantsLogin(pageHtml)
          ? 'انتهت جلسة الدخول. أعد تحميل الصفحة وسجّل الدخول مجدداً.'
          : 'لم تصل قائمة القيم من الخادم. أعد تحميل الصفحة وحاول مجدداً.'
      );
    }
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
    if (form.dataset.pending === '1') return;
    var submitButton = form.querySelector('button[type="submit"]');
    if (submitButton && submitButton.disabled) return;
    form.dataset.pending = '1';
    if (submitButton) submitButton.disabled = true;
    if (feedback) {
      feedback.textContent = 'جارٍ الحفظ...';
      feedback.className = 'text-sm text-on-surface-variant';
    }

    var token = csrfTokenOf(form);
    var headers = {
      'X-Requested-With': 'XMLHttpRequest',
      'Accept': 'application/json'
    };
    if (token) headers['X-CSRFToken'] = token;

    try {
      var actionUrl = form.getAttribute('action') || window.location.href;
      var response = await fetch(actionUrl, {
        method: 'POST',
        headers: headers,
        body: new FormData(form),
        credentials: 'same-origin'
      });
      var result = await readJsonResponse(response);
      if (!response.ok || !result.ok) {
        var failure = new Error(result.message || 'تعذر حفظ التغيير.');
        if (response.status === 401 || response.status === 403) {
          failure.message += ' — أعد تحميل الصفحة وسجّل الدخول مجدداً.';
        }
        throw failure;
      }

      if (form.id === 'lookupAddForm') form.reset();
      var row = form.closest('[data-lookup-row]');
      var focusId = row ? row.dataset.id : '';
      await refreshValues(focusId);
      setFeedback(result.message || 'تم الحفظ بنجاح.', 'success');
    } catch (error) {
      setFeedback(error && error.message ? error.message : 'تعذر الاتصال بالخادم. حاول مجددًا.', 'error');
    } finally {
      form.dataset.pending = '0';
      if (submitButton && submitButton.isConnected) submitButton.disabled = false;
    }
  });

  filterRows();
})();
