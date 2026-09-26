(function () {
  'use strict';

  function fitPerformanceForm() {
    var page = document.querySelector('.document-page');
    var form = page && page.querySelector('.performance-print-fit');
    if (!page || !form) return;

    form.style.transform = 'none';
    form.style.width = '100%';
    var scale = Math.min(1, page.clientHeight / form.scrollHeight);
    form.style.width = (100 / scale) + '%';
    form.style.transformOrigin = 'top right';
    form.style.transform = 'scale(' + scale + ')';
    page.style.height = (form.scrollHeight * scale) + 'px';
  }

  window.addEventListener('beforeprint', fitPerformanceForm);
  window.addEventListener('afterprint', function () {
    var page = document.querySelector('.document-page');
    var form = page && page.querySelector('.performance-print-fit');
    if (!page || !form) return;
    form.style.transform = '';
    form.style.transformOrigin = '';
    form.style.width = '';
    page.style.height = '';
  });
})();
