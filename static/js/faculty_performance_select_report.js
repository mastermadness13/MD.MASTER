
(function () {
  var BOOT = window.FACULTY_SELECT_REPORT_BOOT || {};
  var URLS = BOOT.urls || {};
  var typeRadios = document.querySelectorAll('input[name="report_type"]');
  var yearSel = document.getElementById('year-select');
  var semSel = document.getElementById('semester-select');
  var deptSel = document.getElementById('dept-select');
  var courseBlock = document.getElementById('course-block');
  var teacherBlock = document.getElementById('teacher-block');
  var courseSel = document.getElementById('course-select');
  var teacherSel = document.getElementById('teacher-select');

  /* Course/teacher names and codes come from the /api/courses and /api/teachers
   * endpoints, which accept arbitrary text. Escape before building <option>. */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function currentType() {
    return document.querySelector('input[name="report_type"]:checked').value;
  }

  function refreshType() {
    var t = currentType();
    courseBlock.classList.toggle('hidden', t !== 'course');
    teacherBlock.classList.toggle('hidden', t !== 'teacher');
  }
  typeRadios.forEach(function (r) { r.addEventListener('change', refreshType); });

  deptSel.addEventListener('change', function () {
    var deptId = this.value;
    if (!deptId) {
      courseSel.innerHTML = '<option value="">— اختر القسم أولاً —</option>';
      teacherSel.innerHTML = '<option value="">— اختر القسم أولاً —</option>';
      return;
    }

    fetch(URLS.coursesApi + '?department_id=' + deptId)
      .then(r => r.json())
      .then(data => {
        if (!data.length) {
          courseSel.innerHTML = '<option value="">— لا توجد مقررات في هذا القسم —</option>';
        } else {
          let html = '<option value="">— اختر المقرر —</option>';
          data.forEach(c => {
            html += '<option value="' + c.id + '">' + esc(c.name) +
                    (c.code ? ' (' + esc(c.code) + ')' : '') + '</option>';
          });
          courseSel.innerHTML = html;
        }
      })
      .catch(() => { courseSel.innerHTML = '<option value="">— خطأ في التحميل —</option>'; });

    fetch(URLS.teachersApi + '?department_id=' + deptId)
      .then(r => r.json())
      .then(data => {
        if (!data.length) {
          teacherSel.innerHTML = '<option value="">— لا يوجد أساتذة في هذا القسم —</option>';
        } else {
          let html = '<option value="">— اختر عضو هيئة التدريس —</option>';
          data.forEach(t => {
            html += '<option value="' + t.id + '">' + esc(t.name) + '</option>';
          });
          teacherSel.innerHTML = html;
        }
      })
      .catch(() => { teacherSel.innerHTML = '<option value="">— خطأ في التحميل —</option>'; });
  });

  document.getElementById('report-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var year = yearSel.value;
    var semester = semSel.value;
    var dept = deptSel.value;
    var t = currentType();

    if (!year || !dept) { alert('يرجى اختيار العام الجامعي والقسم'); return; }

    if (t === 'course') {
      if (!courseSel.value) { alert('يرجى اختيار المقرر'); return; }
      window.location.href = URLS.courseReport.replace('/0', '/' + courseSel.value) +
        '?year=' + encodeURIComponent(year) +
        '&semester=' + encodeURIComponent(semester) +
        '&dept=' + encodeURIComponent(dept);
    } else {
      if (!teacherSel.value) { alert('يرجى اختيار عضو هيئة التدريس'); return; }
      window.location.href = URLS.preview.replace('/0', '/' + teacherSel.value) +
        '?year=' + encodeURIComponent(year) +
        '&semester=' + encodeURIComponent(semester) +
        '&dept=' + encodeURIComponent(dept);
    }
  });

  refreshType();
})();
