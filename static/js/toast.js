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

  /* Flash messages and API error strings reach here verbatim from the server.
   * Several of them interpolate database values (teacher name, course name,
   * period label) that only get .strip() on the way in, so they must not be
   * parsed as markup. `&quot;` / `&#39;` are included so this is also safe if
   * a caller ever moves the value into an attribute. */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  window.showNotification = function (message, type, duration) {
    type = type || 'info';
    duration = typeof duration === 'number' ? duration : 3000;
    var container = ensureContainer();

    var el = document.createElement('div');
    var persistent = type === 'recovery_code';
    var bg = persistent || type === 'success' ? 'bg-primary-container border-primary-fixed'
      : type === 'warning' ? 'bg-warning-faint border-warning-border'
      : type === 'error' ? 'bg-error-container border-error'
      : 'bg-surface border-primary';
    var text = persistent || type === 'success' ? 'text-on-primary-container'
      : type === 'warning' ? 'text-warning-text'
      : type === 'error' ? 'text-error'
      : 'text-on-surface';
    var icon = persistent || type === 'success' ? 'key' : (type === 'error' ? 'error' : (type === 'warning' ? 'warning' : 'info'));

    el.className = 'notification pointer-events-auto flex items-center justify-between ' + bg + ' border-l-4 p-4 rounded-lg shadow-lg';
    el.innerHTML =
      '<div class="flex items-center gap-3">' +
        '<span class="material-symbols-outlined shrink-0">' + icon + '</span>' +
        '<p class="font-body-md ' + text + '">' + esc(message) + '</p>' +
      '</div>' +
      '<button type="button" class="text-outline hover:text-on-surface transition-colors shrink-0 px-2 py-1 text-xs font-bold" aria-label="' +
        (persistent ? 'تأكيد القراءة' : 'إغلاق') + '">' +
        (persistent ? 'تأكيد القراءة' : '<span class="material-symbols-outlined text-sm">close</span>') +
      '</button>';

    container.appendChild(el);
    var closeBtn = el.querySelector('button');
    closeBtn.addEventListener('click', function () { dismiss(el); });
    requestAnimationFrame(function () { el.classList.add('show'); });
    if (duration > 0) {
      setTimeout(function () { dismiss(el); }, duration);
    }
  };
})();
