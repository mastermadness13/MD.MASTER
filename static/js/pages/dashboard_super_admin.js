(function() {
  var arabicMonths = ['يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'];
  var arabicDays = ['الأحد','الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت'];

  function renderDateCard() {
    var now = new Date();
    document.getElementById('dayNumber').textContent = now.getDate();
    document.getElementById('dayName').textContent = arabicDays[now.getDay()];
    document.getElementById('monthName').textContent = arabicMonths[now.getMonth()];
    document.getElementById('yearName').textContent = now.getFullYear();
  }

  function animateCounters() {
    document.querySelectorAll('.sa-stat-value[data-count]').forEach(function(el) {
      var target = parseInt(el.dataset.count, 10);
      if (!target) { el.textContent = target; return; }
      var duration = 1200;
      var start = performance.now();
      function update(now) {
        var elapsed = now - start;
        var progress = Math.min(elapsed / duration, 1);
        var eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(target * eased);
        if (progress < 1) requestAnimationFrame(update);
      }
      requestAnimationFrame(update);
    });
  }

  var deptChartData = [
    { name: 'الاتصالات', value: 32, color: 'var(--tertiary)' },
    { name: 'الحاسوب', value: 28, color: 'var(--info)' },
    { name: 'المدني', value: 24, color: 'var(--tertiary)' },
    { name: 'المعماري', value: 22, color: 'var(--success)' },
    { name: 'النفط', value: 34, color: 'var(--primary-dark)' },
    { name: 'العام', value: 29, color: 'var(--primary)' }
  ];

  function renderDeptChart() {
    var container = document.getElementById('deptChart');
    if (!container) return;
    var maxVal = Math.max.apply(null, deptChartData.map(function(d) { return d.value; }));
    container.innerHTML = deptChartData.map(function(d) {
      var h = (d.value / maxVal) * 100;
      return '<div class="sa-mini-bar-group">' +
        '<div class="sa-mini-bar-value">' + d.value + '</div>' +
        '<div class="sa-mini-bar" style="height:0%;background:' + d.color + '" data-height="' + h + '%"></div>' +
        '<div class="sa-mini-bar-label">' + d.name + '</div>' +
      '</div>';
    }).join('');

    setTimeout(function() {
      container.querySelectorAll('.sa-mini-bar').forEach(function(bar, i) {
        setTimeout(function() { bar.style.height = bar.dataset.height; }, i * 80);
      });
    }, 400);
  }

  var donutData = [
    { label: 'مدير نظام', value: 3, color: 'var(--primary)' },
    { label: 'مشرف قسم', value: 10, color: 'var(--tertiary)' },
    { label: 'عضو تدريس', value: 87, color: 'var(--success)' },
    { label: 'موظف', value: 12, color: 'var(--info)' }
  ];

  function renderDonut() {
    var svg = document.getElementById('donutSvg');
    var legend = document.getElementById('donutLegend');
    if (!svg || !legend) return;
    var total = donutData.reduce(function(s, d) { return s + d.value; }, 0);
    var circ = 2 * Math.PI * 60;
    var offset = 0;

    svg.innerHTML = '<circle cx="80" cy="80" r="60" stroke="var(--border)" stroke-dasharray="' + circ + '" stroke-dashoffset="0"/>';

    donutData.forEach(function(d) {
      var pct = d.value / total;
      var dashLen = pct * circ;
      var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', '80');
      circle.setAttribute('cy', '80');
      circle.setAttribute('r', '60');
      circle.setAttribute('stroke', d.color);
      circle.setAttribute('stroke-dasharray', dashLen + ' ' + (circ - dashLen));
      circle.setAttribute('stroke-dashoffset', '' + (-offset));
      svg.appendChild(circle);
      offset += dashLen;
    });

    legend.innerHTML = donutData.map(function(d) {
      return '<div class="sa-donut-legend-item">' +
        '<span class="sa-donut-legend-dot" style="background:' + d.color + '"></span>' +
        '<span>' + d.label + '</span>' +
        '<span class="sa-donut-legend-value">' + d.value + '</span>' +
      '</div>';
    }).join('');
  }

  var upcomingExams = [
    { day: '28', month: 'نوفمبر', course: 'استاتيكا — قسم النفط', meta: 'قاعة 1 — 09:00 ص', type: 'تحريري', typeClass: 'written' },
    { day: '29', month: 'نوفمبر', course: 'ميكانيكا موائع', meta: 'قاعة 2 — 11:00 ص', type: 'تحريري', typeClass: 'written' },
    { day: '01', month: 'ديسمبر', course: 'خواص صخور المكمن', meta: 'معمل نفط — 09:00 ص', type: 'عملي', typeClass: 'practical' }
  ];

  function renderUpcoming() {
    var el = document.getElementById('upcomingList');
    if (!el) return;
    el.innerHTML = upcomingExams.map(function(e) {
      return '<div class="sa-upcoming-item">' +
        '<div class="sa-upcoming-date"><span class="day">' + e.day + '</span><span class="month">' + e.month + '</span></div>' +
        '<div class="sa-upcoming-info">' +
          '<div class="sa-upcoming-course">' + e.course + '</div>' +
          '<div class="sa-upcoming-meta"><span class="material-symbols-outlined">schedule</span>' + e.meta + '</div>' +
        '</div>' +
        '<span class="sa-upcoming-type ' + e.typeClass + '">' + e.type + '</span>' +
      '</div>';
    }).join('');
  }

  var systemStatus = [
    { label: 'قاعدة البيانات', value: 'متصلة', status: 'online', progress: 95, color: 'var(--success)' },
    { label: 'التخزين', value: '72% مستخدم', status: 'warning', progress: 72, color: 'var(--warning)' },
    { label: 'البريد الإلكتروني', value: 'نشط', status: 'online', progress: 100, color: 'var(--success)' },
    { label: 'النسخ الاحتياطي', value: 'آخر نسخة: اليوم', status: 'online', progress: 100, color: 'var(--success)' },
    { label: 'ذاكرة الخادم', value: '45%', status: 'online', progress: 45, color: 'var(--success)' }
  ];

  function renderStatus() {
    var container = document.getElementById('statusList');
    if (!container) return;
    container.innerHTML = systemStatus.map(function(s) {
      return '<div class="sa-status-item">' +
        '<span class="sa-status-dot ' + s.status + '"></span>' +
        '<span class="sa-status-label">' + s.label + '</span>' +
        '<span class="sa-status-value">' + s.value + '</span>' +
      '</div>' +
      '<div style="margin-bottom:4px">' +
        '<div class="sa-progress-bar-bg">' +
          '<div class="sa-progress-bar-fill" style="width:0%;background:' + s.color + '" data-target="' + s.progress + '"></div>' +
        '</div>' +
      '</div>';
    }).join('');

    setTimeout(function() {
      container.querySelectorAll('.sa-progress-bar-fill').forEach(function(bar) {
        bar.style.width = bar.dataset.target + '%';
      });
    }, 500);
  }

  document.getElementById('activityFilter').addEventListener('click', function(e) {
    var chip = e.target.closest('.sa-filter-chip');
    if (!chip) return;
    var filter = chip.dataset.filter;
    document.querySelectorAll('#activityFilter .sa-filter-chip').forEach(function(c) {
      c.classList.toggle('active', c === chip);
    });
    document.querySelectorAll('#activityBody tr[data-filter]').forEach(function(row) {
      if (filter === 'all') {
        row.style.display = '';
      } else {
        row.style.display = row.dataset.filter === filter ? '' : 'none';
      }
    });
  });

  renderDateCard();
  renderDeptChart();
  renderDonut();
  renderUpcoming();
  renderStatus();
  setTimeout(animateCounters, 200);

  setTimeout(function() {
    var header = document.getElementById('pageHeader');
    if (header) {
      header.classList.add('hiding');
      setTimeout(function() { header.style.display = 'none'; }, 600);
    }
  }, 10000);
})();
