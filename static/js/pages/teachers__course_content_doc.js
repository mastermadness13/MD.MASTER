(function () {
  var WEEKS_LIMIT = 12;

  function initCurriculumSection(bodyId, addBtnId, totalInlineId, prefix, onTotal) {
    var body = document.getElementById(bodyId);
    if (!body) return;
    var addBtn = document.getElementById(addBtnId);
    var totalOut = document.getElementById(totalInlineId);

    function rowInputs(tr, name) {
      return tr.querySelector('[name="' + prefix + '_' + name + '[]"]');
    }

    function createRow() {
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td class="align-middle text-center font-bold text-black row-index"></td>' +
        '<td class="align-middle"><textarea name="' + prefix + '_curriculum_topic[]" rows="2" placeholder="الموضوع"></textarea></td>' +
        '<td class="align-middle"><input type="number" name="' + prefix + '_curriculum_weeks[]" min="1" value="1" class="text-center font-semibold week-input"></td>' +
        '<td class="align-middle"><textarea name="' + prefix + '_curriculum_topic_en[]" rows="2" dir="ltr" placeholder="Topic (EN)" class="font-[Inter] text-sm"></textarea></td>' +
        '<td class="align-middle text-center"><button type="button" class="cc-curriculum-remove text-red-500 hover:text-red-700 bg-red-50 hover:bg-red-100 p-1 rounded font-bold cursor-pointer text-xs" title="حذف الصف" aria-label="حذف الصف">✕</button></td>';
      attachRowHandlers(tr);
      return tr;
    }

    function attachRowHandlers(tr) {
      var inputs = tr.querySelectorAll('input[name^="' + prefix + '_curriculum_"], textarea[name^="' + prefix + '_curriculum_"]');
      inputs.forEach(function (inp) {
        inp.addEventListener('input', onCurriculumInput);
        inp.addEventListener('focus', onCurriculumFocus);
      });
      var rem = tr.querySelector('.cc-curriculum-remove');
      if (rem) {
        rem.addEventListener('click', function (e) {
          if (body.querySelectorAll('tr').length <= 1) return;
          var row = e.target.closest('tr');
          if (row) row.remove();
          renumberRows();
          recalc();
        });
      }
    }

    function isRowEmpty(tr) {
      var t = rowInputs(tr, 'curriculum_topic');
      var w = rowInputs(tr, 'curriculum_weeks');
      return !((t && t.value && t.value.trim()) || (w && w.value && w.value.trim()));
    }

    function maybeAddRow() {
      var rows = body.querySelectorAll('tr');
      var last = rows[rows.length - 1];
      if (last && !isRowEmpty(last)) {
        body.appendChild(createRow());
        renumberRows();
      }
      recalc();
    }

    function onCurriculumInput(e) {
      var tr = e.target.closest('tr');
      var rows = body.querySelectorAll('tr');
      var last = rows[rows.length - 1];
      if (tr === last && !isRowEmpty(last)) {
        body.appendChild(createRow());
        renumberRows();
      }
      recalc();
    }

    function onCurriculumFocus(e) {
      var tr = e.target.closest('tr');
      var rows = body.querySelectorAll('tr');
      var last = rows[rows.length - 1];
      if (tr === last && !isRowEmpty(last)) {
        body.appendChild(createRow());
        renumberRows();
        recalc();
      }
    }

    function renumberRows() {
      var i = 1;
      body.querySelectorAll('tr').forEach(function (tr) {
        var cell = tr.querySelector('td:first-child');
        if (cell) {
          cell.textContent = i;
          var idx = tr.querySelector('.row-index');
          if (idx && idx !== cell) idx.textContent = i;
        }
        i++;
      });
    }

    function recalc() {
      var sum = 0;
      body.querySelectorAll('tr').forEach(function (tr) {
        if (isRowEmpty(tr)) return;
        var w = rowInputs(tr, 'curriculum_weeks');
        sum += parseInt(w && w.value || 0, 10) || 0;
      });
      if (totalOut) {
        totalOut.textContent = sum;
        totalOut.classList.toggle('weeks-warning', sum > WEEKS_LIMIT);
      }
      if (onTotal) onTotal(sum);
      return sum;
    }

    if (addBtn) addBtn.addEventListener('click', function () { body.appendChild(createRow()); renumberRows(); });

    body.querySelectorAll('tr').forEach(attachRowHandlers);
    renumberRows();
    recalc();
  }

  // First empty row for a fresh sheet: keep weeks at 1
  var theoreticalBody = document.getElementById('ccTheoreticalCurriculumBody');
  if (theoreticalBody) {
    var rows = theoreticalBody.querySelectorAll('tr');
    var topicInput = rows[0].querySelector('[name$="curriculum_topic[]"]');
    if (rows.length === 1 && topicInput && !topicInput.value) {
      var weeks = rows[0].querySelector('input[name$="curriculum_weeks[]"]');
      if (weeks) weeks.value = 1;
    }
  }

  var theoreticalWeeksTotal = 0;
  initCurriculumSection('ccTheoreticalCurriculumBody', 'ccAddTheoreticalRow', 'ccTheoreticalWeeksTotal', 'theoretical', function (sum) {
    theoreticalWeeksTotal = sum;
  });

  // Block submission when total theoretical weeks exceed the limit (12).
  var courseContentFormEl = document.getElementById('courseContentForm');
  if (courseContentFormEl) {
    courseContentFormEl.addEventListener('submit', function (e) {
      if (theoreticalWeeksTotal > WEEKS_LIMIT) {
        e.preventDefault();
        var msg = 'إجمالي الأسابيع النظرية (' + theoreticalWeeksTotal + ') يتجاوز الحد المسموح (' + WEEKS_LIMIT + ') — لا يمكن الحفظ أو النشر.';
        if (window.showNotification) {
          window.showNotification(msg, 'error', 6000);
        } else {
          alert(msg);
        }
      }
    });
  }

  // Hour inputs: sum theory + practical + tutorial into hidden total_hours
  var hourInputs = ['theory_hours', 'practical_hours', 'tutorial_hours'];
  function recalcHours() {
    var total = 0;
    hourInputs.forEach(function (name) {
      var el = document.querySelector('[name="' + name + '"]');
      if (el) total += parseInt(el.value || 0, 10) || 0;
    });
    var t = document.querySelector('[name="total_hours"]');
    if (t) t.value = total;

    ['theory_hours', 'practical_hours', 'tutorial_hours', 'total_hours', 'credits', 'semester'].forEach(function (name) {
      var main = document.querySelector('[name="' + name + '"]');
      if (!main) return;
      var mirrors = document.querySelectorAll('[data-mirror="' + name + '"]');
      mirrors.forEach(function (m) { m.value = main.value; });
    });
  }

  function addListeners(el, handler) {
    if (!el) return;
    el.addEventListener('input', handler);
    el.addEventListener('change', handler);
  }

  function wireSync(name) {
    var main = document.querySelector('[name="' + name + '"]');
    if (main) {
      addListeners(main, function () {
        var mirrors = document.querySelectorAll('[data-mirror="' + name + '"]');
        mirrors.forEach(function (m) { m.value = main.value; });
        if (hourInputs.indexOf(name) !== -1) recalcHours();
      });
    }
    var mirrors = document.querySelectorAll('[data-mirror="' + name + '"]');
    mirrors.forEach(function (m) {
      addListeners(m, function () {
        var target = document.querySelector('[name="' + name + '"]');
        if (target) target.value = m.value;
        if (hourInputs.indexOf(name) !== -1) recalcHours();
      });
    });
  }

  ['theory_hours', 'practical_hours', 'tutorial_hours', 'total_hours', 'credits', 'semester'].forEach(wireSync);
  recalcHours();

  // Force English (Latin) digits everywhere in the sheet, including any
  // Arabic-Indic/Persian digits a user may type.
  function toLatinDigits(v) {
    return String(v || '')
      .replace(/[\u0660-\u0669]/g, function (d) { return String.fromCharCode(d.charCodeAt(0) - 0x0660 + 0x30); })
      .replace(/[\u06F0-\u06F9]/g, function (d) { return String.fromCharCode(d.charCodeAt(0) - 0x06F0 + 0x30); });
  }
  document.addEventListener('input', function (e) {
    var el = e.target;
    if (el && el.matches && el.matches('input[type="number"]')) {
      var latin = toLatinDigits(el.value);
      if (latin !== el.value) {
        el.value = latin;
        recalcHours();
      }
    }
  });

  // Enter-key navigation: move to next empty input (or next) on Enter
  var form = document.getElementById('courseContentForm');
  if (form) {
    function inputsInOrder() {
      return Array.prototype.slice.call(form.querySelectorAll('input:not([type=hidden]), select, textarea'))
        .filter(function (el) { return el.offsetParent !== null; });
    }
    form.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      var active = document.activeElement;
      if (!form.contains(active)) return;
      if (active.tagName === 'TEXTAREA') return;
      e.preventDefault();
      var inputs = inputsInOrder();
      var idx = inputs.indexOf(active);
      if (idx === -1) return;
      var forward = !e.shiftKey;
      var next = null;
      if (forward) {
        for (var i = idx + 1; i < inputs.length; i++) {
          if (!inputs[i].value) { next = inputs[i]; break; }
        }
        if (!next) next = inputs[idx + 1] || inputs[inputs.length - 1];
      } else {
        for (var i = idx - 1; i >= 0; i--) {
          if (!inputs[i].value) { next = inputs[i]; break; }
        }
        if (!next) next = inputs[idx - 1] || inputs[0];
      }
      if (next) next.focus();
    });
  }

})();

window.downloadCourseSheet = function () {
  var sheet = document.querySelector('.cc-sheet');
  if (!sheet) return;

  var clone = sheet.cloneNode(true);
  clone.querySelectorAll('.no-print').forEach(function (el) { el.remove(); });
  clone.querySelectorAll('input, textarea, select').forEach(function (el) {
    if (el.type === 'hidden') { el.remove(); return; }
    if (el.disabled || el.readOnly) {
      el.removeAttribute('disabled');
      el.removeAttribute('readonly');
    }
    var span = document.createElement('span');
    if (el.tagName === 'SELECT') {
      var selOpt = el.options[el.selectedIndex];
      span.textContent = (selOpt && selOpt.textContent && selOpt.textContent.trim()) ? selOpt.textContent : '';
    } else {
      span.textContent = el.value || el.placeholder || '';
    }
    if (el.getAttribute('dir')) span.setAttribute('dir', el.getAttribute('dir'));
    span.style.fontWeight = '600';
    el.parentNode.replaceChild(span, el);
  });

  var sheetStyle = document.getElementById('ccSheetStyle');
  var css = sheetStyle ? sheetStyle.textContent : '';

  var codeEl = document.querySelector('.cc-sheet');
  var courseCode = (codeEl && codeEl.getAttribute('data-course-code')) || 'course';
  var title = 'مفردات مقرر ' + courseCode;

  var html =
    '<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">' +
    '<title>' + title + '</title>' +
    '<link rel="preconnect" href="https://fonts.googleapis.com">' +
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' +
    '<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">' +
    '<script src="https://cdn.tailwindcss.com"><\/script>' +
    '<style>' + css + '</style>' +
    '</head><body class="bg-slate-100 p-4 sm:p-8">' + clone.outerHTML + '</body></html>';

  var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'course-' + courseCode + '.html';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);

  if (window.showNotification) {
    window.showNotification('تم تجهيز ملف المقرر للتحميل', 'success', 4000);
  }
};