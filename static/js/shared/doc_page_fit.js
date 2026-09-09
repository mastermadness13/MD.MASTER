/**
 * Scales a .document-page element to fit the viewport width on narrow screens.
 * Used by faculty performance print and leaves report pages.
 */
(function () {
  'use strict';
  function fitDocPage() {
    var page = document.querySelector('.document-page');
    if (!page) return;
    if (window.innerWidth > 860) { page.style.transform = ''; page.style.marginBottom = ''; return; }
    var vw = document.documentElement.clientWidth - 20;
    page.style.transform = 'none';
    var w = page.offsetWidth || 794;
    var scale = Math.min(1, vw / w);
    page.style.transform = 'scale(' + scale + ')';
    page.style.marginBottom = ((scale - 1) * page.offsetHeight) + 'px';
  }
  window.addEventListener('resize', fitDocPage);
  window.addEventListener('load', fitDocPage);
  document.addEventListener('DOMContentLoaded', fitDocPage);
  fitDocPage();
})();
