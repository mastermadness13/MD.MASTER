/* SPA.teachers — teachers list + CRUD modals. */
(function () {
  'use strict';

  var S = window.SPA;
  var E = S.escapeHtml;

  function renderList(el) {
    el.innerHTML =
      '<div class="flex items-center justify-between mb-5">' +
      '<div><h1 class="text-2xl font-bold text-on-surface">أعضاء هيئة التدريس</h1>' +
      '<p class="text-sm text-on-surface-variant mt-1">إدارة بيانات أعضاء هيئة التدريس</p></div>' +
      '<div id="spa-teacher-actions"></div></div>' +
      '<div class="bg-white rounded-xl border border-outline shadow-sm">' +
      '<div class="p-3 border-b border-outline-variant">' +
      '<div class="relative">' +
      '<span class="material-symbols-outlined absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">search</span>' +
      '<input id="spa-teacher-search" type="text" placeholder="بحث بالاسم أو الرقم…" class="w-full pr-10 pl-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary">' +
      '</div></div>' +
      '<div id="spa-teacher-table" class="overflow-x-auto"></div>' +
      '<div id="spa-teacher-pager" class="p-3 border-t border-outline-variant"></div></div>';

    if (can('teachers.manage')) {
      document.getElementById('spa-teacher-actions').innerHTML =
        '<button id="spa-teacher-add" class="inline-flex items-center gap-2 bg-primary text-on-primary px-4 py-2 rounded-lg font-bold text-sm hover:opacity-90">' +
        '<span class="material-symbols-outlined text-lg">person_add</span> إضافة عضو هيئة تدريس</button>';
      document.getElementById('spa-teacher-add').addEventListener('click', function () { openForm(); });
    }

    var search = document.getElementById('spa-teacher-search');
    var timer = null;
    search.addEventListener('input', function () {
      clearTimeout(timer); timer = setTimeout(function () { loadPage(1); }, 300);
    });
    loadPage(1);
  }

  function loadPage(page) {
    var q = (document.getElementById('spa-teacher-search') || {}).value || '';
    q = q.trim();
    var url = '/api/teachers?page=' + page;
    if (q) url += '&search=' + encodeURIComponent(q);
    var table = document.getElementById('spa-teacher-table');
    table.innerHTML = '<div class="p-10 text-center text-on-surface-variant text-sm">جاري التحميل…</div>';
    S.api.get(url).then(function (data) {
      renderTable(table, data.items || []);
      renderPager(data, page, q);
    }).catch(function (err) {
      table.innerHTML = '<div class="p-10 text-center text-error text-sm font-bold">' + E(err.message) + '</div>';
    });
  }

  function renderTable(table, items) {
    if (!items.length) {
      table.innerHTML = '<div class="p-10 text-center text-on-surface-variant text-sm">لا يوجد أعضاء هيئة تدريس</div>';
      return;
    }
    var rows = items.map(function (t) {
      var actions = '';
      actions += '<button type="button" class="spa-icon-btn" data-view="' + t.id + '" title="عرض"><span class="material-symbols-outlined text-lg">visibility</span></button>';
      if (can('teachers.manage')) {
        actions += '<button type="button" class="spa-icon-btn" data-edit="' + t.id + '" title="تعديل"><span class="material-symbols-outlined text-lg">edit</span></button>';
        actions += '<button type="button" class="spa-icon-btn text-error" data-del="' + t.id + '" title="حذف"><span class="material-symbols-outlined text-lg">delete</span></button>';
      }
      return '<tr class="border-b border-outline-variant hover:bg-surface-hover">' +
        '<td class="p-3"><div class="font-bold text-on-surface">' + E(t.name || '') + '</div>' +
        '<div class="text-xs text-on-surface-variant">' + E(t.academic_number || '') + '</div></td>' +
        '<td class="p-3 text-on-surface-variant">' + E(t.department_name || '—') + '</td>' +
        '<td class="p-3 text-on-surface-variant">' + E(t.rank_name || t.academic_rank || '—') + '</td>' +
        '<td class="p-3 text-on-surface-variant">' + E(t.phone || '') + '</td>' +
        '<td class="p-3 text-left whitespace-nowrap">' + actions + '</td></tr>';
    }).join('');
    table.innerHTML = '<table class="w-full text-right text-sm">' +
      '<thead><tr class="text-on-surface-variant border-b border-outline-variant bg-surface">' +
      '<th class="p-3 font-bold">الاسم</th><th class="p-3 font-bold">القسم</th><th class="p-3 font-bold">الرتبة</th><th class="p-3 font-bold">الهاتف</th><th class="p-3 font-bold text-left">إجراءات</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';

    table.querySelectorAll('[data-view]').forEach(function (b) { b.addEventListener('click', function () { openView(+b.dataset.view); }); });
    table.querySelectorAll('[data-edit]').forEach(function (b) { b.addEventListener('click', function () { openForm(+b.dataset.edit); }); });
    table.querySelectorAll('[data-del]').forEach(function (b) { b.addEventListener('click', function () { openDelete(+b.dataset.del); }); });
  }

  function renderPager(data, page, q) {
    var totalPages = Math.max(1, Math.ceil((data.total || 0) / (data.per_page || 20)));
    var pager = document.getElementById('spa-teacher-pager');
    if (!pager) return;
    pager.innerHTML = '<div class="flex items-center justify-end gap-1">' +
      '<button type="button" class="spa-icon-btn" data-pg="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + '><span class="material-symbols-outlined text-lg">chevron_right</span></button>' +
      '<span class="px-2 text-sm text-on-surface-variant">' + page + '/' + totalPages + '</span>' +
      '<button type="button" class="spa-icon-btn" data-pg="' + (page + 1) + '"' + (page >= totalPages ? ' disabled' : '') + '><span class="material-symbols-outlined text-lg">chevron_left</span></button></div>';
    pager.querySelectorAll('[data-pg]').forEach(function (b) {
      if (!b.disabled) b.addEventListener('click', function () { loadPage(+b.dataset.pg); });
    });
  }

  function openView(id) {
    S.api.get('/api/teachers/' + id).then(function (detail) {
      var t = detail.teacher || detail;
      var body = document.createElement('div');
      body.className = 'space-y-4';
      body.innerHTML =
        '<div class="flex items-center gap-4">' +
        '<div class="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center">' +
        '<span class="material-symbols-outlined text-3xl text-primary">person</span></div>' +
        '<div><div class="font-bold text-lg text-on-surface">' + E(t.name || '') + '</div>' +
        '<div class="text-sm text-on-surface-variant">' + E(t.academic_number || '') + '</div></div></div>' +
        '<dl class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">' +
        field('القسم', t.department_name) + field('التخصص', t.specialization) +
        field('الرتبة', t.rank_name || t.academic_rank) + field('الهاتف', t.phone) +
        field('البريد', t.email) + '</dl>';
      S.modal.open({ title: 'بيانات عضو هيئة التدريس', body: body });
    }).catch(function (err) { S.modal.open({ title: 'خطأ', body: makeErr(err.message) }); });
  }

  function openForm(id) {
    var metaReq = S.api.get('/api/departments');
    var teacherReq = id ? S.api.get('/api/teachers/' + id) : Promise.resolve(null);
    Promise.all([metaReq, teacherReq]).then(function (results) {
      var depts = (results[0].items || results[0] || []);
      var detail = results[1];
      var t = detail ? (detail.teacher || detail) : {};
      buildForm(depts, t);
    }).catch(function (err) { S.modal.open({ title: 'خطأ', body: makeErr(err.message) }); });
  }

  function buildForm(depts, teacher) {
    var isEdit = !!teacher.id;
    var deptOpts = '<option value="">— بدون قسم —</option>' + depts.map(function (d) {
      return '<option value="' + d.id + '"' + (d.id == teacher.department_id ? ' selected' : '') + '>' + E(d.name) + '</option>';
    }).join('');

    var body = document.createElement('div');
    body.innerHTML = '<form id="spa-teacher-form"><div class="grid grid-cols-1 sm:grid-cols-2 gap-4">' +
      formField('name', 'الاسم الكامل', 'text', teacher.name, { required: true }) +
      formField('academic_number', 'رقم الموظف', 'text', teacher.academic_number) +
      '<div><label class="block text-sm font-bold mb-1">القسم</label>' +
      '<select name="department_id" class="w-full px-3 py-2 rounded-lg border border-outline text-sm">' + deptOpts + '</select></div>' +
      formField('specialization', 'التخصص', 'text', teacher.specialization) +
      formField('email', 'البريد الإلكتروني', 'email', teacher.email) +
      formField('phone', 'الهاتف', 'tel', teacher.phone) +
      (isEdit ? '' : formField('password', 'كلمة المرور', 'password', '', { required: true })) +
      (isEdit ? '' : '<div class="sm:col-span-2"><label class="block text-sm font-bold mb-1">اسم المستخدم</label>' +
        '<input name="username" type="text" required class="w-full px-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="يُولّد تلقائياً إذا ترك فارغاً"></div>') +
      '</div>' +
      '<div class="mt-6 flex items-center justify-end gap-3">' +
      '<button type="button" class="px-4 py-2 rounded-lg border border-outline text-sm font-bold" data-spa-modal-close>إلغاء</button>' +
      '<button type="submit" class="px-5 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold hover:opacity-90">' +
      '<span class="material-symbols-outlined text-lg align-middle">save</span> حفظ</button></div></form>';

    S.modal.open({ title: isEdit ? 'تعديل عضو هيئة تدريس' : 'إضافة عضو هيئة تدريس', body: body });

    body.querySelector('#spa-teacher-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var fd = new FormData(e.target);
      var payload = {};
      fd.forEach(function (v, k) { if (v) payload[k] = v; });
      var promise = isEdit ? S.api.put('/api/teachers/' + teacher.id, payload) : S.api.post('/api/teachers', payload);
      promise.then(function () {
        S.modal.close();
        showToastSuccess(isEdit ? 'تم تحديث البيانات' : 'تمت الإضافة بنجاح');
        loadPage(1);
      }).catch(function (err) { S.modal.showError(err.message); });
    });
  }

  function openDelete(id) {
    var body = document.createElement('div');
    body.innerHTML = '<p class="text-sm">هل أنت متأكد من حذف هذا العضو؟</p>' +
      '<div class="mt-5 flex items-center justify-end gap-3">' +
      '<button type="button" class="px-4 py-2 rounded-lg border border-outline text-sm font-bold" data-spa-modal-close>إلغاء</button>' +
      '<button type="button" class="px-5 py-2 rounded-lg bg-error text-on-primary text-sm font-bold" id="spa-teacher-del">حذف</button></div>';
    S.modal.open({ title: 'حذف', body: body });
    document.getElementById('spa-teacher-del').addEventListener('click', function () {
      S.api.del('/api/teachers/' + id).then(function () { S.modal.close(); showToastSuccess('تم الحذف'); loadPage(1); })
        .catch(function (err) { S.modal.showError(err.message); });
    });
  }

  function formField(name, label, type, value, extra) {
    extra = extra || {};
    return '<div><label class="block text-sm font-bold mb-1">' + label + (extra.required ? ' <span class="text-error">*</span>' : '') + '</label>' +
      '<input name="' + name + '" type="' + type + '" value="' + E(value || '') + '"' +
      (extra.required ? ' required' : '') +
      ' class="w-full px-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary"></div>';
  }

  function field(label, value) {
    return '<div><dt class="text-xs text-on-surface-variant font-bold">' + label + '</dt>' +
      '<dd class="font-semibold text-on-surface mt-0.5">' + E(value || '—') + '</dd></div>';
  }

  function makeErr(msg) { var el = document.createElement('div'); el.className = 'text-error font-bold text-sm'; el.textContent = msg; return el; }

  function can(p) { return ((S.session && S.session.permissions) || []).indexOf(p) !== -1; }

  window.SPA.VIEWS.teachers = renderList;
  window.SPA.VIEWS.teachers_admin = renderList;
  window.SPA.VIEWS.teachers_view = renderList;
})();