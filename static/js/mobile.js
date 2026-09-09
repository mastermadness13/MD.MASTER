/**
 * mobile.js — phone/tablet adaptation helpers.
 *  1. Auto-wraps bare <table> elements in a horizontal scroll container
 *     (also catches tables injected dynamically via AJAX).
 *  2. Notification bell: tap-to-toggle (hover doesn't exist on touch).
 *  3. Syncs sidebar drawer/collapsed state when crossing the desktop
 *     breakpoint (e.g. rotating a tablet).
 *  4. Locks background scroll while the mobile sidebar drawer is open.
 */
(function () {
  'use strict';

  if (!document.body || document.body.hasAttribute('data-skip-mobile-js')) return;

  /* ── 1. Table auto-wrap ─────────────────────────────────────── */

  var WRAP_HINT = /(overflow|scroll|wrap|container)/i;

  function hasScrollableAncestor(table) {
    var p = table.parentElement;
    while (p && p !== document.body) {
      var cls = typeof p.className === 'string' ? p.className : '';
      if (WRAP_HINT.test(cls)) return true;
      if (table.closest && table.closest('.document-page')) return true;
      var ov = window.getComputedStyle(p).overflowX;
      if (ov === 'auto' || ov === 'scroll') return true;
      p = p.parentElement;
    }
    return false;
  }

  function wrapTable(table) {
    var wrap = document.createElement('div');
    wrap.className = 'table-scroll-wrap';
    table.parentNode.insertBefore(wrap, table);
    wrap.appendChild(table);
  }

  function wrapTables(root) {
    var scope = root || document;
    var tables = scope.querySelectorAll('table');
    for (var i = 0; i < tables.length; i++) {
      var t = tables[i];
      if (t.closest('.table-scroll-wrap')) continue;
      if (hasScrollableAncestor(t)) continue;
      wrapTable(t);
    }
  }

  function scheduleWrap() {
    clearTimeout(scheduleWrap._t);
    scheduleWrap._t = setTimeout(function () { wrapTables(document); }, 150);
  }

  /* ── 2. Notification bell tap-to-toggle ────────────────────── */

  function initNotifTap() {
    var dropdown = document.querySelector('.notif-dropdown');
    var bell = dropdown ? dropdown.querySelector('.notif-bell') : null;
    if (!dropdown || !bell || bell.dataset.notifTapBound) return;
    bell.dataset.notifTapBound = '1';
    bell.addEventListener('click', function (e) {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    });
    document.addEventListener('click', function (e) {
      if (!dropdown.contains(e.target)) dropdown.classList.remove('open');
    });
  }

  /* ── 3. Sidebar breakpoint sync + scroll lock ──────────────── */

  function initSidebarSync() {
    var sidebar = document.getElementById('appSidebar');
    if (!sidebar) return;
    var overlay = document.getElementById('sidebarOverlay');
    var content = document.getElementById('sidebarContent');

    function closeDrawer() {
      sidebar.classList.remove('open');
      if (overlay) overlay.classList.remove('open');
      document.body.classList.remove('sidebar-mobile-open');
    }

    var mq = window.matchMedia('(min-width: 1024px)');
    function sync(e) {
      if (e.matches) {
        closeDrawer();
      } else {
        sidebar.classList.remove('collapsed');
        if (content) content.classList.remove('sidebar-collapsed');
        document.body.classList.remove('sidebar-collapsed');
        try { localStorage.setItem('ropely-sidebar-collapsed', '0'); } catch (err) {}
      }
    }
    if (mq.addEventListener) mq.addEventListener('change', sync);
    else if (mq.addListener) mq.addListener(sync);

    // Wrap toggleSidebar to keep body scroll lock in sync with drawer state
    var origToggle = window.toggleSidebar;
    if (typeof origToggle === 'function' && !window.__toggleSidebarWrapped) {
      window.__toggleSidebarWrapped = true;
      window.toggleSidebar = function () {
        origToggle();
        requestAnimationFrame(function () {
          document.body.classList.toggle(
            'sidebar-mobile-open',
            sidebar.classList.contains('open')
          );
        });
      };
    }

    // Close the drawer when a nav link inside it is tapped
    sidebar.addEventListener('click', function (e) {
      var link = e.target.closest ? e.target.closest('.sidebar-link') : null;
      if (link) closeDrawer();
    });
  }

  /* ── Boot ──────────────────────────────────────────────────── */

  function boot() {
    wrapTables(document);
    initNotifTap();
    initSidebarSync();

    var main = document.getElementById('mainContent');
    if (main && window.MutationObserver) {
      new MutationObserver(scheduleWrap).observe(main, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
