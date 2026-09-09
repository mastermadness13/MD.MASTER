    var DEPTS = [], COURSES = [], COURSE_BY_ID = {};
    var currentDept = null;
    var YEAR_NAMES = { 1: 'السنة الأولى', 2: 'السنة الثانية', 3: 'السنة الثالثة', 4: 'السنة الرابعة' };
    var SEMESTER_NAMES = { 1: 'الفصل الأول', 2: 'الفصل الثاني', 3: 'الفصل الثالث', 4: 'الفصل الرابع', 5: 'الفصل الخامس', 6: 'الفصل السادس', 7: 'الفصل السابع', 8: 'الفصل الثامن' };

    function esc(s) { return Utils.escapeHtml(s); }
    function infoHref(d) { return '?dept=' + encodeURIComponent(d.name); }

    function deptByName(name) {
      if (!name) return null;
      for (var i = 0; i < DEPTS.length; i++) if (DEPTS[i].name === name) return DEPTS[i];
      return null;
    }
    function deptById(id) {
      for (var i = 0; i < DEPTS.length; i++) if (DEPTS[i].id === id) return DEPTS[i];
      return null;
    }
    function deptCourses(dept) {
      var out = COURSES.filter(function (c) { return c.departmentId === dept.id; });
      out.sort(function (a, b) {
        if ((a.year || 0) !== (b.year || 0)) return (a.year || 0) - (b.year || 0);
        if ((a.semester || 0) !== (b.semester || 0)) return (a.semester || 0) - (b.semester || 0);
        return String(a.code || '').localeCompare(String(b.code || ''), 'ar');
      });
      return out;
    }
    function paramDept() {
      var m = window.location.search.match(/[?&]dept=([^&]+)/);
      if (!m) return null;
      try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; }
    }
    function prereqCodes(c) {
      var ids = c.prerequisites || [];
      var codes = [];
      for (var i = 0; i < ids.length; i++) {
        var pc = COURSE_BY_ID[ids[i]];
        if (pc) codes.push(pc.code);
      }
      return codes.length ? codes.join('، ') : '—';
    }
    function totalUnits(courses) {
      var n = 0;
      courses.forEach(function (c) { n += (c.theoreticalHours || 0) + (c.practicalHours || 0); });
      return n;
    }

    /* ---------- Department Switcher ---------- */
    function renderSwitcher() {
      var wrap = document.getElementById('deptSwitcher');
      wrap.innerHTML = '';
      DEPTS.forEach(function (d) {
        var active = d.id === currentDept.id;
        var color = d.accentColor || '#6b21a8';
        var a = document.createElement('a');
        a.className = 'dept-pill';
        a.href = infoHref(d);
        a.innerHTML = '<span class="material-symbols-outlined">' + (d.icon || 'domain') + '</span><span>' + esc(d.name) + '</span>';
        a.style.borderColor = active ? color : color + '55';
        a.style.background = active ? color : 'transparent';
        a.style.color = active ? '#ffffff' : color;
        wrap.appendChild(a);
      });
    }

    /* ---------- Courses Plan ---------- */
    function coursesTable(courses) {
      var rows = '';
      var tTheory = 0, tPract = 0;
      courses.forEach(function (c, i) {
        var th = c.theoreticalHours || 0;
        var tp = c.practicalHours || 0;
        tTheory += th; tPract += tp;
        rows += '<tr class="hover:bg-surface-hover transition-colors">' +
          '<td class="px-3 py-2 text-center text-text-muted text-xs font-semibold">' + (i + 1) + '</td>' +
          '<td class="px-3 py-2"><span class="font-mono font-bold text-primary text-xs">' + esc(c.code) + '</span></td>' +
          '<td class="px-3 py-2 font-medium text-text-primary text-sm">' + esc(c.name) + '</td>' +
          '<td class="px-3 py-2 text-center text-text-secondary text-sm">' + th + '</td>' +
          '<td class="px-3 py-2 text-center text-text-secondary text-sm">' + tp + '</td>' +
          '<td class="px-3 py-2 text-center font-bold text-text-secondary text-sm">' + esc(prereqCodes(c)) + '</td>' +
        '</tr>';
      });
      rows += '<tr class="bg-surface-zebra font-bold text-text-primary">' +
        '<td class="px-3 py-2 text-center text-xs" colspan="3">المجموع (' + courses.length + ' مادة)</td>' +
        '<td class="px-3 py-2 text-center text-sm">' + tTheory + '</td>' +
        '<td class="px-3 py-2 text-center text-sm">' + tPract + '</td>' +
        '<td class="px-3 py-2 text-center text-xs text-text-muted">—</td>' +
      '</tr>';
      return '<div class="overflow-x-auto"><table class="w-full min-w-[640px]">' +
        '<thead class="bg-surface-zebra">' +
          '<tr>' +
            '<th class="px-3 py-2 text-center font-semibold text-text-secondary text-xs w-10">ت</th>' +
            '<th class="px-3 py-2 text-right font-semibold text-text-secondary text-xs">رقم المادة</th>' +
            '<th class="px-3 py-2 text-right font-semibold text-text-secondary text-xs">اسم المادة</th>' +
            '<th class="px-3 py-2 text-center font-semibold text-text-secondary text-xs">نظري</th>' +
            '<th class="px-3 py-2 text-center font-semibold text-text-secondary text-xs">عملي</th>' +
            '<th class="px-3 py-2 text-center font-semibold text-text-secondary text-xs">الاعتمادية</th>' +
          '</tr>' +
        '</thead>' +
        '<tbody class="divide-y divide-gray-100">' + rows + '</tbody></table></div>';
    }

    function renderPlan(dept, color) {
      var courses = deptCourses(dept);
      if (!courses.length) return '<p class="text-sm text-text-muted py-4">لا توجد مقررات مسجلة لهذا القسم.</p>';
      var groups = {};
      courses.forEach(function (c) {
        var key = (c.year || 1) + '-' + (c.semester || 1);
        if (!groups[key]) groups[key] = [];
        groups[key].push(c);
      });
      var keys = Object.keys(groups).sort(function (a, b) {
        var ay = parseInt(a.split('-')[0], 10), by = parseInt(b.split('-')[0], 10);
        var as = parseInt(a.split('-')[1], 10), bs = parseInt(b.split('-')[1], 10);
        return (ay - by) || (as - bs);
      });
      var html = '';
      keys.forEach(function (key) {
        var y = parseInt(key.split('-')[0], 10);
        var s = parseInt(key.split('-')[1], 10);
        var list = groups[key];
        html += '<div class="print-block bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mb-6 print-sheet" id="plan-' + dept.id + '-' + key + '">' +
          '<div class="px-4 py-3 border-b border-gray-100 flex items-center justify-between flex-wrap gap-2" style="background:linear-gradient(to left, ' + color + '14, transparent)">' +
            '<div class="flex items-center gap-2.5">' +
              '<span class="w-8 h-8 rounded-lg text-white flex items-center justify-center" style="background:' + color + '"><span class="material-symbols-outlined text-lg">table_chart</span></span>' +
              '<div>' +
                '<h3 class="text-sm font-bold text-text-primary m-0 leading-tight">جدول مقررات ' + esc(dept.name) + ' — ' + (YEAR_NAMES[y] || 'السنة ' + y) + ' — ' + (SEMESTER_NAMES[s] || 'الفصل ' + s) + '</h3>' +
                '<span class="text-[11px] text-text-muted">' + list.length + ' مادة — ' + totalUnits(list) + ' وحدة دراسية</span>' +
              '</div>' +
            '</div>' +
            '<span class="text-xs font-bold px-2.5 py-1 rounded-full text-white" style="background:' + color + '">' + (YEAR_NAMES[y] || 'السنة ' + y) + '</span>' +
          '</div>' +
          coursesTable(list) +
        '</div>';
      });
      return html;
    }

    /* ---------- Profile Sections ---------- */
    function sectionCard(title, icon, body, color, id) {
      return '<div class="print-block bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mb-4 print-sheet section-anchor"' + (id ? ' id="' + id + '"' : '') + '>' +
        '<div class="px-4 py-3 border-b border-gray-100 flex items-center gap-2.5" style="background:linear-gradient(to left, ' + color + '14, transparent)">' +
          '<span class="material-symbols-outlined text-primary" style="color:' + color + '">' + icon + '</span>' +
          '<h3 class="text-sm font-bold text-text-primary m-0">' + title + '</h3>' +
        '</div>' +
        '<div class="p-4 prose-section">' + body + '</div>' +
      '</div>';
    }
    function listItems(items, color) {
      if (!items || !items.length) return '';
      return '<ul class="space-y-2">' + items.map(function (it) {
        return '<li class="text-sm text-text-secondary leading-relaxed">' +
          '<span class="material-symbols-outlined text-[16px] mt-0.5 shrink-0" style="color:' + color + '">check_circle</span>' +
          '<span>' + esc(it) + '</span></li>';
      }).join('') + '</ul>';
    }
    function paragraph(text) {
      return text ? '<p class="text-sm text-text-secondary leading-relaxed whitespace-pre-line m-0">' + esc(text) + '</p>' : '';
    }

    function renderProfile(d, color) {
      var p = d.profile;
      if (!p) return '';
      var html = '';
      var full = [
        { t: 'رؤية القسم', i: 'visibility', v: paragraph(p.vision) },
        { t: 'رسالة القسم', i: 'campaign', v: paragraph(p.mission) },
        { t: 'كلمة القسم', i: 'record_voice_over', v: paragraph(p.word) }
      ];
      var grid = [
        { t: 'أهداف القسم', i: 'track_changes', v: listItems(p.objectives, color), id: 'objectives' },
        { t: 'متطلبات الالتحاق', i: 'fact_check', v: listItems(p.requirements, color) },
        { t: 'مجالات الدراسة', i: 'menu_book', v: listItems(p.studyFields, color) },
        { t: 'المهارات التي يكتسبها الطالب', i: 'workspace_premium', v: listItems(p.skills, color) },
        { t: 'المعامل والتجهيزات', i: 'science', v: listItems(p.labs, color) + (p.labsNote ? '<p class="text-sm text-text-secondary leading-relaxed mt-3 mb-0">' + esc(p.labsNote) + '</p>' : '') },
        { t: 'التدريب العملي', i: 'construction', v: listItems(p.practicalTraining, color) },
        { t: 'فرص العمل بعد التخرج', i: 'work', v: listItems(p.careers, color), id: 'careers' },
        { t: 'فرص استكمال الدراسة', i: 'school', v: listItems(p.furtherStudy, color) }
      ];
      full.forEach(function (s) { if (s.v) html += sectionCard(s.t, s.i, s.v, color); });
      var gridHtml = '';
      grid.forEach(function (s) { if (s.v) gridHtml += sectionCard(s.t, s.i, s.v, color, s.id); });
      if (gridHtml) html += '<div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">' + gridHtml + '</div>';
      return html;
    }

    /* ---------- Hero Introduction ---------- */
    function renderHero(d, courses, color) {
      return '<div class="rounded-3xl overflow-hidden mb-6 text-white relative print-sheet" style="background:linear-gradient(135deg, ' + color + ' 0%, #1e1b4b 100%)">' +
        '<div class="absolute inset-0 opacity-10" style="background-image:radial-gradient(circle at 15% 15%, rgba(255,255,255,.5) 0, transparent 35%), radial-gradient(circle at 85% 80%, rgba(255,255,255,.5) 0, transparent 40%)"></div>' +
        '<div class="relative p-6 sm:p-10">' +
          '<div class="inline-flex items-center gap-2 bg-white/15 backdrop-blur px-3 py-1.5 rounded-full text-white/90 text-xs font-bold mb-4">' +
            '<span class="material-symbols-outlined text-sm">school</span> كلية التقنية الهندسية زوارة' +
          '</div>' +
          '<div class="flex items-start gap-5 flex-wrap">' +
            '<span class="w-16 h-16 sm:w-20 sm:h-20 rounded-2xl bg-white/15 flex items-center justify-center shrink-0 shadow-lg"><span class="material-symbols-outlined text-5xl">' + (d.icon || 'school') + '</span></span>' +
            '<div class="flex-1 min-w-[220px]">' +
              '<h1 class="text-2xl sm:text-3xl font-extrabold m-0 leading-tight">مرحباً بك في ' + esc(d.name) + '</h1>' +
              '<p class="text-white/85 text-sm sm:text-base leading-relaxed mt-3 m-0 max-w-2xl">' + esc(d.description || '') + '</p>' +
            '</div>' +
          '</div>' +
          '<div class="flex items-center gap-2 flex-wrap mt-6">' +
            '<div class="bg-white/15 rounded-xl px-4 py-2.5 text-center"><div class="text-lg font-bold leading-none">' + courses.length + '</div><div class="text-[11px] text-white/70 mt-1">مادة</div></div>' +
            '<div class="bg-white/15 rounded-xl px-4 py-2.5 text-center"><div class="text-lg font-bold leading-none">' + totalUnits(courses) + '</div><div class="text-[11px] text-white/70 mt-1">وحدة</div></div>' +
            '<div class="bg-white/15 rounded-xl px-4 py-2.5 text-center"><div class="text-lg font-bold leading-none">' + (d.semesters || 0) + '</div><div class="text-[11px] text-white/70 mt-1">فصل</div></div>' +
            '<div class="bg-white/15 rounded-xl px-4 py-2.5 text-center"><div class="text-lg font-bold leading-none">' + (d.majors || 0) + '</div><div class="text-[11px] text-white/70 mt-1">تخصص</div></div>' +
          '</div>' +
          '<div class="flex items-center gap-2 flex-wrap mt-6 no-print">' +
            '<a href="#plan" class="inline-flex items-center gap-2 bg-white px-5 py-2.5 rounded-xl text-sm font-bold transition hover:shadow-xl" style="color:' + color + '"><span class="material-symbols-outlined text-lg">table_chart</span> الخطة الدراسية</a>' +
            '<a href="#objectives" class="inline-flex items-center gap-2 bg-white/15 hover:bg-white/25 px-5 py-2.5 rounded-xl text-sm font-bold transition"><span class="material-symbols-outlined text-lg">track_changes</span> أهداف القسم</a>' +
            '<a href="#careers" class="inline-flex items-center gap-2 bg-white/15 hover:bg-white/25 px-5 py-2.5 rounded-xl text-sm font-bold transition"><span class="material-symbols-outlined text-lg">work</span> فرص العمل</a>' +
          '</div>' +
        '</div>' +
      '</div>';
    }

    /* ---------- Intro Card ---------- */
    function introCard(d, color) {
      var p = d.profile;
      if (!p || !p.about) return '';
      return '<div class="print-block bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mb-6 print-sheet">' +
        '<div class="p-5 sm:p-6">' +
          '<div class="flex items-center gap-2.5 mb-3">' +
            '<span class="w-9 h-9 rounded-lg flex items-center justify-center text-white shrink-0" style="background:' + color + '"><span class="material-symbols-outlined text-lg">menu_book</span></span>' +
            '<div>' +
              '<h2 class="text-base font-bold text-text-primary m-0 leading-tight">مقدمة عن ' + esc(d.name) + '</h2>' +
              '<span class="text-[11px] text-text-muted">نبذة تعريفية عن القسم</span>' +
            '</div>' +
          '</div>' +
          '<p class="text-sm text-text-secondary leading-relaxed whitespace-pre-line m-0">' + esc(p.about) + '</p>' +
        '</div>' +
      '</div>';
    }

    function renderContent() {
      var el = document.getElementById('content');
      var d = currentDept;
      if (!d) {
        el.innerHTML = '<div class="bg-white rounded-2xl border border-dashed border-gray-200 py-16 text-center">' +
          '<span class="material-symbols-outlined text-[44px] text-text-faint">error</span>' +
          '<p class="text-text-secondary font-semibold mt-3">لم يتم العثور على القسم.</p></div>';
        return;
      }
      var color = d.accentColor || '#6b21a8';
      var courses = deptCourses(d);
      document.title = 'معلومات ' + d.name + ' — كلية التقنية الهندسية زوارة';
      el.innerHTML =
        renderHero(d, courses, color) +
        introCard(d, color) +
        '<h2 class="text-lg font-bold text-text-primary mb-3 mt-2 flex items-center gap-2"><span class="material-symbols-outlined" style="color:' + color + '">table_chart</span> الخطة الدراسية</h2>' +
        '<div id="plan" class="section-anchor">' + renderPlan(d, color) + '</div>' +
        '<h2 class="text-lg font-bold text-text-primary mb-3 mt-8 flex items-center gap-2"><span class="material-symbols-outlined" style="color:' + color + '">school</span> معلومات عن القسم</h2>' +
        renderProfile(d, color);
      window.scrollTo(0, 0);
    }

    async function load() {
      try {
        DEPTS = await DataClient.getDepartments();
        COURSES = await DataClient.getCourses();
        COURSE_BY_ID = {};
        COURSES.forEach(function (c) { COURSE_BY_ID[c.id] = c; });

        var pv = paramDept();
        currentDept = null;
        if (pv != null) {
          var num = parseInt(pv, 10);
          currentDept = isNaN(num) ? deptByName(pv) : deptById(num);
        }
        if (!currentDept) currentDept = DEPTS.length ? DEPTS[0] : null;
        renderSwitcher();
        renderContent();
      } catch (err) {
        document.getElementById('content').innerHTML =
          '<div class="bg-white rounded-2xl border border-dashed border-gray-200 py-16 text-center">' +
          '<span class="material-symbols-outlined text-[44px] text-text-faint">error</span>' +
          '<p class="text-text-secondary font-semibold mt-3">تعذر تحميل البيانات. تأكد من تشغيل الموقع عبر خادم محلي (HTTP).</p></div>';
        console.error(err);
      }
    }

    load();
