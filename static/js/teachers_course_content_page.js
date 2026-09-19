(function () {
  var BOOT = window.TEACHERS_COURSE_CONTENT_PAGE_BOOT || {};
  var URLS = BOOT.urls || {};

  if (BOOT.auto_print && window.self === window.top) {
    window.addEventListener('load', function () {
      window.setTimeout(function () {
        window.print();
      }, 300);
    });
  }

  var form = document.getElementById('courseContentForm');
  if (form) {
    form.addEventListener('submit', function (e) {
      var btn = e.submitter;
      if (btn && btn.dataset.action) {
        if (btn.dataset.action === 'send') {
          var ok = window.confirm('سيتم نشر المقرر وإظهاره في الجدول الدراسي مباشرة. متابعة؟');
          if (!ok) {
            e.preventDefault();
            return;
          }
        }
        form.elements['action'].value = btn.dataset.action;
      }
    });
  }

  var fileInput = document.getElementById('formFileInput');
  if (fileInput) {
    fileInput.addEventListener('change', function () {
      var f = fileInput.files && fileInput.files[0];
      if (!f) return;
      var isPdf = (f.type && f.type === 'application/pdf') || /\.pdf$/i.test(f.name);
      if (!isPdf) {
        if (window.showNotification) window.showNotification('يجب أن يكون الملف بصيغة PDF', 'error');
        fileInput.value = '';
        return;
      }
      if (f.size > 10 * 1024 * 1024) {
        if (window.showNotification) window.showNotification('حجم الملف يتجاوز 10 ميغابايت', 'error');
        fileInput.value = '';
        return;
      }
      if (window.showNotification) window.showNotification('تم اختيار الملف: ' + f.name, 'info', 3000);
    });
  }

  var courseSelect = document.getElementById('ccCourseSelect');
  if (courseSelect) {
    courseSelect.addEventListener('change', function () {
      var val = courseSelect.value;
      if (val) {
        window.location.href = URLS.create + '?course_id=' + val;
      }
    });
  }
})();