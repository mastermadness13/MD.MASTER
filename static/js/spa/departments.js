/* SPA.departments — departments list + CRUD modals. */
(function () {
  'use strict';

  var S = window.SPA;
  var E = S.escapeHtml;

  function renderList(el) {
    el.innerHTML =
      '<div class="flex items-center justify-between mb-5">' +
      '<div><h1 class="text-2xl font-bold text-on-surface">الأقسام</h1>' +
      '<p class="text-sm text-on-surface-variant mt-1">إدارة الأقسام الكلية والإدارية</p></div>' +
      '<div id="spa-dept-actions"></div></div>' +
      '<div class="bg-white rounded-xl border border-outline shadow-sm">' +
      '<div class="p-3 border-b border-outline-variant flex flex-wrap items-center gap-3">' +
      '<div class="relative flex-1 min-w-[200px]">' +
      '<span class="material-symbols-outlined absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">search</span>' +
      '<input id="spa-dept-search" type="text" placeholder="بحث بالاسم…" class="w-full pr-10 pl-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary">' +
      '</div>' +
      '<select id="spa-dept-type" class="px-3 py-2 rounded-lg border border-outline text-sm">' +
      '<option value="">الكل</option><option value="academic">كلية</option><option value="administrative">إداري</option>' +
      '</select>' +
      '</div>' +
      '<div id="spa-dept-table" class="overflow-x-auto"></div>' +
      '<div id="spa-dept-pager" class="p-3 border-t border-outline-variant"></div></div>';

    if (can('departments.manage')) {
      document.getElementById('spa-dept-actions').innerHTML =
        '<button id="spa-dept-add" class="inline-flex items-center gap-2 bg-primary text-on-primary px-4 py-2 rounded-lg font-bold text-sm hover:opacity-90">' +
        '<span class="material-symbols-outlined text-lg">add</span> إضافة قسم</button>';
      document.getElementById('spa-dept-add').addEventListener('click', function () { openForm(); });
    }

    var search = document.getElementById('spa-dept-search');
    var typeFilter = document.getElementById('spa-dept-type');
    var timer = null;
    function reload() { clearTimeout(timer); timer = setTimeout(function () { loadPage(1); }, 300); }
    search.addEventListener('input', reload);
    typeFilter.addEventListener('change', function () { loadPage(1); });

    function loadPage(page) {
      var q = search.value.trim();
      var type = typeFilter.value;
      var url = '/api/departments?page=' + page;
      if (q) url += '&search=' + encodeURIComponent(q);
      if (type) url += '&type=' + encodeURIComponent(type);
      var table = document.getElementById('spa-dept-table');
      table.innerHTML = '<div class="p-10 text-center text-on-surface-variant text-sm">جاري التحميل…</div>';
      S.api.get(url).then(function (data) {
        renderTable(table, data.items || []);
        renderPager(data, page, q, type);
      }).catch(function (err) {
        table.innerHTML = '<div class="p-10 text-center text-error text-sm font-bold">' + E(err.message) + '</div>';
      });
    }

    loadPage(1);
  }

  function renderTable(table, items) {
    if (!items.length) {
      table.innerHTML = '<div class="p-10 text-center text-on-surface-variant text-sm">لا توجد أقسام</div>';
      return;
    }
    var rows = items.map(function (d) {
      var actions = '';
      if (can('departments.manage')) {
        actions += '<button type="button" class="spa-icon-btn" data-edit="' + d.id + '" title="تعديل"><span class="material-symbols-outlined text-lg">edit</span></button>';
        actions += '<button type="button" class="spa-icon-btn text-error" data-del="' + d.id + '" title="حذف"><span class="material-symbols-outlined text-lg">delete</span></button>';
      }
      var typeLabel = d.type === 'academic' ? '<span class="inline-block px-2 py-0.5 rounded-full text-xs font-bold bg-blue-100 text-blue-800">كلية</span>' :
        '<span class="inline-block px-2 py-0.5 rounded-full text-xs font-bold bg-orange-100 text-orange-800">إداري</span>';
      return '<tr class="border-b border-outline-variant hover:bg-surface-hover">' +
        '<td class="p-3 font-bold text-on-surface">' + E(d.name || '') + '</td>' +
        '<td class="p-3">' + typeLabel + '</td>' +
        '<td class="p-3 text-on-surface-variant">' + (d.semesters || 0) + '</td>' +
        '<td class="p-3 text-on-surface-variant">' + (d.major_count || 0) + '</td>' +
        '<td class="p-3 text-left whitespace-nowrap">' + actions + '</td></tr>';
    }).join('');
    table.innerHTML = '<table class="w-full text-right text-sm">' +
      '<thead><tr class="text-on-surface-variant border-b border-outline-variant bg-surface">' +
      '<th class="p-3 font-bold">الاسم</th><th class="p-3 font-bold">النوع</th><th class="p-3 font-bold">الفصول</th><th class="p-3 font-bold">التخصصات</th><th class="p-3 font-bold text-left">إجراءات</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';

    table.querySelectorAll('[data-edit]').forEach(function (b) {
      b.addEventListener('click', function () { openForm(+b.dataset.edit); });
    });
    table.querySelectorAll('[data-del]').forEach(function (b) {
      b.addEventListener('click', function () { openDelete(+b.dataset.del); });
    });

  }

  function renderPager(data, page, q, type) {
    var totalPages = Math.max(1, Math.ceil((data.total || 0) / (data.per_page || 20)));
    var pager = document.getElementById('spa-dept-pager');
    if (!pager) return;
    pager.innerHTML = '<div class="flex items-center justify-end gap-1">' +
      '<button type="button" class="spa-icon-btn" data-pg="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + '><span class="material-symbols-outlined text-lg">chevron_right</span></button>' +
      '<span class="px-2 text-sm text-on-surface-variant">' + page + '/' + totalPages + '</span>' +
      '<button type="button" class="spa-icon-btn" data-pg="' + (page + 1) + '"' + (page >= totalPages ? ' disabled' : '') + '><span class="material-symbols-outlined text-lg">chevron_left</span></button></div>';
    pager.querySelectorAll('[data-pg]').forEach(function (b) {
      if (!b.disabled) b.addEventListener('click', function () {
        var pg = +b.dataset.pg;
        var search = document.getElementById('spa-dept-search');
        var type = document.getElementById('spa-dept-type');
        var url = '/api/departments?page=' + pg;
        if (search && search.value.trim()) url += '&search=' + encodeURIComponent(search.value.trim());
        if (type && type.value) url += '&type=' + encodeURIComponent(type.value);
        var table = document.getElementById('spa-dept-table');
        table.innerHTML = '<div class="p-10 text-center text-sm">جاري التحميل…</div>';
        S.api.get(url).then(function (d) { renderTable(table, d.items || []); renderPager(d, pg, q, type); });
      });
    });
  }

  function openForm(id) {
    var req = id ? S.api.get('/api/departments/' + id) : Promise.resolve(null);
    req.then(function (detail) {
      var dept = detail ? (detail.department || detail) : {};
      buildForm(dept);
    }).catch(function (err) {
      S.modal.open({ title: 'الأقسام', body: makeErr(err.message) });
    });
  }

  function buildForm(dept) {
    var isEdit = !!dept.id;
    var body = document.createElement('div');
    body.innerHTML = '<form id="spa-dept-form">' +
      '<div class="space-y-4">' +
      '<div><label class="block text-sm font-bold mb-1">اسم القسم <span class="text-error">*</span></label>' +
      '<input name="name" type="text" value="' + E(dept.name || '') + '" required class="w-full px-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary"></div>' +
      '<div><label class="block text-sm font-bold mb-1">النوع</label>' +
      '<select name="type" class="w-full px-3 py-2 rounded-lg border border-outline text-sm">' +
      '<option value="academic"' + (dept.type === 'academic' ? ' selected' : '') + '>كلية</option>' +
      '<option value="administrative"' + (dept.type === 'administrative' ? ' selected' : '') + '>إداري</option></select></div>' +
      '<div><label class="block text-sm font-bold mb-1">عدد الفصول</label>' +
      '<input name="semesters" type="number" min="1" max="12" value="' + (dept.semesters || 2) + '" class="w-full px-3 py-2 rounded-lg border border-outline text-sm"></div>' +
      '<div class="flex items-center gap-2">' +
      '<input type="checkbox" name="hidden" id="dept-hidden"' + (dept.hidden ? ' checked' : '') + ' class="rounded">' +
      '<label for="dept-hidden" class="text-sm">مخفٍ (قسم إداري)</label></div>' +
      '</div>' +
      '<div class="mt-6 flex items-center justify-end gap-3">' +
      '<button type="button" class="px-4 py-2 rounded-lg border border-outline text-sm font-bold" data-spa-modal-close>إلغاء</button>' +
      '<button type="submit" class="px-5 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold hover:opacity-90">' +
      '<span class="material-symbols-outlined text-lg align-middle">save</span> حفظ</button></div></form>';

    var modal = S.modal.open({ title: isEdit ? 'تعديل قسم' : 'إضافة قسم', body: body });
    body.querySelector('#spa-dept-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var fd = new FormData(e.target);
      var payload = {
        name: fd.get('name') || '',
        type: fd.get('type') || 'academic',
        semesters: parseInt(fd.get('semesters')) || 2,
        hidden: fd.has('hidden') ? 1 : 0
      };
      var promise = isEdit ? S.api.put('/api/departments/' + dept.id, payload) : S.api.post('/api/departments', payload);
      promise.then(function () {
        S.modal.close();
        showToastSuccess(isEdit ? 'تم تحديث القسم' : 'تم إضافة القسم');
        loadCurrentView();
      }).catch(function (err) { S.modal.showError(err.message); });
    });
  }

  function openDelete(id) {
    var body = document.createElement('div');
    body.innerHTML = '<p class="text-sm text-on-surface">هل أنت متأكد من حذف هذا القسم؟</p>' +
      '<div class="mt-5 flex items-center justify-end gap-3">' +
      '<button type="button" class="px-4 py-2 rounded-lg border border-outline text-sm font-bold" data-spa-modal-close>إلغاء</button>' +
      '<button type="button" class="px-5 py-2 rounded-lg bg-error text-on-primary text-sm font-bold" id="spa-dept-del">حذف</button></div>';
    S.modal.open({ title: 'حذف قسم', body: body });
    document.getElementById('spa-dept-del').addEventListener('click', function () {
      S.api.del('/api/departments/' + id).then(function () {
        S.modal.close();
        showToastSuccess('تم حذف القسم');
        loadCurrentView();
      }).catch(function (err) { S.modal.showError(err.message); });
    });
  }


  function loadCurrentView() {
    var el = document.getElementById('app-content');
    if (el) renderList(el);
  }

  function can(p) {
    var perms = (S.session && S.session.permissions) || [];
    return perms.indexOf(p) !== -1;
  }

  function makeErr(msg) {
    var el = document.createElement('div');
    el.className = 'text-error font-bold text-sm';
    el.textContent = msg;
    return el;
  }

  window.SPA.VIEWS.departments = renderList;
})();
