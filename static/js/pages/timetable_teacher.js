  (function () {
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
  })();
