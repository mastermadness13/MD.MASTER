/**
 * Exams workspace API client — thin fetch wrapper around /api/exams/*.
 * Unwraps the standard envelope {ok, data}; throws Error(message) on failure.
 */
(function () {
  'use strict';

  var csrfToken = (function () {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  })();

  function parse(resp) {
    return resp.json().catch(function () {
      return { ok: false, message: 'استجابة غير متوقعة من الخادم.' };
    });
  }

  function request(method, path, body) {
    var headers = { 'X-CSRFToken': csrfToken };
    var opts = { method: method, headers: headers, credentials: 'same-origin' };
    if (body !== undefined && body !== null) {
      if (body instanceof FormData) {
        opts.body = body;
      } else {
        headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
    }
    return fetch(path, opts).then(function (resp) {
      return parse(resp).then(function (data) {
        if (resp.status === 401) {
          window.location.href = '/login';
          throw new Error('جلسة منتهية، يرجى تسجيل الدخول');
        }
        if (!data.ok) {
          throw new Error(data.message || 'حدث خطأ في العملية');
        }
        return data.data;
      });
    });
  }

  window.Exams = window.Exams || {};
  window.Exams.api = {
    get: function (path) { return request('GET', path); },
    post: function (path, body) { return request('POST', path, body); },
    put: function (path, body) { return request('PUT', path, body); },
    patch: function (path, body) { return request('PATCH', path, body); },
    del: function (path) { return request('DELETE', path); },
    csrf: csrfToken
  };
})();
