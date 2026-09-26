document.addEventListener('DOMContentLoaded', function () {
  // ── Editable selects: pick an existing option OR type a new value ──
  document.querySelectorAll('[data-editable-toggle]').forEach(function (btn) {
    var field = btn.getAttribute('data-editable-toggle');
    var wrap = document.querySelector('[data-editable-wrap="' + field + '"]');
    var input = document.querySelector('[data-editable-input="' + field + '"]');
    var select = document.querySelector('[data-editable-select="' + field + '"]');
    if (!wrap || !input || !select) return;

    function sync() {
      var has = (input.value || '').trim().length > 0;
      if (has) {
        select.value = '';
        select.disabled = true;
      } else {
        select.disabled = false;
      }
    }

    btn.addEventListener('click', function () {
      var hidden = wrap.style.display === 'none';
      wrap.style.display = hidden ? 'flex' : 'none';
      if (hidden) input.focus();
    });

    input.addEventListener('input', function () {
      if ((input.value || '').trim().length > 0) {
        select.value = '';
        select.disabled = true;
      } else {
        select.disabled = false;
      }
    });

    select.addEventListener('change', function () {
      if (select.value) {
        input.value = '';
        wrap.style.display = 'none';
        select.disabled = false;
      }
    });

    sync();
  });

  // ── Specialization filtered by linked department checkboxes ──
  (function () {
    var specSel = document.getElementById('create_specialization') || document.getElementById('edit_specialization');
    if (!specSel) return;
    var cache = [];
    specSel.querySelectorAll('option[data-dept]').forEach(function (o) {
      cache.push({ id: o.value, dept: o.getAttribute('data-dept'), name: o.textContent });
    });
    function render() {
      var checked = [];
      document.querySelectorAll('input[name="department_ids[]"]:checked').forEach(function (cb) {
        checked.push(cb.value);
      });
      var prev = specSel.value;
      specSel.innerHTML = '<option value="">اختر التخصص (اختياري)</option>';
      cache.forEach(function (s) {
        if (checked.length === 0 || checked.indexOf(s.dept) !== -1) {
          var o = document.createElement('option');
          o.value = s.id;
          o.textContent = s.name;
          specSel.appendChild(o);
        }
      });
      if (prev && cache.some(function (s) { return s.id === prev && (checked.length === 0 || checked.indexOf(s.dept) !== -1); })) {
        specSel.value = prev;
      }
    }
    document.querySelectorAll('input[name="department_ids[]"]').forEach(function (cb) {
      cb.addEventListener('change', render);
    });
    render();
  })();

  // ── Headship department shown only for the academic department head ──
  (function () {
    var posSel = document.getElementById('positionSelect');
    var hodWrap = document.getElementById('headshipDeptWrap');
    var teachingDeptWrap = document.getElementById('teachingDeptWrap');
    if (!posSel) return;
    function toggleHead() {
      if (hodWrap) hodWrap.style.display = ['رئيس القسم العلمي', 'رئيس قسم', 'رئيس القسم'].indexOf(posSel.value) !== -1 ? '' : 'none';
      if (teachingDeptWrap) teachingDeptWrap.style.display = posSel.value === 'عضو تدريس' ? '' : 'none';
    }
    // تلوين ذهبي للخيارات التي تمنح لوحة تحكم إدارية
    var panelTasks = ['رئيس القسم العلمي', 'رئيس قسم', 'رئيس القسم', 'رئيس قسم البحث والتطوير', 'مدير مكتب أعضاء هيئة التدريس',
                      'رئيس قسم الدراسة والامتحانات', 'مكتب إدارة أعضاء هيئة التدريس'];
    function tintPanel() {
      var gold = panelTasks.indexOf(posSel.value) !== -1;
      posSel.classList.toggle('text-amber-600', gold);
      posSel.classList.toggle('font-bold', gold);
      posSel.classList.toggle('text-on-surface', !gold);
    }
    posSel.addEventListener('change', toggleHead);
    posSel.addEventListener('change', tintPanel);
    toggleHead();
    tintPanel();
  })();

  // ── Confirm-replace row shown only for an occupied department ──
  (function () {
    var hodSel = document.getElementById('hodDepartmentSelect');
    var confirmWrap = document.getElementById('confirmReplaceWrap');
    var confirmBox = document.getElementById('confirmReplaceHod');
    if (!hodSel || !confirmWrap) return;
    function updateConfirmVisibility() {
      var opt = hodSel.options[hodSel.selectedIndex];
      var occupied = opt ? opt.getAttribute('data-occupied') === '1' : false;
      confirmWrap.style.display = occupied ? 'flex' : 'none';
      if (!occupied && confirmBox) confirmBox.checked = false;
    }
    hodSel.addEventListener('change', updateConfirmVisibility);
    updateConfirmVisibility();
  })();

  // ── Decisions: add a visual row (مسترشد به فقط) ──
  (function () {
    var wrap = document.getElementById('decisionsWrap');
    if (!wrap) return;
    window.addDecisionRow = function () {
      var first = wrap.querySelector('.decision-row');
      if (!first) return;
      var clone = first.cloneNode(true);
      clone.querySelectorAll('input, select').forEach(function (el) {
        el.value = '';
      });
      var removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'md:col-span-4 text-red-600 hover:text-red-700 font-label-md flex items-center gap-1 justify-end';
      removeBtn.innerHTML = '<span class="material-symbols-outlined text-[16px]">close</span> حذف القرار';
      removeBtn.addEventListener('click', function () {
        wrap.removeChild(clone);
      });
      clone.appendChild(removeBtn);
      wrap.appendChild(clone);
    };
  })();
});