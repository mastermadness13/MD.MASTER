var BOOT = window.BASE_GREETING_BOOT || {};
  var NAME = BOOT.name || '';

  document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('firstLoginBanner')) return;
    window.showNotification('مرحباً بعودتك 👋 ' + NAME, 'success', 5000);
  });
