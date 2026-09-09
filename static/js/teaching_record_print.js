document.addEventListener('DOMContentLoaded', function () {
  var BOOT = window.TEACHING_RECORD_PRINT_BOOT || {};
  if (BOOT.printFlag) {
    setTimeout(function () { window.print(); }, 250);
  }
});
