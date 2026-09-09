
(function () {
  var BOOT = window.TEACHERS_UPLOAD_BOOT || {};
  var MAX_BYTES = BOOT.maxUploadMb * 1024 * 1024;
  var form = document.querySelector('form[action*="teacher_upload"]');
  var input = form ? form.querySelector('input[name="file"]') : null;
  var errEl = document.getElementById('upload-size-error');
  if (!form || !input || !errEl) return;
  form.addEventListener('submit', function (e) {
    var file = input.files && input.files[0];
    if (file && file.size > MAX_BYTES) {
      e.preventDefault();
      errEl.classList.remove('hidden');
      input.focus();
    }
  });
  input.addEventListener('change', function () { errEl.classList.add('hidden'); });
})();
