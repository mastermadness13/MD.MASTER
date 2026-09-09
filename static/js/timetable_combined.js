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

  var selDept = P.dept ? P.dept.id : null;
  var selSem = P.selected_semester;
  var activeVersionId = P.current_version_id;
  var locked = !!P.locked;

  var H = window.TimetableHelpers.create({ periods: periods, base: BASE });
  var esc = H.esc, semesterNumLabel = H.semesterNumLabel, fmtDate = H.fmtDate,
      qs = H.qs, nav = H.nav;


  // ── Next year ────────────────────────────────────────────
  function openNextYear() {
    if (locked) { window.showNotification('لا يمكن إنشاء نسخة من جدول للعرض فقط.', 'error'); return; }
    var deptName = '';
    departments.forEach(function (d) { if (d.id === selDept) deptName = d.name; });
    document.getElementById('nyInfo').textContent = 'سيُفتح جدول جديد فارغ للقسم «' + deptName + '» الفصل ' + semesterNumLabel(selSem) + '. يُحفظ الجدول الحالي ويُنشأ الجدول الجديد.';
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
  window.openNextYear = openNextYear;
  window.closeNextYear = closeNextYear;
  window.createNextYear = createNextYear;

  // ── Init ─────────────────────────────────────────────────
})();
