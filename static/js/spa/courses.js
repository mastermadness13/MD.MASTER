/* SPA.courses — courses list + CRUD modals. */
(function () {
  'use strict';

  var S = window.SPA;
  var E = S.escapeHtml;

  function renderList(el) {
    el.innerHTML =
      '<div class="flex items-center justify-between mb-5">' +
      '<div><h1 class="text-2xl font-bold text-on-surface">المقررات الدراسية</h1>' +
      '<p class="text-sm text-on-surface-variant mt-1">إدارة المقررات الكلية</p></div>' +
      '<div id="spa-course-actions"></div></div>' +
      '<div class="bg-white rounded-xl border border-outline shadow-sm">' +
      '<div class="p-3 border-b border-outline-variant flex flex-wrap items-center gap-3">' +
      '<div class="relative flex-1 min-w-[200px]">' +
      '<span class="material-symbols-outlined absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">search</span>' +
      '<input id="spa-course-search" type="text" placeholder="بحث بالاسم أو الكود…" class="w-full pr-10 pl-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary">' +
      '</div></div>' +
      '<div id="spa-course-table" class="overflow-x-auto"></div>' +
      '<div id="spa-course-pager" class="p-3 border-t border-outline-variant"></div></div>';

    if (can('courses.manage')) {
      document.getElementById('spa-course-actions').innerHTML =
        '<button id="spa-course-add" class="inline-flex items-center gap-2 bg-primary text-on-primary px-4 py-2 rounded-lg font-bold text-sm hover:opacity-90">' +
        '<span class="material-symbols-outlined text-lg">add</span> إضافة مقرر</button>';
      document.getElementById('spa-course-add').addEventListener('click', function () { openForm(); });
    }

    var search = document.getElementById('spa-course-search');
    var timer = null;
    search.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(function () { loadPage(1); }, 300); });
    loadPage(1);
  }

  function loadPage(page) {
    var q = ((document.getElementById('spa-course-search') || {}).value || '').trim();
    var url = '/api/courses?page=' + page;
    if (q) url += '&search=' + encodeURIComponent(q);
    var table = document.getElementById('spa-course-table');
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
      table.innerHTML = '<div class="p-10 text-center text-on-surface-variant text-sm">لا توجد مقررات</div>';
      return;
    }
    var rows = items.map(function (c) {
      var actions = '';
      if (can('courses.manage')) {
        actions += '<button type="button" class="spa-icon-btn" data-edit="' + c.id + '" title="تعديل"><span class="material-symbols-outlined text-lg">edit</span></button>';
        actions += '<button type="button" class="spa-icon-btn text-error" data-del="' + c.id + '" title="حذف"><span class="material-symbols-outlined text-lg">delete</span></button>';
      }
      return '<tr class="border-b border-outline-variant hover:bg-surface-hover">' +
        '<td class="p-3"><div class="font-bold text-on-surface">' + E(c.name || '') + '</div>' +
        '<div class="text-xs text-on-surface-variant">' + E(c.code || '') + '</div></td>' +
        '<td class="p-3 text-on-surface-variant">' + E(c.department_name || c.department || '—') + '</td>' +
        '<td class="p-3 text-on-surface-variant">' + (c.year || '—') + '</td>' +
        '<td class="p-3 text-left whitespace-nowrap">' + actions + '</td></tr>';
    }).join('');
    table.innerHTML = '<table class="w-full text-right text-sm">' +
      '<thead><tr class="text-on-surface-variant border-b border-outline-variant bg-surface">' +
      '<th class="p-3 font-bold">المقرر</th><th class="p-3 font-bold">القسم</th><th class="p-3 font-bold">السنة</th><th class="p-3 font-bold text-left">إجراءات</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';

    table.querySelectorAll('[data-edit]').forEach(function (b) { b.addEventListener('click', function () { openForm(+b.dataset.edit); }); });
    table.querySelectorAll('[data-del]').forEach(function (b) { b.addEventListener('click', function () { openDelete(+b.dataset.del); }); });
  }

  function renderPager(data, page) {
    var totalPages = Math.max(1, Math.ceil((data.total || 0) / (data.per_page || 20)));
    var pager = document.getElementById('spa-course-pager');
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
    var metaReq = S.api.get('/api/departments');
    var courseReq = id ? S.api.get('/api/courses/' + id) : Promise.resolve(null);
    Promise.all([metaReq, courseReq]).then(function (r) {
      var depts = r[0].items || r[0] || [];
      var course = r[1] ? (r[1].course || r[1]) : {};
      buildForm(depts, course);
    }).catch(function (err) { S.modal.open({ title: 'خطأ', body: makeErr(err.message) }); });
  }

  function buildForm(depts, course) {
    var isEdit = !!course.id;
    var deptOpts = '<option value="">— بدون قسم —</option>' + depts.map(function (d) {
      return '<option value="' + d.id + '"' + (d.id == course.department_id ? ' selected' : '') + '>' + E(d.name) + '</option>';
    }).join('');

    var body = document.createElement('div');
    body.innerHTML = '<form id="spa-course-form"><div class="grid grid-cols-1 sm:grid-cols-2 gap-4">' +
      formField('name', 'اسم المقرر', 'text', course.name, { required: true }) +
      formField('code', 'كود المقرر', 'text', course.code, { required: true }) +
      '<div><label class="block text-sm font-bold mb-1">القسم</label>' +
      '<select name="department_id" class="w-full px-3 py-2 rounded-lg border border-outline text-sm">' + deptOpts + '</select></div>' +
      formField('year', 'السنة', 'number', course.year, { min: 1, max: 5 }) +
      '<div class="sm:col-span-2">' + formField('notes', 'ملاحظات', 'text', course.notes) + '</div>' +
      '</div>' +
      '<div class="mt-6 flex items-center justify-end gap-3">' +
      '<button type="button" class="px-4 py-2 rounded-lg border border-outline text-sm font-bold" data-spa-modal-close>إلغاء</button>' +
      '<button type="submit" class="px-5 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold hover:opacity-90">' +
      '<span class="material-symbols-outlined text-lg align-middle">save</span> حفظ</button></div></form>';

    S.modal.open({ title: isEdit ? 'تعديل مقرر' : 'إضافة مقرر', body: body });
    body.querySelector('#spa-course-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var fd = new FormData(e.target);
      var payload = {};
      fd.forEach(function (v, k) { payload[k] = v; });
      payload.department_id = payload.department_id || null;
      payload.year = parseInt(payload.year) || null;
      var promise = isEdit ? S.api.put('/api/courses/' + course.id, payload) : S.api.post('/api/courses', payload);
      promise.then(function () { S.modal.close(); showToastSuccess(isEdit ? 'تم التحديث' : 'تمت الإضافة'); loadPage(1); })
        .catch(function (err) { S.modal.showError(err.message); });
    });
  }

  function openDelete(id) {
    var body = document.createElement('div');
    body.innerHTML = '<p class="text-sm">هل أنت متأكد من حذف هذا المقرر؟</p>' +
      '<div class="mt-5 flex items-center justify-end gap-3">' +
      '<button type="button" class="px-4 py-2 rounded-lg border border-outline text-sm font-bold" data-spa-modal-close>إلغاء</button>' +
      '<button type="button" class="px-5 py-2 rounded-lg bg-error text-on-primary text-sm font-bold" id="spa-course-del">حذف</button></div>';
    S.modal.open({ title: 'حذف مقرر', body: body });
    document.getElementById('spa-course-del').addEventListener('click', function () {
      S.api.del('/api/courses/' + id).then(function () { S.modal.close(); showToastSuccess('تم الحذف'); loadPage(1); })
        .catch(function (err) { S.modal.showError(err.message); });
    });
  }

  function formField(name, label, type, value, extra) {
    extra = extra || {};
    return '<div><label class="block text-sm font-bold mb-1">' + label + (extra.required ? ' <span class="text-error">*</span>' : '') + '</label>' +
      '<input name="' + name + '" type="' + type + '" value="' + E(value || '') + '"' +
      (extra.required ? ' required' : '') + (extra.min ? ' min="' + extra.min + '"' : '') + (extra.max ? ' max="' + extra.max + '"' : '') +
      ' class="w-full px-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary"></div>';
  }

  function makeErr(msg) { var el = document.createElement('div'); el.className = 'text-error font-bold text-sm'; el.textContent = msg; return el; }
  function can(p) { return ((S.session && S.session.permissions) || []).indexOf(p) !== -1; }

  window.SPA.VIEWS.courses = renderList;
  window.SPA.VIEWS.courses_admin = renderList;
  window.SPA.VIEWS.courses_view = renderList;
  window.SPA.VIEWS.courses_hod = renderList;
})();
