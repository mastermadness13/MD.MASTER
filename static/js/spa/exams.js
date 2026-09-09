/* SPA.exams — exams workspace. */
(function () {
  'use strict';

  var S = window.SPA;
  var E = S.escapeHtml;

  var currentTab = 'schedule';

  function renderExams(el) {
    el.innerHTML =
      '<div class="mb-5"><h1 class="text-2xl font-bold text-on-surface">الامتحانات</h1>' +
      '<p class="text-sm text-on-surface-variant mt-1">إدارة جدولة وتنظيم الامتحانات</p></div>' +
      '<div class="flex items-center gap-1 border-b border-outline-variant mb-4 overflow-x-auto">' +
      tabBtn('schedule', 'الجدول') +
      tabBtn('period', 'فترة الامتحانات') +
      '</div>' +
      '<div id="spa-exam-content" class="bg-white rounded-xl border border-outline shadow-sm p-4">جاري التحميل…</div>';

    el.querySelectorAll('[data-tab]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        currentTab = btn.dataset.tab;
        el.querySelectorAll('[data-tab]').forEach(function (b) {
          b.className = b.dataset.tab === currentTab
            ? 'px-4 py-2 text-sm font-bold text-primary border-b-2 border-primary whitespace-nowrap'
            : 'px-4 py-2 text-sm font-bold text-on-surface-variant hover:text-primary whitespace-nowrap';
        });
        loadTab();
      });
    });

    loadTab();
  }

  function tabBtn(key, label) {
    return '<button data-tab="' + key + '" class="' +
      (key === currentTab ? 'text-primary border-b-2 border-primary' : 'text-on-surface-variant hover:text-primary') +
      ' px-4 py-2 text-sm font-bold whitespace-nowrap">' + label + '</button>';
  }

  function loadTab() {
    var box = document.getElementById('spa-exam-content');
    box.innerHTML = '<div class="text-center py-10 text-sm">جاري التحميل…</div>';

    switch (currentTab) {
      case 'schedule': loadSchedule(box); break;
      case 'period': loadPeriod(box); break;
      default: box.innerHTML = '<div class="text-center py-10 text-sm">قريباً</div>';
    }
  }

  function loadSchedule(box) {
    S.api.get('/api/exams/schedule').then(function (data) {
      var exams = data.items || data.schedules || data || [];
      if (!exams.length) {
        box.innerHTML = '<div class="text-center py-10 text-on-surface-variant text-sm">لا يوجد جدول امتحانات بعد</div>';
        return;
      }
      var rows = exams.map(function (e) {
        return '<tr class="border-b border-outline-variant hover:bg-surface-hover">' +
          '<td class="p-3 font-bold">' + E(e.course_name || e.course || '') + '</td>' +
          '<td class="p-3">' + E(e.teacher_name || '—') + '</td>' +
          '<td class="p-3">' + E(e.room_name || e.room || '—') + '</td>' +
          '<td class="p-3">' + E(e.date || '—') + '</td>' +
          '<td class="p-3">' + E(e.start_time || '') + ' - ' + E(e.end_time || '') + '</td>' +
          '</tr>';
      }).join('');
      box.innerHTML = '<table class="w-full text-right text-sm">' +
        '<thead><tr class="text-on-surface-variant border-b border-outline-variant bg-surface">' +
        '<th class="p-3 font-bold">المقرر</th><th class="p-3 font-bold">عضو هيئة التدريس</th><th class="p-3 font-bold">القاعة</th><th class="p-3 font-bold">التاريخ</th><th class="p-3 font-bold">الوقت</th>' +
        '</tr></thead><tbody>' + rows + '</tbody></table>';
    }).catch(function (err) {
      box.innerHTML = '<div class="text-center py-10 text-error text-sm font-bold">' + E(err.message) + '</div>';
    });
  }

  function loadPeriod(box) {
    S.api.get('/api/exams/period').then(function (data) {
      var p = data || {};
      box.innerHTML = '<form id="spa-exam-period-form" class="max-w-lg space-y-4">' +
        '<h3 class="font-bold text-on-surface">فترة الامتحانات</h3>' +
        ff('start_date', 'تاريخ البداية', 'date', p.start_date) +
        ff('end_date', 'تاريخ النهاية', 'date', p.end_date) +
        ff('first_session', 'الحصة الأولى', 'time', p.first_session || '08:00') +
        ff('second_session', 'الحصة الثانية', 'time', p.second_session || '11:00') +
        ff('third_session', 'الحصة الثالثة', 'time', p.third_session || '14:00') +
        '<div class="flex items-center justify-end gap-3 pt-4">' +
        '<button type="submit" class="px-5 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold hover:opacity-90">' +
        '<span class="material-symbols-outlined text-lg align-middle">save</span> حفظ</button></div></form>';
      box.querySelector('#spa-exam-period-form').addEventListener('submit', function (e) {
        e.preventDefault();
        var fd = new FormData(e.target);
        var payload = {};
        fd.forEach(function (v, k) { payload[k] = v; });
        S.api.put('/api/exams/period', payload).then(function () {
          showToastSuccess('تم حفظ فترة الامتحانات');
        }).catch(function (err) { showToastError(err.message); });
      });
    }).catch(function (err) {
      box.innerHTML = '<div class="text-center py-10 text-error text-sm font-bold">' + E(err.message) + '</div>';
    });
  }

  function ff(name, label, type, value, extra) {
    extra = extra || {};
    return '<div><label class="block text-sm font-bold mb-1">' + label + '</label>' +
      '<input name="' + name + '" type="' + type + '" value="' + E(value || '') + '"' +
      (extra.min ? ' min="' + extra.min + '"' : '') +
      ' class="w-full px-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary"></div>';
  }

  function can(p) { return ((S.session && S.session.permissions) || []).indexOf(p) !== -1; }

  window.SPA.VIEWS.exams = renderExams;
})();
