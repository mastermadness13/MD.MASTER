document.addEventListener('DOMContentLoaded', function () {
  var sel = document.getElementById('perf-teacher-select');
  if (!sel) return;
  sel.addEventListener('change', function () {
    var opt = this.options[this.selectedIndex];
    if (opt && opt.dataset.url) {
      window.location.href = opt.dataset.url;
    }
  });
});
