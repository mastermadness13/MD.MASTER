(function () {
  var input = document.getElementById('iconInput');
  var wrap = document.getElementById('iconPicker');
  var preview = document.getElementById('iconPreview');
  if (!input || !wrap) return;
  function refreshPreview(v) {
    if (preview) preview.textContent = v || '📖';
  }
  var picker = window.CourseIconPicker.create(wrap, {
    value: input.value || '📖',
    preview: false,
    onChange: function (v) { input.value = v; refreshPreview(v); }
  });
  input.addEventListener('input', function () {
    var v = input.value || '📖';
    refreshPreview(v);
    picker.setValue(v);
  });
  refreshPreview(input.value);
})();
