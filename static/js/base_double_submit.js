
  /* Prevent duplicate form submissions caused by double-clicking submit */
  (function () {
    document.addEventListener('submit', function (e) {
      if (e.defaultPrevented) return;
      var form = e.target;
      if (form.getAttribute('data-no-double-guard') !== null) return;
      var btn = form.querySelector('button[type="submit"]');
      if (!btn) return;
      if (btn.getAttribute('data-submitting') === '1') {
        e.preventDefault();
        return;
      }
      btn.setAttribute('data-submitting', '1');
      btn.style.opacity = '0.6';
      setTimeout(function () {
        btn.removeAttribute('data-submitting');
        btn.style.opacity = '';
      }, 4000);
    });
  })();
