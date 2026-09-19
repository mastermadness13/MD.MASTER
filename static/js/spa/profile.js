/* SPA.profile — user profile / settings. */
(function () {
  'use strict';

  var S = window.SPA;
  var E = S.escapeHtml;

  function renderProfile(el) {
    el.innerHTML =
      '<div class="mb-5"><h1 class="text-2xl font-bold text-on-surface">ملفي الشخصي</h1>' +
      '<p class="text-sm text-on-surface-variant mt-1">عرض وتعديل بياناتك</p></div>' +
      '<div class="max-w-2xl">' +
      '<div id="spa-profile-view" class="bg-white rounded-xl border border-outline shadow-sm p-6">جاري التحميل…</div>' +
      '</div>';

    loadProfile();
  }

  function loadProfile() {
    var box = document.getElementById('spa-profile-view');
    S.api.get('/api/auth/me').then(function (data) {
      var user = data.user || {};
      box.innerHTML =
        '<div class="flex items-center gap-4 mb-6">' +
        '<div class="w-16 h-16 rounded-full bg-primary flex items-center justify-center text-on-primary font-bold text-2xl">' +
        E((user.label || user.username || '').substring(0, 1)) + '</div>' +
        '<div><div class="text-xl font-bold text-on-surface">' + E(user.label || user.username) + '</div>' +
        '<div class="text-sm text-on-surface-variant">' + E(data.role_label || '') + '</div></div></div>' +
        '<dl class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm mb-6">' +
        f('اسم المستخدم', user.username) +
        f('البريد الإلكتروني', user.email) +
        f('الهاتف', user.phone) +
        f('القسم', user.department_name || '—') +
        '</dl>' +
        '<div class="border-t border-outline-variant pt-4">' +
        '<h3 class="font-bold text-on-surface mb-3">تغيير كلمة المرور</h3>' +
        '<form id="spa-profile-pass" class="space-y-3">' +
        '<div><label class="block text-sm font-bold mb-1">كلمة المرور الحالية</label>' +
        '<input name="current_password" type="password" required class="w-full px-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary"></div>' +
        '<div><label class="block text-sm font-bold mb-1">كلمة المرور الجديدة</label>' +
        '<input name="new_password" type="password" required minlength="8" class="w-full px-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary"></div>' +
        '<div><label class="block text-sm font-bold mb-1">تأكيد كلمة المرور</label>' +
        '<input name="confirm_password" type="password" required minlength="8" class="w-full px-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary"></div>' +
        '<div class="flex justify-end"><button type="submit" class="px-5 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold hover:opacity-90">' +
        '<span class="material-symbols-outlined text-lg align-middle">save</span> حفظ</button></div></form></div>';

      box.querySelector('#spa-profile-pass').addEventListener('submit', function (e) {
        e.preventDefault();
        var fd = new FormData(e.target);
        var payload = {
          current_password: fd.get('current_password'),
          new_password: fd.get('new_password'),
          confirm_password: fd.get('confirm_password')
        };
        if (payload.new_password !== payload.confirm_password) {
          showToastError('كلمتا المرور غير متطابقتين');
          return;
        }
        if (payload.new_password.length < 8) {
          showToastError('كلمة المرور يجب أن تكون 8 أحرف على الأقل');
          return;
        }
        if (!/[A-Z]/.test(payload.new_password) || !/[a-z]/.test(payload.new_password) || !/\d/.test(payload.new_password)) {
          showToastError('كلمة المرور يجب أن تحتوي على حرف كبير وصغير ورقم');
          return;
        }
        fetch('/change-password', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'X-CSRFToken': getCsrf(),
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            current_password: payload.current_password,
            new_password: payload.new_password,
            confirm_password: payload.confirm_password
          })
        }).then(function (res) { return res.json().catch(function () { return null; }); })
          .then(function (data) {
            if (data && data.ok === false) { showToastError(data.message || 'خطأ'); return; }
            if (data && data.ok === true) {
              showToastSuccess('تم تغيير كلمة المرور بنجاح');
              e.target.reset();
              return;
            }
            showToastError('تعذر تغيير كلمة المرور، حاول مجدداً');
          }).catch(function (err) { showToastError(err.message || 'خطأ'); });
      });
    }).catch(function (err) {
      box.innerHTML = '<div class="text-center py-10 text-error text-sm font-bold">' + E(err.message) + '</div>';
    });
  }

  function f(label, value) {
    return '<div><dt class="text-xs text-on-surface-variant font-bold">' + label + '</dt><dd class="font-semibold text-on-surface mt-0.5">' + E(value || '—') + '</dd></div>';
  }

  function getCsrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  window.SPA.VIEWS.profile = renderProfile;
})();
