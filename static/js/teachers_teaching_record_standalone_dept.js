// cascade
(function () {
  var BOOT = window.TEACHERS_TEACHING_RECORD_STANDALONE_BOOT || {};
  var URLS = BOOT.urls || {};
  /* Teacher names come from the by-department API and are unvalidated beyond
   * .strip(), so escape before concatenating into the <option> markup. */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
document.getElementById('tr-dept-select').addEventListener('change', function() {
  var deptId = this.value;
  var teacherSelect = document.getElementById('tr-teacher-select');
  var loading = document.getElementById('tr-teacher-loading');

  if (!deptId) {
    teacherSelect.innerHTML = '<option value="">— اختر القسم أولاً —</option>';
    teacherSelect.disabled = true;
    return;
  }

  loading.classList.remove('hidden');
  teacherSelect.disabled = true;
  teacherSelect.innerHTML = '<option value="">جاري التحميل...</option>';

  fetch(URLS.byDept + '?department_id=' + deptId)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      loading.classList.add('hidden');
      if (data.length === 0) {
        teacherSelect.innerHTML = '<option value="">— لا يوجد أساتذة في هذا القسم —</option>';
      } else {
        var html = '<option value="">— اختر عضو هيئة التدريس —</option>';
        data.forEach(function(t) {
          html += '<option value="' + t.id + '">' + esc(t.name) + (t.academic_number ? ' (' + esc(t.academic_number) + ')' : '') + '</option>';
        });
        teacherSelect.innerHTML = html;
      }
      teacherSelect.disabled = false;
    })
    .catch(function() {
      loading.classList.add('hidden');
      teacherSelect.innerHTML = '<option value="">— خطأ في التحميل —</option>';
      teacherSelect.disabled = false;
    });
});

(function() {
  var deptSelect = document.getElementById('tr-dept-select');
  var teacherSelect = document.getElementById('tr-teacher-select');
  if (deptSelect.value && teacherSelect.disabled) {
    deptSelect.dispatchEvent(new Event('change'));
  }
})();
})();
