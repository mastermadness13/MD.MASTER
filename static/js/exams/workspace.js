/**
 * Exam workspace shell — boots the role-aware exam matrix and provides
 * toast/esc/print helpers shared by the exams UI.
 */
(function () {
  'use strict';

  var root = document.getElementById('exams-workspace');
  if (!root) return;

  var role = root.getAttribute('data-role') || '';
  var panel = document.getElementById('panel-schedule');

  window.ExamToast = function (msg, isError) {
    var t = document.getElementById('exam-toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'exam-toast';
      document.body.appendChild(t);
    }
    t.className = 'exam-toast' + (isError ? ' exam-toast-error' : '');
    t.textContent = msg;
    requestAnimationFrame(function () { t.classList.add('show'); });
    clearTimeout(t._t);
    t._t = setTimeout(function () { t.classList.remove('show'); }, 3400);
  };

  var PRINT_DAYS = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس'];

  function normDay(d) { return String(d || '').replace('الإثنين', 'الاثنين'); }

  function buildPrintSheets(dept, period, yearLabel, semStart, semEnd) {
    if (!dept) {
      return '<div style="text-align:center; padding:48px 24px; color:#4b4450; background:white; border:1px solid #CFC2D3; border-radius:8px;">لا توجد بيانات امتحانات لعرضها</div>';
    }
    var semLabels = dept.semesterLabels || [];
    var weeks = (dept.weeks || []).slice().sort(function (a, b) { return a - b; });
    var sheets = '';

    weeks.forEach(function (week) {
      var weekExams = (dept.exams || []).filter(function (e) { return Number(e.week) === Number(week); });
      if (!weekExams.length) return;
      var wk = String(week);
      var dayDates = (dept.dateMap && dept.dateMap[wk]) || {};
      var dayDisplays = (dept.dateDisplayMap && dept.dateDisplayMap[wk]) || {};

      var headers = '<th style="width:80px; padding:6px 5px; font-weight:700; color:#0b1c30;">اليوم</th>';
      semLabels.forEach(function (label) {
        headers += '<th style="padding:6px 5px; font-weight:700; color:#0b1c30;">' + escapeHtml(label) + '</th>';
      });

      var body = '';
      PRINT_DAYS.forEach(function (day) {
        var raw = dayDates[day] || '';
        var ar = dayDisplays[day] || '';
        var datePart = '';
        if (ar) {
          datePart = '<span style="font-size:11px; font-weight:400; color:#4b4450; margin-top:2px; display:block;">' + ar + '</span>';
        } else if (raw) {
          var pt = raw.split('-');
          datePart = '<span style="font-size:11px; font-weight:400; color:#4b4450; margin-top:2px; display:block;">' +
            (parseInt(pt[2], 10) + '/' + parseInt(pt[1], 10)) + '</span>';
        }
        body += '<tr><td style="font-weight:700; background:#f8f9ff; vertical-align:middle; padding:8px 5px;">' +
          day + '<br>' + datePart + '</td>';

        semLabels.forEach(function (label, si) {
          var sem = Number(dept.semStart) + si;
          var matched = weekExams.filter(function (e) {
            return normDay(e.day) === day && Number(e.semester) === Number(sem);
          });
          if (!matched.length) {
            body += '<td style="color:#4b4450; text-align:center; vertical-align:middle; padding:8px 5px;">-</td>';
            return;
          }
          var e = matched[0];
          var isPractical = e.type === 'practical';
          body += '<td class="' + (isPractical ? 'exam-cell-practical' : 'exam-cell-written') +
            '" style="vertical-align:top; padding:8px 6px;">' +
            '<div style="font-weight:700; font-size:11px; text-align:center; color:#320058; margin-bottom:4px; line-height:1.2;">' + escapeHtml(e.course || '—') + '</div>' +
            '<div class="' + (isPractical ? 'exam-badge-practical' : 'exam-badge-written') +
            '" style="font-size:9px; padding:1px 6px; border-radius:3px; display:inline-block; font-weight:500;">' +
            (isPractical ? 'عملي' : 'نظري') + '</div>' +
            '<div style="font-size:10px; margin-top:4px; padding-top:4px; border-top:1px solid rgba(0,0,0,0.1); display:flex; flex-direction:column; gap:2px; text-align:right;">' +
            '<span style="font-weight:500; white-space:nowrap;">القاعة: ' + escapeHtml(e.hall || '—') + '</span>' +
            '<span style="font-weight:500; white-space:nowrap;" dir="ltr">' + escapeHtml(e.time || '—') + '</span>' +
            '</div></td>';
        });
        body += '</tr>';
      });

      var periodLine = '';
      if (semStart) {
        periodLine = '<p style="margin:0; font-size:11px;">فترة الامتحانات: ' + semStart + ' — ' + (semEnd || '') + '</p>';
      }

      sheets += '' +
        '<div class="a4-document print-sheet">' +
          '<header class="exam-print-header" style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px; padding-bottom:10px;">' +
            '<div style="text-align:right; flex:1;">' +
              '<h2 style="font-size:14px; font-weight:700; color:#320058; margin:0 0 2px 0; line-height:1.3;">كلية التقنية الهندسية زوارة</h2>' +
              '<p style="font-size:12px; color:#4b4450; margin:0;">' + escapeHtml(dept.name) + '</p>' +
            '</div>' +
            '<div style="text-align:center; flex:1; display:flex; flex-direction:column; align-items:center;">' +
              '<img src="/static/image/logo.png" alt="شعار الكلية" style="width:44px; height:44px; object-fit:contain; margin-bottom:4px;">' +
              '<h1 style="font-size:20px; font-weight:700; color:#320058; margin:0; line-height:1.2;">جدول الامتحانات</h1>' +
            '</div>' +
            '<div style="text-align:left; flex:1; color:#4b4450; font-size:12px;">' +
              '<p style="margin:0 0 2px 0;">سنة ' + escapeHtml(yearLabel || '—') + '</p>' +
              '<p style="margin:0 0 2px 0;">الأسبوع ' + week + '</p>' +
              periodLine +
            '</div>' +
          '</header>' +
          '<div style="flex:1;">' +
            '<table class="exam-grid" style="text-align:center; font-size:11px; width:100%; table-layout:fixed;">' +
              '<thead><tr style="background:#eff4ff;">' + headers + '</tr></thead>' +
              '<tbody>' + body + '</tbody>' +
            '</table>' +
          '</div>' +
          '<div style="margin-top:auto; padding-top:24px; display:flex; justify-content:space-between; align-items:flex-end;">' +
            '<div style="text-align:center; width:200px; border-top:1px solid #7d7481; padding-top:8px;">' +
              '<p style="font-weight:500; color:#0b1c30; margin:0; font-size:12px;">توقيع رئيس القسم</p>' +
            '</div>' +
            '<div style="text-align:center; width:200px; border-top:1px solid #7d7481; padding-top:8px;">' +
              '<p style="font-weight:500; color:#0b1c30; margin:0; font-size:12px;">اعتماد إدارة الكلية</p>' +
            '</div>' +
          '</div>' +
        '</div>';
    });

    return sheets || (
      '<div style="text-align:center; padding:48px 24px; color:#4b4450; background:white; border:1px solid #CFC2D3; border-radius:8px;">لا توجد بيانات امتحانات لعرضها</div>'
    );
  }

  window.ExamPrint = function () {
    var area = document.getElementById('exam-print-area');
    var state = (window.ExamSchedule && window.ExamSchedule.getState) ? window.ExamSchedule.getState() : null;
    var yearLabel = root.getAttribute('data-year') || '';
    if (state && state.period && state.period.yearLabel && !yearLabel) yearLabel = state.period.yearLabel;
    if (area) {
      area.innerHTML = buildPrintSheets(
        state && state.dept, state && state.period, yearLabel,
        state ? state.semesterExamStart : '', state ? state.semesterExamEnd : ''
      );
    }
    window.print();
  };

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  window.ExamEsc = escapeHtml;

  // head_of_department sees only their own department (the API already
  // filters it server-side); everyone else gets the full matrix.
  var scoped = role === 'head_of_department';

  if (window.ExamSchedule && typeof window.ExamSchedule.init === 'function' && panel) {
    window.ExamSchedule.init(panel, { role: role, scoped: scoped });
  }

  var printBtn = document.getElementById('ws-print');
  if (printBtn) printBtn.addEventListener('click', window.ExamPrint);

  var periodStart = document.getElementById('period-start');
  var periodEnd = document.getElementById('period-end');
  var periodSave = document.getElementById('period-save');
  var periodHint = document.getElementById('period-hint');
  var canManagePeriod = role === 'exam';

  function refreshPeriodEditor() {
    if (!canManagePeriod || !periodStart || !periodEnd) return;
    window.Exams.api.get('/api/exams/semester-period').then(function (data) {
      var sem = data && data.semester ? data.semester : null;
      if (!sem) {
        periodStart.disabled = true;
        periodEnd.disabled = true;
        if (periodSave) periodSave.disabled = true;
        if (periodHint) periodHint.textContent = 'لا يوجد فصل دراسي نشط';
        return;
      }
      periodStart.disabled = false;
      periodEnd.disabled = false;
      if (periodSave) periodSave.disabled = false;
      periodStart.value = sem.exam_start_date || '';
      periodEnd.value = sem.exam_end_date || '';
      if (periodHint) periodHint.textContent = 'الافتراضي تلقائي — آخر أسبوعين من الفصل الدراسي (قابل للتعديل)';
    }).catch(function (err) {
      if (periodHint) periodHint.textContent = err.message;
    });
  }

  if (periodSave) {
    periodSave.addEventListener('click', function () {
      var start = periodStart.value;
      var end = periodEnd.value;
      if (!start || !end) { window.ExamToast('يرجى تحديد تاريخ البداية والنهاية', true); return; }
      if (start > end) { window.ExamToast('تاريخ النهاية يجب أن يكون بعد تاريخ البداية', true); return; }
      periodSave.disabled = true;
      window.Exams.api.put('/api/exams/semester-period', {
        exam_start_date: start,
        exam_end_date: end
      }).then(function () {
        window.ExamToast('تم حفظ فترة الامتحانات');
        periodSave.disabled = false;
        if (window.ExamSchedule && typeof window.ExamSchedule.init === 'function' && panel) {
          window.ExamSchedule.init(panel, { role: role, scoped: scoped });
        }
      }).catch(function (err) {
        periodSave.disabled = false;
        window.ExamToast(err.message, true);
      });
    });
    refreshPeriodEditor();
  }

  window.ExamWorkspace = {
    role: role,
    scoped: scoped
  };
})();
