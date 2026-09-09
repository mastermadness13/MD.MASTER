    function esc(s) { return Utils.escapeHtml(s); }

    function renderDeptCarousel(depts, courses) {
      var CARDS = [];
      var current = 0;
      var track = document.getElementById('track');
      var dotsBox = document.getElementById('dots');
      var viewport = document.getElementById('viewport');

      function courseCount(id) {
        var n = 0;
        courses.forEach(function (c) { if (c.departmentId === id) n++; });
        return n;
      }

      function buildCards() {
        track.innerHTML = '';
        CARDS = [];
        depts.forEach(function (d) {
          var card = document.createElement('div');
          card.className = 'card';
          card.dataset.name = d.name;
          card.innerHTML =
            '<div class="card-img" style="background:linear-gradient(160deg,' + d.accentColor + ' 0%,#1e1b4b 100%)">' +
              '<span class="material-symbols-outlined big-icon">' + (d.icon || 'school') + '</span>' +
              '<span class="badge">' + (d.majors || 0) + ' تخصص</span>' +
            '</div>' +
            '<div class="card-body">' +
              '<h2>' + esc(d.name) + '</h2>' +
              '<p class="desc">' + esc(d.description || '') + '</p>' +
              '<div class="meta">' +
                '<span class="chip">' + courseCount(d.id) + ' مقرر</span>' +
                '<span class="chip">' + (d.semesters || 0) + ' فصل دراسي</span>' +
              '</div>' +
              '<div class="open-hint"><span class="material-symbols-outlined">open_in_new</span> عرض المعلومات</div>' +
            '</div>';
          card.addEventListener('click', function () { openDept(d.name); });
          track.appendChild(card);
          CARDS.push(card);
        });
      }

      function openDept(name) {
        window.location.href = 'pages/department-info.html?dept=' + encodeURIComponent(name);
      }

      function goTo(index) {
        var n = CARDS.length;
        if (!n) return;
        current = ((index % n) + n) % n;
        layout();
      }
      function next() { goTo(current + 1); }
      function prev() { goTo(current - 1); }

      function cardWidth() {
        var c = CARDS[0];
        if (!c) return 340;
        var s = getComputedStyle(c);
        return c.offsetWidth + (parseFloat(s.marginLeft) + parseFloat(s.marginRight));
      }

      function layout() {
        var vw = viewport.clientWidth;
        var cw = cardWidth();
        var offset = (vw - cw) / 2;
        track.style.transform = 'translateX(' + (current * cw - offset) + 'px)';
        CARDS.forEach(function (c, i) {
          c.classList.toggle('active', i === current);
          c.classList.toggle('peak', i !== current);
        });
        dotsBox.innerHTML = '';
        CARDS.forEach(function (_, i) {
          var b = document.createElement('button');
          b.className = 'dot' + (i === current ? ' active' : '');
          b.setAttribute('aria-label', 'القسم ' + (i + 1));
          b.addEventListener('click', function () { goTo(i); });
          dotsBox.appendChild(b);
        });
      }

      buildCards();
      document.getElementById('nextBtn').addEventListener('click', next);
      document.getElementById('prevBtn').addEventListener('click', prev);
      layout();
      var t;
      window.addEventListener('resize', function () {
        clearTimeout(t);
        t = setTimeout(layout, 120);
      });
    }

    async function load() {
      try {
        var res = await Promise.all([
          DataClient.getDepartments(),
          DataClient.getCourses(),
          DataClient.getTeachers(),
          DataClient.getRooms(),
          DataClient.getTimetable(),
          DataClient.getExams()
        ]);
        var depts = res[0], courses = res[1], teachers = res[2], rooms = res[3], tt = res[4], exams = res[5];

        document.getElementById('stat-depts').textContent = depts.length;
        document.getElementById('stat-courses').textContent = courses.length;
        document.getElementById('stat-teachers').textContent = teachers.length;
        document.getElementById('stat-rooms').textContent = rooms.length;

        renderDeptCarousel(depts, courses);

        var weekdays = Utils.getWeekdays();
        var ttWrap = document.getElementById('tt-preview');
        if (tt.length > 0) {
          var headers = weekdays.map(function (w) { return '<th class="bg-gray-50 border border-gray-200 px-3 py-2.5 text-xs font-semibold text-gray-600">' + w.label + '</th>'; }).join('');
          var periods = [];
          tt.forEach(function (e) { if (periods.indexOf(e.period) < 0) periods.push(e.period); });
          var rows = periods.map(function (p) {
            var cells = weekdays.map(function (w) {
              var entry = null;
              tt.forEach(function (e) { if (e.day === w.label && e.period === p) entry = e; });
              if (!entry) return '<td class="border border-gray-200 px-2 py-2 bg-gray-50/50"></td>';
              return '<td class="border border-gray-200 px-2 py-2 align-top"><div class="tt-cell-chip">' + esc(entry.courseName) + '</div>' +
                '<div class="text-[11px] text-gray-500 mt-1">' + esc(entry.roomName || '') + '</div></td>';
            }).join('');
            return '<tr><td class="bg-gray-50 border border-gray-200 px-3 py-2.5 text-center font-semibold text-xs text-gray-600">الفترة ' + p + '</td>' + cells + '</tr>';
          }).join('');
          ttWrap.innerHTML = '<div class="overflow-x-auto"><table class="w-full min-w-[640px] border-collapse"><thead><tr><th class="bg-gray-50 border border-gray-200 px-3 py-2.5 text-xs font-semibold text-gray-600">الفترة</th>' + headers + '</tr></thead><tbody>' + rows + '</tbody></table></div>';
        } else {
          ttWrap.innerHTML = '<div class="text-center py-12 text-gray-500"><p>لا توجد جداول مسجلة بعد.</p></div>';
        }

        var exWrap = document.getElementById('exams-preview');
        if (exams.length > 0) {
          exWrap.innerHTML = '<div class="space-y-2.5">' + exams.slice(0, 5).map(function (e) {
            var dateParts = String(e.examDate || '').split('-');
            var day = dateParts.length === 3 ? dateParts[2] : (e.examDate || '');
            var dayName = '—';
            try { dayName = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'][new Date(e.examDate + 'T00:00:00').getDay()]; } catch (err) {}
            return '<div class="bg-white border border-gray-200 rounded-xl p-3.5 flex items-center gap-3">' +
              '<div class="text-center bg-emerald-50 border border-emerald-100 rounded-xl px-3 py-2 min-w-[52px]"><b class="block text-emerald-700">' + esc(day) + '</b><span class="text-[10px] text-gray-500">' + esc(dayName) + '</span></div>' +
              '<div class="flex-1"><b class="text-sm">' + esc(e.courseName) + '</b>' +
              '<div class="text-xs text-gray-500 mt-0.5">' + esc(e.courseCode || '') + ' • ' + esc(e.roomName || 'القاعة غير محددة') + '</div></div>' +
              '<span class="bg-amber-100 text-amber-700 text-[11px] px-2.5 py-1 rounded-full font-semibold">مخطط</span>' +
            '</div>';
          }).join('') + '</div>';
        } else {
          exWrap.innerHTML = '<div class="bg-white border border-gray-200 rounded-xl text-center py-12 text-gray-500"><p>لا توجد امتحانات مسجلة بعد.</p></div>';
        }
      } catch (err) {
        document.getElementById('track').innerHTML = '<div class="bg-white border border-gray-200 rounded-xl text-center py-12 text-red-600"><p>تعذر تحميل البيانات. تأكد من تشغيل الموقع عبر خادم محلي (HTTP).</p></div>';
        console.error(err);
      }
    }
    load();
