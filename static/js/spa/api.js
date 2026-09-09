/* SPA.api — thin fetch wrapper for the REST API.
   Handles the JSON envelope ({ok, data}), the CSRF header, and error display. */
(function () {
  'use strict';

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  async function request(method, url, data) {
    var headers = { 'X-CSRFToken': csrfToken() };
    var opts = { method: method, credentials: 'same-origin', headers: headers };
    if (data !== undefined) {
      headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(data);
    }
    var res = await fetch(url, opts);
    var payload = null;
    try { payload = await res.json(); } catch (e) { /* non-JSON body */ }
    if (!res.ok || !payload || payload.ok === false) {
      var error = new Error((payload && payload.message) || 'حدث خطأ غير متوقع');
      error.status = res.status;
      if (res.status === 401) {
        window.location.hash = '';
        window.location.reload();
      }
      throw error;
    }
    return payload.data;
  }

  window.SPA = window.SPA || {};
  window.SPA.api = {
    get: function (url) { return request('GET', url); },
    post: function (url, data) { return request('POST', url, data); },
    put: function (url, data) { return request('PUT', url, data); },
    del: function (url) { return request('DELETE', url); }
  };
})();
