
(function () {
  var sidebar = document.getElementById('appSidebar');
  var content = document.getElementById('sidebarContent');
  var overlay = document.getElementById('sidebarOverlay');
  var KEY = 'ropely-sidebar-collapsed';

  function restore() {
    if (!sidebar || !content) return;
    var saved;
    try { saved = localStorage.getItem(KEY); } catch (e) { saved = null; }
    if (saved === '1' && window.innerWidth >= 1024) {
      sidebar.classList.add('collapsed');
      content.classList.add('sidebar-collapsed');
      document.body.classList.add('sidebar-collapsed');
    }
  }

  window.toggleSidebar = function () {
    if (!sidebar || !overlay) return;
    if (window.innerWidth < 1024) {
      sidebar.classList.toggle('open');
      overlay.classList.toggle('open');
    } else {
      var collapsed = sidebar.classList.toggle('collapsed');
      content.classList.toggle('sidebar-collapsed', collapsed);
      document.body.classList.toggle('sidebar-collapsed', collapsed);
      try { localStorage.setItem(KEY, collapsed ? '1' : '0'); } catch (e) {}
    }
  };

  window.closeSidebarMobile = function () {
    if (!sidebar || !overlay) return;
    sidebar.classList.remove('open');
    overlay.classList.remove('open');
  };

  /* Theme handling lives in static/js/theme.js, loaded in the <head> before
     this file. It exposes window.applyTheme and window.toggleTheme. */
  restore();

})();
