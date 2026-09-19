/**
 * Action menu (dropdown) for table actions.
 * Usage:
 *   <button class="action-menu-btn" onclick="toggleActionMenu(this)">more_vert</button>
 *   <div class="action-menu hidden ..."> ... items ... </div>
 */
(function () {
  'use strict';

  function menuOf(btn) {
    return btn ? btn.nextElementSibling : null;
  }

  function setOpen(btn, open) {
    var menu = menuOf(btn);
    if (!menu) return;
    if (open) {
      menu.classList.remove('hidden');
      btn.setAttribute('aria-expanded', 'true');
    } else {
      menu.classList.add('hidden');
      btn.setAttribute('aria-expanded', 'false');
    }
  }

  function closeAll() {
    document.querySelectorAll('.action-menu:not(.hidden)').forEach(function (menu) {
      menu.classList.add('hidden');
      var btn = menu.previousElementSibling;
      if (btn && btn.setAttribute) btn.setAttribute('aria-expanded', 'false');
    });
  }

  window.toggleActionMenu = function (btn) {
    var wasOpen = menuOf(btn) && !menuOf(btn).classList.contains('hidden');
    closeAll();
    if (!wasOpen) setOpen(btn, true);
  };

  document.addEventListener('click', function (e) {
    if (!e.target.closest('.action-menu-btn')) {
      closeAll();
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAll();
  });

})();