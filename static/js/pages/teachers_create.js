document.addEventListener('DOMContentLoaded', function () {
  // ── Specialization filtered by linked department checkboxes ──
  (function () {
    var specSel = document.getElementById('create_specialization');
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

  // ── Headship department shown only when task = 'رئيس قسم' ──
  (function () {
    var posSel = document.getElementById('positionSelect');
    var hodWrap = document.getElementById('headshipDeptWrap');
    if (!posSel || !hodWrap) return;
    function toggleHead() {
      hodWrap.style.display = posSel.value === 'رئيس قسم' ? '' : 'none';
    }
    posSel.addEventListener('change', toggleHead);
    toggleHead();
  })();

  // ── Decisions: add a visual row (مسترشد به فقط) ──
  window.addDecisionRow = function () {
    var wrap = document.getElementById('decisionsWrap');
    if (!wrap) return;
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
});
