/* SPA.history — audit log view. */
(function () {
  'use strict';

  var S = window.SPA;
  var E = S.escapeHtml;

  function renderHistory(el) {
    el.innerHTML =
      '<div class="mb-5"><h1 class="text-2xl font-bold text-on-surface">سجل التغييرات</h1>' +
      '<p class="text-sm text-on-surface-variant mt-1">تتبع جميع التعديلات في النظام</p></div>' +
      '<div class="bg-white rounded-xl border border-outline shadow-sm">' +
      '<div class="p-3 border-b border-outline-variant">' +
      '<div class="relative">' +
      '<span class="material-symbols-outlined absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">search</span>' +
      '<input id="spa-history-search" type="text" placeholder="بحث في السجل…" class="w-full pr-10 pl-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary">' +
      '</div></div>' +
      '<div id="spa-history-table" class="overflow-x-auto"></div>' +
      '<div id="spa-history-pager" class="p-3 border-t border-outline-variant"></div></div>';

    var search = document.getElementById('spa-history-search');
    var timer = null;
    search.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(function () { loadPage(1); }, 300); });
    loadPage(1);
  }

  function loadPage(page) {
    var q = ((document.getElementById('spa-history-search') || {}).value || '').trim();
    var url = '/api/history?page=' + page;
    if (q) url += '&search=' + encodeURIComponent(q);
    var table = document.getElementById('spa-history-table');
    table.innerHTML = '<div class="p-10 text-center text-sm">جاري التحميل…</div>';
    S.api.get(url).then(function (data) {
      renderTable(table, data.items || []);
      renderPager(data, page);
    }).catch(function (err) {
      table.innerHTML = '<div class="p-10 text-center text-error text-sm font-bold">' + E(err.message) + '</div>';
    });
  }

  function renderTable(table, items) {
    if (!items.length) {
      table.innerHTML = '<div class="p-10 text-center text-on-surface-variant text-sm">لا يوجد سجل</div>';
      return;
    }
    var actionIcons = {
      create: 'add_circle',
      update: 'edit',
      delete: 'delete',
      login: 'login',
      restore: 'unarchive'
    };
    var actionColors = {
      create: 'text-emerald-600',
      update: 'text-blue-600',
      delete: 'text-error',
      login: 'text-purple-600',
      restore: 'text-amber-600'
    };
    var rows = items.map(function (h) {
      var icon = actionIcons[h.action] || 'info';
      var color = actionColors[h.action] || 'text-on-surface-variant';
      return '<tr class="border-b border-outline-variant hover:bg-surface-hover">' +
        '<td class="p-3"><span class="material-symbols-outlined text-lg ' + color + '">' + icon + '</span></td>' +
        '<td class="p-3 font-bold text-on-surface">' + E(h.username || h.user_name || '—') + '</td>' +
        '<td class="p-3 text-on-surface-variant">' + E(h.entity_type || h.type || '—') + '</td>' +
        '<td class="p-3 text-on-surface-variant">' + E(h.message || h.description || '—') + '</td>' +
        '<td class="p-3 text-on-surface-variant text-xs">' + E(h.created_at || h.timestamp || '') + '</td>' +
        '</tr>';
    }).join('');
    table.innerHTML = '<table class="w-full text-right text-sm">' +
      '<thead><tr class="text-on-surface-variant border-b border-outline-variant bg-surface">' +
      '<th class="p-3 w-10"></th><th class="p-3 font-bold">المستخدم</th><th class="p-3 font-bold">النوع</th><th class="p-3 font-bold">الوصف</th><th class="p-3 font-bold">التاريخ</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function renderPager(data, page) {
    var totalPages = Math.max(1, Math.ceil((data.total || 0) / (data.per_page || 20)));
    var pager = document.getElementById('spa-history-pager');
    if (!pager) return;
    pager.innerHTML = '<div class="flex items-center justify-end gap-1">' +
      '<button class="spa-icon-btn" data-pg="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + '><span class="material-symbols-outlined text-lg">chevron_right</span></button>' +
      '<span class="px-2 text-sm text-on-surface-variant">' + page + '/' + totalPages + '</span>' +
      '<button class="spa-icon-btn" data-pg="' + (page + 1) + '"' + (page >= totalPages ? ' disabled' : '') + '><span class="material-symbols-outlined text-lg">chevron_left</span></button></div>';
    pager.querySelectorAll('[data-pg]').forEach(function (b) {
      if (!b.disabled) b.addEventListener('click', function () { loadPage(+b.dataset.pg); });
    });
  }

  window.SPA.VIEWS.history = renderHistory;
})();
