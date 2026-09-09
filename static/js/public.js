// Unified public portal interactions
(function () {
  function togglePublicNav() {
    var nav = document.getElementById('publicMobileNav');
    if (nav) nav.classList.toggle('open');
  }
  window.togglePublicNav = togglePublicNav;

  // One-time info toast for guests (once per browser session)
  document.addEventListener('DOMContentLoaded', function () {
    var isGuest = document.body.getAttribute('data-guest') === '1';
    if (!isGuest) return;
    try {
      if (sessionStorage.getItem('ropely-public-greeting')) return;
      sessionStorage.setItem('ropely-public-greeting', '1');
      setTimeout(function () {
        window.showNotification('مرحباً بك في المنصة الرقمية للكلية', 'info', 3000);
      }, 400);
    } catch (e) { /* sessionStorage unavailable — skip greeting */ }
  });
})();
