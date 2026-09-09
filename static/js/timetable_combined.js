(function () {
  var BOOT = window.TIMETABLE_COMBINED_BOOT || {};
  var BASE = BOOT.base || '/timetable';
  var API = BOOT.api || '/timetable';
  var CSRF = (function () {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  })();

  var P = BOOT.payload || {};
  var departments = P.departments || [];
  var periods = P.periods || [];
  var days = P.days || [];
  var versions = P.versions || [];

  var selDept = P.dept ? P.dept.id : null;
  var selSem = P.selected_semester;
  var activeVersionId = P.current_version_id;
  var viewingVersionId = P.viewing_version_id;
  var viewingYear = P.viewing_semester_code || P.semester_code;
  var locked = !!P.locked;

  var H = window.TimetableHelpers.create({ periods: periods, base: BASE });
  var esc = H.esc, semesterNumLabel = H.semesterNumLabel, fmtDate = H.fmtDate,
      qs = H.qs, nav = H.nav;

  // ── Archive ──────────────────────────────────────────────
  function toggleArchive() {
    var d = document.getElementById('archiveDropdown');
    if (d.classList.contains('hidden')) { renderArchive(); d.classList.remove('hidden'); }
    else d.classList.add('hidden');
  }
  function closeArchive() { document.getElementById('archiveDropdown').classList.add('hidden'); }
  function isArchiveTarget(node) {
    var n = node;
    while (n) {
      if (n.id === 'archiveDropdown' || n.id === 'archiveBtn') return true;
      n = n.parentNode;
    }
    return false;
  }
  function renderArchive() {
    var body = document.getElementById('archiveBody');
    body.innerHTML = '';
    document.getElementById('archiveCount').textContent = versions.length;
    var deptName = '';
    departments.forEach(function (d) { if (d.id === selDept) deptName = d.name; });
    document.getElementById('archiveTitle').textContent = 'أرشيف ' + deptName + ' — الفصل ' + semesterNumLabel(selSem);

    if (!versions.length) {
      body.innerHTML = '<div class="px-4 py-10 text-center">' +
        '<span class="material-symbols-outlined text-[32px] text-text-faint block mb-2">archive</span>' +
        '<div class="text-sm text-text-secondary">لا يوجد أرشيف لهذا القسم والفصل بعد</div>' +
        '</div>';
      return;
    }
    var lastYear = null;
    versions.forEach(function (v) {
      var html = '';
      var displayName = v.semester_name_ar || v.semester_code || '—';
      if (displayName !== lastYear) {
        lastYear = displayName;
        html += '<div class="px-4 pt-2.5 pb-1.5 flex items-center gap-2 text-xs font-bold text-text-secondary">' +
          '<span class="material-symbols-outlined text-[14px] text-primary">calendar_month</span>' +
          'الفصل: ' + esc(displayName) +
          '</div>';
      }
      var active = v.id === viewingVersionId;
      html += '<div class="flex items-center gap-1 px-3 py-2 hover:bg-surface-container transition' + (active ? ' bg-primary/5' : '') + '">' +
        '<button type="button" onclick="window.__ttOpenVersion(' + v.id + ')" class="flex-1 flex items-center justify-between gap-2 text-right">' +
          '<span>' +
            '<span class="block text-sm font-bold text-on-surface">' + v.cnt + ' محاضرة</span>' +
            '<span class="block text-[11px] text-text-secondary mt-0.5">آخر تعديل: ' + fmtDate(v.updated_at) + '</span>' +
          '</span>' +
          '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-surface-zebra text-text-secondary">أرشيف</span>' +
        '</button>' +
        '<button type="button" title="فتح" onclick="window.__ttOpenVersion(' + v.id + ')" class="p-1.5 rounded-lg text-text-secondary hover:text-primary hover:bg-primary-container transition">' +
          '<span class="material-symbols-outlined text-[18px]">visibility</span>' +
        '</button>' +
        '</div>';
      body.insertAdjacentHTML('beforeend', html);
    });
  }
  function openVersion(id) {
    nav({ department_id: selDept, version_id: id });
  }
  function returnToCurrent() {
    nav({ department_id: selDept });
  }

  // ── Next year ────────────────────────────────────────────
  function openNextYear() {
    if (locked) { window.showNotification('لا يمكن إنشاء نسخة من جدول أرشيفي.', 'error'); return; }
    var deptName = '';
    departments.forEach(function (d) { if (d.id === selDept) deptName = d.name; });
    document.getElementById('nyInfo').textContent = 'سيُفتح جدول جديد فارغ للقسم «' + deptName + '» الفصل ' + semesterNumLabel(selSem) + '. يُنقل الجدول الحالي تلقائيًا إلى الأرشيف.';
    document.getElementById('nyWarn').classList.add('hidden');
    document.getElementById('nySeason').value = '';
    document.getElementById('nyYear').value = '';
    document.getElementById('nyOverlay').classList.remove('hidden');
    document.getElementById('nyModal').classList.remove('hidden');
  }
  function closeNextYear() {
    document.getElementById('nyOverlay').classList.add('hidden');
    document.getElementById('nyModal').classList.add('hidden');
  }
  function createNextYear() {
    var copy = document.getElementById('nyCopy').checked;
    var season = document.getElementById('nySeason').value || '';
    var yearVal = document.getElementById('nyYear').value.trim();
    var year = yearVal ? parseInt(yearVal, 10) : null;
    var payload = { version_id: activeVersionId, copy_entries: copy };
    if (season) payload.season = season;
    if (year) payload.year = year;
    fetch(API + '/api/version/create-next', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json().catch(function () { return { ok: false, message: 'استجابة غير متوقعة من الخادم.' }; }); })
      .then(function (d) {
        if (d && d.ok) {
          closeNextYear();
          window.showNotification(d.message || 'تم إنشاء النسخة بنجاح.', 'success');
          if (d.url && selDept) setTimeout(function () { location.href = d.url; }, 400);
          else setTimeout(function () { nav({ department_id: selDept }); }, 400);
        }
        else if (d && d.duplicate) {
          var warnBox = document.getElementById('nyWarn');
          warnBox.querySelector('span').innerText = (d.message || 'توجد نسخة لهذا الفصل/العام مسبقًا — اختر تاريخًا مختلفًا.');
          warnBox.classList.remove('hidden');
        }
        else { window.showNotification((d && d.message) || 'فشل إنشاء النسخة.', 'error'); }
      })
      .catch(function () { window.showNotification('تعذر الاتصال بالخادم.', 'error'); });
  }

  // ── Global hooks for inline handlers ─────────────────────
  window.toggleArchive = toggleArchive;
  window.closeArchive = closeArchive;
  window.openNextYear = openNextYear;
  window.closeNextYear = closeNextYear;
  window.createNextYear = createNextYear;
  window.__ttOpenVersion = function (id) { openVersion(id); };
  window.returnToCurrent = returnToCurrent;

  // ── Init ─────────────────────────────────────────────────
  document.addEventListener('click', function (e) {
    var dd = document.getElementById('archiveDropdown');
    if (dd.classList.contains('hidden')) return;
    if (!isArchiveTarget(e.target)) closeArchive();
  });
})();
