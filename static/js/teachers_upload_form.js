(function () {
  function bindSizeCheck(form) {
    var input = form.querySelector('input[name="file"]');
    var errEl = document.getElementById('upload-size-error');
    if (!input || !errEl) return;
    var maxMb = parseFloat(form.getAttribute('data-upload-limit')) || 16;
    var maxBytes = maxMb * 1024 * 1024;
    form.addEventListener('submit', function (e) {
      var f = input.files && input.files[0];
      if (f && f.size > maxBytes) {
        e.preventDefault();
        errEl.classList.remove('hidden');
        input.focus();
      }
    });
    input.addEventListener('change', function () { errEl.classList.add('hidden'); });
  }

  var forms = document.querySelectorAll('form[data-upload-limit]');
  for (var i = 0; i < forms.length; i++) bindSizeCheck(forms[i]);

  var toggle = document.getElementById('uploadToggle');
  var body = document.getElementById('uploadBody');
  var chevron = document.getElementById('uploadChevron');
  if (toggle && body && chevron) {
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
  }
})();