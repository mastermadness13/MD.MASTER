/* Shared toast notifications (used by both the app shell and the public portal). */
(function () {
  function ensureContainer() {
    var c = document.getElementById('notification-container');
    if (!c) {
      c = document.createElement('div');
      c.id = 'notification-container';
      c.className = 'fixed top-4 left-1/2 -translate-x-1/2 z-[100] flex flex-col gap-2 w-full max-w-md px-4 pointer-events-none';
      document.body.appendChild(c);
    }
    return c;
  }

  function dismiss(el) {
    el.classList.remove('show');
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 500);
  }

  window.showNotification = function (message, type, duration) {
    type = type || 'info';
    duration = typeof duration === 'number' ? duration : 3000;
    var container = ensureContainer();

    var el = document.createElement('div');
    var bg = type === 'success' ? 'bg-primary-container border-primary-fixed' : 'bg-surface border-primary';
    var text = type === 'success' ? 'text-on-primary-container' : 'text-on-surface';
    var icon = type === 'success' ? 'waving_hand' : (type === 'error' ? 'error' : 'info');

    el.className = 'notification pointer-events-auto flex items-center justify-between ' + bg + ' border-l-4 p-4 rounded-lg shadow-lg';
    el.innerHTML =
      '<div class="flex items-center gap-3">' +
        '<span class="material-symbols-outlined shrink-0">' + icon + '</span>' +
        '<p class="font-body-md ' + text + '">' + message + '</p>' +
      '</div>' +
      '<button type="button" class="text-outline hover:text-on-surface transition-colors shrink-0" aria-label="إغلاق">' +
        '<span class="material-symbols-outlined text-sm">close</span>' +
      '</button>';

    container.appendChild(el);
    var closeBtn = el.querySelector('button');
    closeBtn.addEventListener('click', function () { dismiss(el); });
    requestAnimationFrame(function () { el.classList.add('show'); });
    setTimeout(function () { dismiss(el); }, duration);
  };
})();
