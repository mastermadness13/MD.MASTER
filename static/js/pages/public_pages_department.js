    (function () {
      var DEPTS = [], COURSES = [];
      var CARDS = [];          // DOM elements in "real" order
      var current = 0;         // index into DEPTS
      var CARD_GAP = 24;       // margin 12px each side

      function courseCount(id) {
        var n = 0;
        COURSES.forEach(function (c) { if (c.departmentId === id) n++; });
        return n;
      }

      function buildCards() {
        var track = document.getElementById('track');
        track.innerHTML = '';
        CARDS = [];
        DEPTS.forEach(function (d) {
          var card = document.createElement('div');
          card.className = 'card';
          card.dataset.name = d.name;
          card.innerHTML =
            '<div class="card-img" style="background:linear-gradient(160deg,' + d.accentColor + ' 0%,#1e1b4b 100%)">' +
              '<span class="material-symbols-outlined big-icon">' + (d.icon || 'school') + '</span>' +
              '<span class="badge">' + d.majors + ' تخصص</span>' +
            '</div>' +
            '<div class="card-body">' +
              '<h2>' + Utils.escapeHtml(d.name) + '</h2>' +
              '<p class="desc">' + Utils.escapeHtml(d.description || '') + '</p>' +
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
        window.location.href = 'department-info.html?dept=' + encodeURIComponent(name);
      }

      function goTo(index) {
        var n = DEPTS.length;
        current = ((index % n) + n) % n;
        render();
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
        var viewport = document.getElementById('viewport');
        var vw = viewport.clientWidth;
        var cw = cardWidth();
        var offset = (vw - cw) / 2;
        document.getElementById('track').style.transform = 'translateX(' + (current * cw - offset) + 'px)';

        CARDS.forEach(function (c, i) {
          var active = (i === current);
          c.classList.toggle('active', active);
          c.classList.toggle('peak', !active);
        });

        var dots = document.getElementById('dots');
        dots.innerHTML = '';
        DEPTS.forEach(function (_, i) {
          var b = document.createElement('button');
          b.className = 'dot' + (i === current ? ' active' : '');
          b.onclick = function () { goTo(i); };
          dots.appendChild(b);
        });
      }

      function render() { layout(); }

      function resize() { layout(); }

      function load() {
        Promise.all([DataClient.getDepartments(), DataClient.getCourses()]).then(function (res) {
          DEPTS = res[0];
          COURSES = res[1];
          buildCards();
          var p = window.location.search.match(/[?&]dept=(\d+)/);
          if (p) { var idx = 0; DEPTS.forEach(function (d, i) { if (String(d.id) === p[1]) idx = i; }); current = idx; }
          layout();
        }).catch(function (err) {
          document.getElementById('track').innerHTML = '<p class="text-red-600" style="color:#dc2626;padding:40px;text-align:center">تعذر تحميل البيانات.</p>';
          console.error(err);
        });
      }

      document.getElementById('prevBtn').addEventListener('click', prev);
      document.getElementById('nextBtn').addEventListener('click', next);
      document.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowRight') prev();
        if (e.key === 'ArrowLeft') next();
      });
      window.addEventListener('resize', resize);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(resize);

      load();
    })();
