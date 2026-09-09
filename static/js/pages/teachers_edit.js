document.addEventListener('DOMContentLoaded', function () {
  (function () {
    var specSel = document.getElementById('edit_specialization');
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
});
