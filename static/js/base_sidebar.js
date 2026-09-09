
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

  window.applyTheme = function () {
    var doc = document.documentElement;
    var saved = null;
    try { saved = localStorage.getItem('ropely-theme'); } catch (e) { saved = null; }
    var dark = saved === 'dark';
    doc.setAttribute('data-theme', dark ? 'dark' : 'light');
    var icon = document.getElementById('sidebarThemeIcon');
    var label = document.getElementById('sidebarThemeLabel');
    if (icon) icon.textContent = dark ? 'light_mode' : 'dark_mode';
    if (label) label.textContent = dark ? 'الوضع النهاري' : 'الوضع الليلي';
    var topIcon = document.getElementById('themeToggleIconTopbar');
    if (topIcon) topIcon.textContent = dark ? 'light_mode' : 'dark_mode';
  };

  window.toggleTheme = function () {
    var doc = document.documentElement;
    var dark = doc.getAttribute('data-theme') === 'dark';
    var next = dark ? 'light' : 'dark';
    try { localStorage.setItem('ropely-theme', next); } catch (e) {}
    window.applyTheme();
  };

  restore();
  window.applyTheme();

  /* ── Sidebar "More" collapsible group ── */
  var moreKey = 'ropely-sidebar-more';
  var moreGroup = document.getElementById('sidebarMoreGroup');
  var moreIcon = document.getElementById('sidebarMoreIcon');
  var moreDivider = document.getElementById('sidebarMoreDivider');

  function restoreMore() {
    if (!moreGroup) return;
    var saved;
    try { saved = localStorage.getItem(moreKey); } catch (e) { saved = null; }
    if (saved === '1') {
      moreGroup.classList.remove('collapsed');
      if (moreIcon) moreIcon.textContent = 'expand_less';
      if (moreDivider) moreDivider.setAttribute('aria-expanded', 'true');
    }
  }

  window.toggleSidebarMore = function () {
    if (!moreGroup) return;
    var collapsed = moreGroup.classList.toggle('collapsed');
    if (moreIcon) moreIcon.textContent = collapsed ? 'expand_more' : 'expand_less';
    if (moreDivider) moreDivider.setAttribute('aria-expanded', String(!collapsed));
    try { localStorage.setItem(moreKey, collapsed ? '0' : '1'); } catch (e) {}
  };

  restoreMore();
})();

/* ── Sidebar "Archives" collapsible group ── */
(function () {
  var archKey = 'ropely-sidebar-archives';
  var archGroup = document.getElementById('sidebarArchivesGroup');
  var archIcon = document.getElementById('sidebarArchivesIcon');
  var archDivider = document.getElementById('sidebarArchivesDivider');

  function restoreArchives() {
    if (!archGroup) return;
    var saved;
    try { saved = localStorage.getItem(archKey); } catch (e) { saved = null; }
    if (saved === '1') {
      archGroup.classList.remove('collapsed');
      if (archIcon) archIcon.textContent = 'expand_less';
      if (archDivider) archDivider.setAttribute('aria-expanded', 'true');
    }
  }

  window.toggleSidebarArchives = function () {
    if (!archGroup) return;
    var collapsed = archGroup.classList.toggle('collapsed');
    if (archIcon) archIcon.textContent = collapsed ? 'expand_more' : 'expand_less';
    if (archDivider) archDivider.setAttribute('aria-expanded', String(!collapsed));
    try { localStorage.setItem(archKey, collapsed ? '0' : '1'); } catch (e) {}
  };

  restoreArchives();
})();
