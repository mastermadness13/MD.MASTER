// Shared pure helpers for the timetable views (rnd / department / combined).
// Usage: var H = window.TimetableHelpers.create({ periods: periods, base: BASE });
//        var esc = H.esc, qs = H.qs, ...;
// `periods` is bound for periodByCode()/entryTime(); `base` is bound for nav().
window.TimetableHelpers = (function () {
  function create(options) {
    var periods = (options && options.periods) || [];
    var BASE = (options && options.base) || '';

    /* All five markup-significant characters, including the apostrophe so the
     * result is safe inside single-quoted attributes too. */
    function esc(s) {
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function semesterNumLabel(s) {
      var names = {1: 'الأول', 2: 'الثاني', 3: 'الثالث', 4: 'الرابع', 5: 'الخامس', 6: 'السادس', 7: 'السابع'};
      return names[s] || '—';
    }
    function fmtTime12(v) {
      if (!v) return v || '';
      var m = String(v).match(/^(\d{1,2}):(\d{2})$/);
      if (!m) return v;
      var h = parseInt(m[1], 10), min = m[2];
      var period = h < 12 ? 'ص' : 'م';
      var h12 = h % 12; if (h12 === 0) h12 = 12;
      return h12 + ':' + min + ' ' + period;
    }
    function periodTime(p) {
      if (p && p.start_time) return fmtTime12(p.start_time) + (p.end_time ? ' ← ' + fmtTime12(p.end_time) : '');
      return '';
    }
    function periodByCode(code) {
      for (var i = 0; i < periods.length; i++) if (periods[i].code === code) return periods[i];
      return null;
    }
    function entryTime(e) {
      if (e && e.start_time) return fmtTime12(e.start_time) + (e.end_time ? ' ← ' + fmtTime12(e.end_time) : '');
      var p = periodByCode(e && e.period);
      return periodTime(p);
    }
    function typeLabel(t) { return t === 'practical' ? 'عملي' : 'نظري'; }
    function cleanTeacher(name) {
      var s = String(name == null ? '' : name).trim();
      var prefixes = ['أ .', 'أ.', 'د .', 'د.'];
      for (var i = 0; i < prefixes.length; i++) {
        if (s.indexOf(prefixes[i]) === 0) { s = s.slice(prefixes[i].length).trim(); break; }
      }
      return s || '—';
    }
    function durationLabel(e) {
      if (!e) return '';
      var st = e.start_time, et = e.end_time;
      if (!st || !et) {
        var p = periodByCode(e.period);
        if (p) { st = p.start_time; et = p.end_time; }
      }
      if (!st || !et) return '';
      var sp = String(st).split(':'), ep = String(et).split(':');
      if (sp.length < 2 || ep.length < 2) return '';
      var totalMin = (parseInt(ep[0], 10) * 60 + parseInt(ep[1], 10)) - (parseInt(sp[0], 10) * 60 + parseInt(sp[1], 10));
      if (totalMin <= 0) return '';
      var h = Math.floor(totalMin / 60);
      if (h === 1) return 'ساعة';
      if (h === 2) return 'ساعتان';
      if (h >= 11) return h + ' ساعة';
      return h + ' ساعات';
    }
    function fmtDate(ts) {
      if (!ts) return '—';
      var d = new Date(ts);
      if (isNaN(d.getTime())) return '—';
      function p(x) { return (x < 10 ? '0' : '') + x; }
      return d.getFullYear() + '/' + p(d.getMonth() + 1) + '/' + p(d.getDate());
    }
    function qs(params) {
      var out = [];
      for (var k in params) if (params[k] !== undefined && params[k] !== null && params[k] !== '') out.push(encodeURIComponent(k) + '=' + encodeURIComponent(params[k]));
      return out.length ? '?' + out.join('&') : '';
    }
    function nav(params) {
      location.href = BASE + qs(params);
    }

    return {
      esc: esc,
      semesterNumLabel: semesterNumLabel,
      fmtTime12: fmtTime12,
      periodTime: periodTime,
      entryTime: entryTime,
      periodByCode: periodByCode,
      typeLabel: typeLabel,
      cleanTeacher: cleanTeacher,
      durationLabel: durationLabel,
      fmtDate: fmtDate,
      qs: qs,
      nav: nav
    };
  }

  return { create: create };
})();