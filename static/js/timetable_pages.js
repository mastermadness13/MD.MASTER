(function () {
  // Shared behaviours for the remaining timetable pages (teacher + list).
  // Follows the TIMETABLE_*_BOOT config pattern used by timetable_live.js:
  //   TIMETABLE_TEACHER_BOOT -> daily-accordion responsive collapse
  //   TIMETABLE_LIST_BOOT    -> filters + deleteEntry (CSRF via meta, toast UI)
  function boot(name) { return window[name] || null; }
  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  }
  function toast(msg, isError) {
    var el = document.getElementById('toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'toast';
      document.body.appendChild(el);
    }
    el.innerHTML = '<span class="material-symbols-outlined text-lg">' + (isError ? 'error' : 'check_circle') + '</span> ' + msg;
    el.className = 'fixed bottom-6 left-6 z-50 flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg text-sm font-semibold text-white ' + (isError ? 'bg-red-600' : 'bg-primary');
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.classList.add('hidden'); }, 3600);
  }
  function buildQuery(extra) {
    var params = new URLSearchParams(location.search);
    for (var k in extra) {
      if (extra[k] === '' || extra[k] === null) params.delete(k);
      else params.set(k, extra[k]);
    }
    return params.toString();
  }

  // ── Teacher weekly schedule: day-accordion (mobile closes non-today days) ──
  function initTeacher() {
    var sections = document.querySelectorAll('.day-accordion');
    if (!sections.length) return;
    var names = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
    function todayAr() { return names[new Date().getDay()]; }

    function sync() {
      var desktop = window.innerWidth >= 1024;
      var today = todayAr();
      sections.forEach(function (sec) {
        if (sec.getAttribute('data-user-toggled') === '1') return;
        if (desktop || sec.getAttribute('data-day') === today) {
          sec.classList.remove('day-acc-collapsed');
        } else {
          sec.classList.add('day-acc-collapsed');
        }
      });
    }
    sections.forEach(function (sec) {
      var header = sec.querySelector('.day-acc-header');
      if (!header) return;
      header.addEventListener('click', function () {
        sec.setAttribute('data-user-toggled', '1');
        sec.classList.toggle('day-acc-collapsed');
      });
    });
    sync();
    window.addEventListener('resize', sync);
  }

  // ── All-departments list (print/timetable): filters + delete ──
  function initList(BOOT) {
    var URLS = (BOOT && BOOT.urls) || {};

    var dept = document.getElementById('deptFilter');
    if (dept) {
      dept.addEventListener('change', function () {
        location.search = buildQuery({ department: dept.value, semester: '', section: '' });
      });
    }
    var sem = document.getElementById('semesterFilter');
    if (sem) {
      sem.addEventListener('change', function () {
        location.search = buildQuery({ semester: sem.value });
      });
    }
    var sec = document.getElementById('sectionFilter');
    if (sec) {
      sec.addEventListener('change', function () {
        location.search = buildQuery({ section: sec.value });
      });
    }

    window.deleteEntry = function (id, name) {
      if (!confirm('هل تريد حذف حصة "' + name + '" من الجدول؟')) return;
      if (!URLS.deleteEntry) return;
      fetch(URLS.deleteEntry, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrf()
        },
        body: JSON.stringify({ lecture_id: id })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d && d.ok) { toast(d.message || 'تمت عملية الحذف'); location.reload(); }
        else toast((d && d.message) || 'فشلت العملية', true);
      }).catch(function () { toast('حدث خطأ أثناء الحذف', true); });
    };
  }

  if (boot('TIMETABLE_TEACHER_BOOT')) initTeacher();
  if (boot('TIMETABLE_LIST_BOOT')) initList(boot('TIMETABLE_LIST_BOOT'));
})();