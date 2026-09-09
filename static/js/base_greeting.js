var BOOT = window.BASE_GREETING_BOOT || {};
  var NAME = BOOT.name || '';

  document.addEventListener('DOMContentLoaded', function () {
    window.showNotification('مرحباً بعودتك 👋 ' + NAME, 'success', 5000);
  });
