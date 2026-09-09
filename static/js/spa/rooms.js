/* SPA.rooms — rooms list + CRUD modals. */
(function () {
  'use strict';

  var S = window.SPA;
  var E = S.escapeHtml;

  function renderList(el) {
    el.innerHTML =
      '<div class="flex items-center justify-between mb-5">' +
      '<div><h1 class="text-2xl font-bold text-on-surface">القاعات</h1>' +
      '<p class="text-sm text-on-surface-variant mt-1">إدارة القاعات والمعامل</p></div>' +
      '<div id="spa-room-actions"></div></div>' +
      '<div class="bg-white rounded-xl border border-outline shadow-sm">' +
      '<div class="p-3 border-b border-outline-variant">' +
      '<div class="relative">' +
      '<span class="material-symbols-outlined absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">search</span>' +
      '<input id="spa-room-search" type="text" placeholder="بحث…" class="w-full pr-10 pl-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary">' +
      '</div></div>' +
      '<div id="spa-room-table" class="overflow-x-auto"></div>' +
      '<div id="spa-room-pager" class="p-3 border-t border-outline-variant"></div></div>';

    if (can('rooms.manage')) {
      document.getElementById('spa-room-actions').innerHTML =
        '<button id="spa-room-add" class="inline-flex items-center gap-2 bg-primary text-on-primary px-4 py-2 rounded-lg font-bold text-sm hover:opacity-90">' +
        '<span class="material-symbols-outlined text-lg">add</span> إضافة قاعة</button>';
      document.getElementById('spa-room-add').addEventListener('click', function () { openForm(); });
    }

    var search = document.getElementById('spa-room-search');
    var timer = null;
    search.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(function () { loadPage(1); }, 300); });
    loadPage(1);
  }

  function loadPage(page) {
    var q = ((document.getElementById('spa-room-search') || {}).value || '').trim();
    var url = '/api/rooms?page=' + page;
    if (q) url += '&search=' + encodeURIComponent(q);
    var table = document.getElementById('spa-room-table');
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
      table.innerHTML = '<div class="p-10 text-center text-on-surface-variant text-sm">لا توجد قاعات</div>';
      return;
    }
    var statusMap = {
      available: '<span class="inline-block px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">متاحة</span>',
      occupied: '<span class="inline-block px-2 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800">مشغولة</span>',
      maintenance: '<span class="inline-block px-2 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800">صيانة</span>'
    };
    var rows = items.map(function (r) {
      var actions = '';
      if (can('rooms.manage')) {
        actions += '<button type="button" class="spa-icon-btn" data-edit="' + r.id + '" title="تعديل"><span class="material-symbols-outlined text-lg">edit</span></button>';
        actions += '<button type="button" class="spa-icon-btn text-error" data-del="' + r.id + '" title="حذف"><span class="material-symbols-outlined text-lg">delete</span></button>';
      }
      return '<tr class="border-b border-outline-variant hover:bg-surface-hover">' +
        '<td class="p-3 font-bold text-on-surface">' + E(r.name || '') + '</td>' +
        '<td class="p-3 text-on-surface-variant">' + E(r.type || '—') + '</td>' +
        '<td class="p-3">' + (statusMap[r.status] || E(r.status || '—')) + '</td>' +
        '<td class="p-3 text-on-surface-variant">' + (r.capacity || '—') + '</td>' +
        '<td class="p-3 text-on-surface-variant">' + E(r.location || '') + '</td>' +
        '<td class="p-3 text-left whitespace-nowrap">' + actions + '</td></tr>';
    }).join('');
    table.innerHTML = '<table class="w-full text-right text-sm">' +
      '<thead><tr class="text-on-surface-variant border-b border-outline-variant bg-surface">' +
      '<th class="p-3 font-bold">الاسم</th><th class="p-3 font-bold">النوع</th><th class="p-3 font-bold">الحالة</th><th class="p-3 font-bold">السعة</th><th class="p-3 font-bold">الموقع</th><th class="p-3 font-bold text-left">إجراءات</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';

    table.querySelectorAll('[data-edit]').forEach(function (b) { b.addEventListener('click', function () { openForm(+b.dataset.edit); }); });
    table.querySelectorAll('[data-del]').forEach(function (b) { b.addEventListener('click', function () { openDelete(+b.dataset.del); }); });
  }

  function renderPager(data, page) {
    var totalPages = Math.max(1, Math.ceil((data.total || 0) / (data.per_page || 20)));
    var pager = document.getElementById('spa-room-pager');
    if (!pager) return;
    pager.innerHTML = '<div class="flex items-center justify-end gap-1">' +
      '<button class="spa-icon-btn" data-pg="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + '><span class="material-symbols-outlined text-lg">chevron_right</span></button>' +
      '<span class="px-2 text-sm text-on-surface-variant">' + page + '/' + totalPages + '</span>' +
      '<button class="spa-icon-btn" data-pg="' + (page + 1) + '"' + (page >= totalPages ? ' disabled' : '') + '><span class="material-symbols-outlined text-lg">chevron_left</span></button></div>';
    pager.querySelectorAll('[data-pg]').forEach(function (b) {
      if (!b.disabled) b.addEventListener('click', function () { loadPage(+b.dataset.pg); });
    });
  }

  function openForm(id) {
    var roomReq = id ? S.api.get('/api/rooms/' + id) : Promise.resolve(null);
    roomReq.then(function (detail) {
      var r = detail ? (detail.room || detail) : {};
      var body = document.createElement('div');
      body.innerHTML = '<form id="spa-room-form"><div class="grid grid-cols-1 sm:grid-cols-2 gap-4">' +
        ff('name', 'اسم القاعة', 'text', r.name, { required: true }) +
        '<div><label class="block text-sm font-bold mb-1">النوع</label>' +
        '<select name="type" class="w-full px-3 py-2 rounded-lg border border-outline text-sm">' +
        '<option value="lecture"' + (r.type === 'lecture' ? ' selected' : '') + '>قاعة محاضرات</option>' +
        '<option value="lab"' + (r.type === 'lab' ? ' selected' : '') + '>معمل</option>' +
        '<option value="hall"' + (r.type === 'hall' ? ' selected' : '') + '>قاعة كبيرة</option>' +
        '<option value="other"' + (r.type === 'other' ? ' selected' : '') + '>أخرى</option></select></div>' +
        '<div><label class="block text-sm font-bold mb-1">الحالة</label>' +
        '<select name="status" class="w-full px-3 py-2 rounded-lg border border-outline text-sm">' +
        '<option value="available"' + (r.status === 'available' || !r.status ? ' selected' : '') + '>متاحة</option>' +
        '<option value="occupied"' + (r.status === 'occupied' ? ' selected' : '') + '>مشغولة</option>' +
        '<option value="maintenance"' + (r.status === 'maintenance' ? ' selected' : '') + '>صيانة</option></select></div>' +
        ff('capacity', 'السعة', 'number', r.capacity, { min: 1 }) +
        ff('location', 'الموقع', 'text', r.location) +
        '</div>' +
        '<div class="mt-6 flex items-center justify-end gap-3">' +
        '<button type="button" class="px-4 py-2 rounded-lg border border-outline text-sm font-bold" data-spa-modal-close>إلغاء</button>' +
        '<button type="submit" class="px-5 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold hover:opacity-90"><span class="material-symbols-outlined text-lg align-middle">save</span> حفظ</button></div></form>';

      S.modal.open({ title: id ? 'تعديل قاعة' : 'إضافة قاعة', body: body });
      body.querySelector('#spa-room-form').addEventListener('submit', function (e) {
        e.preventDefault();
        var fd = new FormData(e.target);
        var payload = {};
        fd.forEach(function (v, k) { payload[k] = v; });
        payload.capacity = parseInt(payload.capacity) || null;
        var promise = id ? S.api.put('/api/rooms/' + id, payload) : S.api.post('/api/rooms', payload);
        promise.then(function () { S.modal.close(); showToastSuccess(id ? 'تم التحديث' : 'تمت الإضافة'); loadPage(1); })
          .catch(function (err) { S.modal.showError(err.message); });
      });
    }).catch(function (err) { S.modal.open({ title: 'خطأ', body: makeErr(err.message) }); });
  }

  function openDelete(id) {
    var body = document.createElement('div');
    body.innerHTML = '<p class="text-sm">هل أنت متأكد من حذف هذه القاعة؟</p>' +
      '<div class="mt-5 flex items-center justify-end gap-3">' +
      '<button type="button" class="px-4 py-2 rounded-lg border border-outline text-sm font-bold" data-spa-modal-close>إلغاء</button>' +
      '<button type="button" class="px-5 py-2 rounded-lg bg-error text-on-primary text-sm font-bold" id="spa-room-del">حذف</button></div>';
    S.modal.open({ title: 'حذف قاعة', body: body });
    document.getElementById('spa-room-del').addEventListener('click', function () {
      S.api.del('/api/rooms/' + id).then(function () { S.modal.close(); showToastSuccess('تم الحذف'); loadPage(1); })
        .catch(function (err) { S.modal.showError(err.message); });
    });
  }

  function ff(name, label, type, value, extra) {
    extra = extra || {};
    return '<div><label class="block text-sm font-bold mb-1">' + label + (extra.required ? ' <span class="text-error">*</span>' : '') + '</label>' +
      '<input name="' + name + '" type="' + type + '" value="' + E(value || '') + '"' +
      (extra.required ? ' required' : '') + (extra.min ? ' min="' + extra.min + '"' : '') +
      ' class="w-full px-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary"></div>';
  }

  function makeErr(msg) { var el = document.createElement('div'); el.className = 'text-error font-bold text-sm'; el.textContent = msg; return el; }
  function can(p) { return ((S.session && S.session.permissions) || []).indexOf(p) !== -1; }

  window.SPA.VIEWS.rooms = renderList;
})();