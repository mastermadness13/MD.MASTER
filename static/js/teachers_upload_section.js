
(function () {
  var BOOT = window.TEACHERS_UPLOAD_SECTION_BOOT || {};
  var toggle = document.getElementById('uploadToggle');
  var body = document.getElementById('uploadBody');
  var chevron = document.getElementById('uploadChevron');
  var KEY = 'ropely-teacher-upload-collapsed';
  function setCollapsed(collapsed) {
    body.style.display = collapsed ? 'none' : '';
    chevron.textContent = collapsed ? 'expand_more' : 'expand_less';
  }
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  setCollapsed(saved === '1');
  toggle.addEventListener('click', function () {
    var collapsed = body.style.display === 'none';
    setCollapsed(!collapsed);
    try { localStorage.setItem(KEY, collapsed ? '0' : '1'); } catch (e) {}
  });

  var MAX_BYTES = BOOT.maxUploadMb * 1024 * 1024;
  var form = document.getElementById('tt-upload-form');
  var input = form.querySelector('input[name="file"]');
  var errEl = document.getElementById('upload-size-error');
  form.addEventListener('submit', function (e) {
    var f = input.files && input.files[0];
    if (f && f.size > MAX_BYTES) {
      e.preventDefault();
      errEl.classList.remove('hidden');
      input.focus();
    }
  });
  input.addEventListener('change', function () { errEl.classList.add('hidden'); });
})();
