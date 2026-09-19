/**
 * bottom_nav.js — mobile app bottom navigation (see bottom_nav.html).
 *
 *  - FAB / "more" button open the bottom sheet dialog, one section at a time.
 *  - Backdrop tap, Escape, or picking a row closes it; body scroll locks.
 *  - The bar hides while scrolling down and reappears on scroll up
 *    (TikTok-style breathing room) once the user is past the top.
 *
 * Desktop (>=1024px) never renders the bar, so nothing happens there.
 */
(function () {
  'use strict';

  var nav = document.getElementById('bottomNav');
  if (!nav || document.body.hasAttribute('data-skip-mobile-js')) return;

  var dialog = document.getElementById('bnSheetDialog');
  if (!dialog) return;

  var sectionCache = {};
  function section(name) {
    if (!sectionCache[name]) {
      sectionCache[name] = dialog.querySelector('[data-bn-section="' + name + '"]');
    }
    return sectionCache[name];
  }

  function openSheet(name) {
    ['quick', 'more'].forEach(function (n) {
      var s = section(n);
      if (s) s.hidden = n !== (name || 'quick');
    });
    dialog.hidden = false;
    requestAnimationFrame(function () {
      dialog.classList.add('show');
      document.body.classList.add('sheet-open');
    });
  }

  function closeSheet() {
    if (!dialog.classList.contains('show')) return;
    dialog.classList.remove('show');
    document.body.classList.remove('sheet-open');
    setTimeout(function () { dialog.hidden = true; }, 260);
  }

  window.toggleBnSheet = function (name) {
    if (dialog.classList.contains('show')) closeSheet();
    else openSheet(name || 'quick');
  };
  window.closeBnSheet = closeSheet;

  dialog.addEventListener('click', function (e) {
    if (e.target.closest('[data-bn-close]')) { closeSheet(); return; }
    /* tap on the obscured backdrop (not the sheet) */
    if (!e.target.closest('.bn-sheet')) closeSheet();
  });
  /* picking any row navigates/acts — dismiss the sheet right after */
  dialog.addEventListener('click', function (e) {
    if (e.target.closest('.bn-item-row')) setTimeout(closeSheet, 120);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeSheet();
  });

  /* Hide on scroll down, reveal on scroll up */
  var lastY = window.pageYOffset || 0;
  window.addEventListener('scroll', function () {
    var y = window.pageYOffset || 0;
    if (Math.abs(y - lastY) < 14) return;
    document.body.classList.toggle('bn-hidden', y > lastY && y > 140);
    lastY = y;
  }, { passive: true });
})();