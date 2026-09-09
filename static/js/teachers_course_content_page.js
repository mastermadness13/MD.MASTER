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
        form.elements['action'].value = btn.dataset.action;
      }
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