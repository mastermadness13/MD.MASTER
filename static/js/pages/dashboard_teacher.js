  (function () {
    var el = document.getElementById('todayDateChip');
    if (!el) return;
    try {
      el.textContent = new Intl.DateTimeFormat('ar', {
        weekday: 'long', day: 'numeric', month: 'long'
      }).format(new Date());
    } catch (e) {
      el.textContent = '';
    }
  })();
