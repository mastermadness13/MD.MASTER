(function () {
  var body = document.getElementById('ccCurriculumBody');
  if (body) {
    var rows = body.querySelectorAll('tr');
    if (rows.length === 1 && !rows[0].querySelector('input[name="curriculum_topic[]"]').value) {
      rows[0].querySelector('input[name="curriculum_weeks[]"]').value = 1;
    }
    var addBtn = document.getElementById('ccAddCurriculumRow');
    var autoToggle = document.getElementById('ccAutoAddToggle');

    function createRow() {
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td class="align-top text-center font-bold text-black"></td>' +
        '<td class="align-top"><input type="text" name="curriculum_topic[]" placeholder="الموضوع"></td>' +
        '<td class="align-top"><input type="text" name="curriculum_content[]" placeholder="المحتوى"></td>' +
        '<td class="align-top"><input type="number" name="curriculum_weeks[]" min="1" value="1"></td>' +
        '<td class="align-top"><input type="text" name="curriculum_topic_en[]" dir="ltr" placeholder="Topic (EN)"></td>' +
        '<td class="align-top"><input type="text" name="curriculum_content_en[]" dir="ltr" placeholder="Content (EN)"></td>' +
        '<td class="align-top text-center"><button type="button" class="cc-curriculum-remove material-symbols-outlined text-red-500 hover:text-red-600 bg-transparent border-0 cursor-pointer" title="حذف">delete</button></td>';
      attachRowHandlers(tr);
      return tr;
    }

    function attachRowHandlers(tr) {
      var inputs = tr.querySelectorAll('input[name="curriculum_topic[]"], input[name="curriculum_topic_en[]"], input[name="curriculum_weeks[]"], input[name="curriculum_content[]"], input[name="curriculum_content_en[]"]');
      inputs.forEach(function (inp) {
        inp.addEventListener('input', onCurriculumInput);
        inp.addEventListener('focus', onCurriculumFocus);
      });
      var rem = tr.querySelector('.cc-curriculum-remove');
      if (rem) rem.addEventListener('click', function (e) { 
        if (body.querySelectorAll('tr').length <= 1) return; 
        e.target.closest('tr').remove();
        renumberRows();
        recalcCurriculumWeeks();
      });
    }

    function onCurriculumInput(e) {
      var tr = e.target.closest('tr');
      // if auto-add enabled and this is last row and it has content, append a blank row
      var rows = body.querySelectorAll('tr');
      var last = rows[rows.length - 1];
      if (autoToggle && autoToggle.checked && tr === last) {
        if (!isRowEmpty(last)) {
          body.appendChild(createRow());
          renumberRows();
          recalcCurriculumWeeks();
        }
      }
      recalcCurriculumWeeks();
    }

    function onCurriculumFocus(e) {
      var tr = e.target.closest('tr');
      var rows = body.querySelectorAll('tr');
      var last = rows[rows.length - 1];
      if (autoToggle && autoToggle.checked && tr === last) {
        if (!isRowEmpty(last)) {
          body.appendChild(createRow());
          renumberRows();
          recalcCurriculumWeeks();
        }
      }
      // don't force recalc here — input handler covers value changes
    }

    function isRowEmpty(tr) {
      var t = tr.querySelector('input[name="curriculum_topic[]"]');
      var w = tr.querySelector('input[name="curriculum_weeks[]"]');
      var c = tr.querySelector('input[name="curriculum_content[]"]');
      return !( (t && t.value && t.value.trim()) || (w && w.value && w.value.trim()) || (c && c.value && c.value.trim()) );
    }

    function renumberRows() {
      var i = 1;
      body.querySelectorAll('tr').forEach(function (tr) {
        var cell = tr.querySelector('td:first-child');
        if (cell) cell.textContent = i;
        i++;
      });
    }

    if (addBtn) addBtn.addEventListener('click', function(){ body.appendChild(createRow()); renumberRows(); });

    // initialize existing rows handlers
    body.querySelectorAll('tr').forEach(function (tr) { attachRowHandlers(tr); });
    renumberRows();
    recalcCurriculumWeeks();
  }

  function recalcCurriculumWeeks() {
    var sum = 0;
    var els = document.querySelectorAll('input[name="curriculum_weeks[]"]');
    els.forEach(function (el) { sum += parseInt(el.value || 0, 10) || 0; });
    var out = document.getElementById('ccWeeksTotal');
    if (out) out.textContent = sum;
    var out2 = document.getElementById('ccWeeksTotalInline');
    if (out2) out2.textContent = sum;
    // highlight & shift when total exceeds 12 weeks
    var over = sum > 12;
    if (out) out.classList.toggle('weeks-warning', over);
    if (out2) out2.classList.toggle('weeks-warning', over);
  }

  // Hour inputs: sum theory + practical into total
  var hourInputs = ['theory_hours', 'practical_hours'];
  function recalcHours() {
    var total = 0;
    hourInputs.forEach(function (name) {
      var el = document.querySelector('[name="' + name + '"]');
      if (el) total += parseInt(el.value || 0, 10) || 0;
    });
    var t = document.querySelector('[name="total_hours"]');
    if (t) t.value = total;

    // sync mirrors for common fields
    ['theory_hours','practical_hours','total_hours','credits','semester'].forEach(function(name){
      var main = document.querySelector('[name="' + name + '"]');
      if (!main) return;
      var mirrors = document.querySelectorAll('[data-mirror="' + name + '"]');
      mirrors.forEach(function(m){ m.value = main.value; });
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
        if (hourInputs.indexOf(name) !== -1 || name === 'total_hours') recalcHours();
      });
    }
    var mirrors = document.querySelectorAll('[data-mirror="' + name + '"]');
    mirrors.forEach(function (m) {
      addListeners(m, function () {
        var main = document.querySelector('[name="' + name + '"]');
        if (main) main.value = m.value;
        if (hourInputs.indexOf(name) !== -1 || name === 'total_hours') recalcHours();
      });
    });
  }

  ['theory_hours','practical_hours','total_hours','credits','semester'].forEach(wireSync);
  recalcHours();

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
      if (active.tagName === 'TEXTAREA') return; // allow newline
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
