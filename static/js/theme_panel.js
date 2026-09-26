/* Appearance panel controller.
   Keeps the native controls in shared/components/theme_panel.html in sync
   with window.themeManager (static/js/theme.js). All persistence lives in
   theme.js, so this file only reads state on open and forwards changes. */

(function () {
  var panel = document.getElementById('themePanel');
  var manager = window.themeManager;
  if (!panel || !manager) return;

  var customBlock = panel.querySelector('[data-theme-custom]');
  var hueSlider = panel.querySelector('[data-theme-hue]');
  var hueValue = panel.querySelector('[data-theme-hue-value]');
  var swatches = panel.querySelectorAll('[data-theme-hue-preset]');
  var resetBtn = panel.querySelector('[data-theme-reset]');

  function each(selector) {
    return panel.querySelectorAll('input[name="' + selector + '"]');
  }

  function syncControls() {
    var mode = manager.mode;
    var prefs = manager.prefs;

    each('theme-mode').forEach(function (input) {
      input.checked = input.value === mode;
    });
    each('theme-density').forEach(function (input) {
      input.checked = input.value === prefs.density;
    });
    each('theme-corner').forEach(function (input) {
      input.checked = input.value === prefs.corner;
    });

    if (hueSlider) {
      hueSlider.value = String(prefs.hue);
      if (hueValue) hueValue.value = prefs.hue + '°';
    }

    /* Density and corner controls live inside the custom block, so they are
       only reachable in custom mode. */
    if (customBlock) customBlock.hidden = mode !== 'custom';
  }

  each('theme-mode').forEach(function (input) {
    input.addEventListener('change', function () {
      if (input.checked) manager.setMode(input.value);
    });
  });

  each('theme-density').forEach(function (input) {
    input.addEventListener('change', function () {
      if (input.checked) manager.setDensity(input.value);
    });
  });

  each('theme-corner').forEach(function (input) {
    input.addEventListener('change', function () {
      if (input.checked) manager.setCorner(input.value);
    });
  });

  if (hueSlider) {
    /* "input" fires continuously while dragging, so the page previews live. */
    hueSlider.addEventListener('input', function () {
      manager.setHue(hueSlider.value);
      if (hueValue) hueValue.value = hueSlider.value + '°';
    });
  }

  swatches.forEach(function (swatch) {
    swatch.addEventListener('click', function () {
      var hue = swatch.getAttribute('data-theme-hue-preset');
      manager.setHue(hue);
      syncControls();
    });
  });

  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      manager.setHue(280);
      manager.setDensity('comfortable');
      manager.setCorner('soft');
      manager.setMode('light');
      syncControls();
    });
  }

  panel.addEventListener('toggle', function (event) {
    /* The "toggle" event on a popover fires for both open and close. */
    if (event.newState === 'open') {
      syncControls();
      var checked = panel.querySelector('input[name="theme-mode"]:checked');
      if (checked) checked.focus();
    }
  });

  panel.addEventListener('click', function (event) {
    if (event.target.closest('[data-theme-panel-close]')) {
      panel.hidePopover();
    }
  });

  syncControls();
})();
