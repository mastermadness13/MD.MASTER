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
  var courseContentSubmitPending = false;
  if (form) {
    function courseContentWeeksBlocked() {
      var output = document.getElementById('ccTheoreticalWeeksTotal');
      var total = parseInt(output ? output.textContent : '0', 10) || 0;
      if (total <= 12) return false;
      var message = 'إجمالي الأسابيع النظرية (' + total + ') يتجاوز الحد المسموح (12) — لا يمكن الحفظ أو النشر.';
      if (window.showNotification) window.showNotification(message, 'error', 6000);
      else window.alert(message);
      return true;
    }

    function submitCourseContentForm() {
      if (courseContentSubmitPending || courseContentWeeksBlocked()) return;
      courseContentSubmitPending = true;
      var submit = function () {
        courseContentSubmitPending = false;
        form.submit();
      };
      if (typeof window.flushCourseContentTranslations === 'function') {
        Promise.resolve(window.flushCourseContentTranslations()).then(submit, submit);
      } else {
        submit();
      }
    }

    form.addEventListener('submit', function (e) {
      var btn = e.submitter;
      if (btn && btn.dataset.action) {
        if (courseContentWeeksBlocked()) return;
        e.preventDefault();
        form.elements['action'].value = btn.dataset.action;
        if (btn.dataset.action === 'send') {
          window.askConfirm({
            message: 'سيتم حفظ مفردات المقرر ونشرها في الجدول الدراسي مباشرة. متابعة؟',
            onConfirm: submitCourseContentForm
          });
        } else {
          submitCourseContentForm();
        }
      }
    });
  }

  var replaceForm = document.getElementById('courseContentReplaceForm');
  if (replaceForm) {
    replaceForm.addEventListener('submit', function (e) {
      var fileInput = replaceForm.elements['file'];
      if (!fileInput || !fileInput.files || !fileInput.files.length) {
        e.preventDefault();
        window.alert('يرجى اختيار ملف PDF أولاً');
        return;
      }
      if (replaceForm.getAttribute('data-confirm-replace') !== '1') return;
      e.preventDefault();
      window.askConfirm({
        message: 'يوجد ملف حالي لهذا النموذج وسيُستبدل بالنسخة الجديدة. متابعة الاستبدال؟',
        onConfirm: function () { replaceForm.submit(); }
      });
    });
  }

  var courseSelect = document.getElementById('ccCourseSelect');
  if (courseSelect) {
    courseSelect.addEventListener('change', function () {
      var val = courseSelect.value;
      if (val) {
        window.location.href = URLS.create + '&course_id=' + val;
      }
    });
  }
})();