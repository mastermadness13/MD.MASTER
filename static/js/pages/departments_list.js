/* Deleting a major (شعبة) is a JSON DELETE endpoint, not a form post, so the
   control is a plain button handled here. Only rendered for departments.manage;
   the bind below is a no-op for read-only roles. The buttons are re-bound from
   SearchComponent's onComplete because the search swap replaces the table body
   via innerHTML, which drops the listeners attached to the old nodes. */
(function () {
  'use strict';

  var meta = document.querySelector('meta[name="csrf-token"]');
  var csrfToken = meta ? meta.getAttribute('content') : '';

  function notify(message, type) {
    if (typeof window.showNotification === 'function') {
      window.showNotification(message, type || 'success');
    }
  }

  function removeMajor(deptId, majorId) {
    var url = '/api/departments/' + deptId + '/majors/' + majorId;
    return fetch(url, {
      method: 'DELETE',
      headers: { 'X-CSRFToken': csrfToken },
      credentials: 'same-origin'
    }).then(function (resp) {
      return resp.json().catch(function () {
        return { ok: false, message: 'استجابة غير متوقعة من الخادم.' };
      }).then(function (data) {
        if (!data.ok) {
          throw new Error(data.message || 'تعذّر حذف الشعبة');
        }
        return data;
      });
    });
  }

  function bind() {
    var buttons = document.querySelectorAll('.delete-major-btn');
    Array.prototype.forEach.call(buttons, function (btn) {
      if (btn.getAttribute('data-bound') === '1') return;
      btn.setAttribute('data-bound', '1');
      btn.addEventListener('click', function () {
        var deptId = btn.getAttribute('data-dept-id');
        var majorId = btn.getAttribute('data-major-id');
        var run = function () {
          btn.disabled = true;
          removeMajor(deptId, majorId).then(function () {
            window.location.reload();
          }).catch(function (err) {
            btn.disabled = false;
            notify(err.message, 'error');
          });
        };
        if (typeof window.askConfirm === 'function') {
          window.askConfirm({
            title: 'حذف الشعبة',
            message: 'تأكيد حذف الشعبة؟',
            label: 'حذف',
            danger: true,
            onConfirm: run
          });
        } else {
          run();
        }
      });
    });
  }

  window.departmentsList = window.departmentsList || {};
  window.departmentsList.bindMajorDelete = bind;

  SearchComponent.init({
    formSelector: '#departmentsSearchForm',
    inputSelector: '.search-input',
    tableSelector: '.search-table',
    countSelector: '.search-results-count',
    clearSelector: '.search-clear',
    spinnerSelector: '.search-spinner',
    paginationSelector: '.search-pagination',
    debounceMs: 300,
    onComplete: bind
  });

  bind();
})();
