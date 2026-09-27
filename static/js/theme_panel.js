/* Appearance panel controller. Persisted state and live application belong to theme.js. */
(function () {
  var panel = document.getElementById('themePanel');
  var manager = window.themeManager;
  if (!panel || !manager) return;

  var customBlock = panel.querySelector('[data-theme-custom]');
  var hueSlider = panel.querySelector('[data-theme-hue]');
  var fontFamilySelect = panel.querySelector('[data-theme-font-family]');
  var fontSizeSlider = panel.querySelector('[data-theme-font-size]');
  var liveStatus = panel.querySelector('[data-theme-live-status]');
  var colorControls = {
    pageColor: {
      setter: 'setPageColor',
      label: 'page',
      dot: 'page'
    },
    cardColor: {
      setter: 'setCardColor',
      label: 'card',
      dot: 'card'
    },
    modalColor: {
      setter: 'setModalColor',
      label: 'modal',
      dot: 'modal'
    },
    borderColor: {
      setter: 'setBorderColor',
      label: 'border',
      dot: 'border'
    },
    textColor: {
      setter: 'setTextColor',
      label: 'text',
      dot: 'text'
    },
    mutedColor: {
      setter: 'setMutedColor',
      label: null,
      dot: null
    },
    inverseTextColor: {
      setter: 'setInverseTextColor',
      label: null,
      dot: null
    },
    buttonColor: {
      setter: 'setButtonColor',
      label: 'button',
      dot: 'button'
    }
  };
  var modeLabels = {
    light: 'نهاري',
    dark: 'ليلي',
    system: 'تلقائي',
    custom: 'مخصص'
  };

  function each(selector) {
    return panel.querySelectorAll(selector);
  }

  function ensureCustomMode() {
    if (manager.mode !== 'custom') manager.setMode('custom');
  }

  function updateStatus(message) {
    if (liveStatus) liveStatus.textContent = message || 'المزامنة الحية مفعّلة';
  }

  function syncColorControl(key) {
    var config = colorControls[key];
    var color = manager.prefs[key];
    if (!config || !color) return;

    var input = panel.querySelector('[data-theme-color-input="' + key + '"]');
    if (input) input.value = color;

    if (config.label) {
      var label = panel.querySelector('[data-theme-color-value="' + config.label + '"]');
      if (label) label.textContent = color;
    }
    if (config.dot) {
      var dot = panel.querySelector('[data-theme-color-dot="' + config.dot + '"]');
      if (dot) dot.style.backgroundColor = color;
    }
    each('[data-theme-color-preset="' + key + '"]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(button.getAttribute('data-color').toLowerCase() === color));
    });
  }

  function relativeLuminance(hex) {
    var channels = [
      parseInt(hex.slice(1, 3), 16),
      parseInt(hex.slice(3, 5), 16),
      parseInt(hex.slice(5, 7), 16)
    ].map(function (channel) {
      var value = channel / 255;
      return value <= 0.04045 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  }

  function contrastRatio(first, second) {
    var firstLuminance = relativeLuminance(first);
    var secondLuminance = relativeLuminance(second);
    return (Math.max(firstLuminance, secondLuminance) + 0.05) /
      (Math.min(firstLuminance, secondLuminance) + 0.05);
  }

  function syncContrast() {
    var badge = panel.querySelector('[data-theme-contrast]');
    if (!badge) return;
    var requested = manager.prefs.textColor;
    var backgrounds = [
      manager.prefs.pageColor,
      manager.prefs.cardColor,
      manager.prefs.modalColor
    ];
    var safe = backgrounds.every(function (background) {
      return contrastRatio(requested, background) >= 4.5;
    });
    badge.textContent = safe ? 'تباين جيد AA' : 'يُطبّق لون مقروء تلقائياً';
    badge.setAttribute('data-contrast-safe', String(safe));
  }

  function syncControls() {
    var mode = manager.mode;
    var prefs = manager.prefs;

    each('input[name="theme-mode"]').forEach(function (input) {
      input.checked = input.value === mode;
    });
    each('input[name="theme-density"]').forEach(function (input) {
      input.checked = input.value === prefs.density;
    });
    each('input[name="theme-corner"]').forEach(function (input) {
      input.checked = input.value === prefs.corner;
    });
    each('input[name="theme-button-style"]').forEach(function (input) {
      input.checked = input.value === prefs.buttonStyle;
    });

    if (hueSlider) hueSlider.value = String(prefs.hue);
    each('[data-theme-hue-value]').forEach(function (output) {
      output.textContent = prefs.hue + '°';
    });
    var accentDot = panel.querySelector('[data-theme-color-dot="accent"]');
    if (accentDot) accentDot.style.backgroundColor = 'hsl(' + prefs.hue + ' 58% 42%)';
    each('[data-theme-hue-preset]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(Number(button.getAttribute('data-theme-hue-preset')) === prefs.hue));
    });

    if (fontFamilySelect) fontFamilySelect.value = prefs.fontFamily || 'Cairo';
    if (fontSizeSlider) fontSizeSlider.value = String(prefs.fontSize || 16);
    each('[data-theme-font-size-value]').forEach(function (output) {
      output.textContent = (prefs.fontSize || 16) + ' px';
    });

    Object.keys(colorControls).forEach(syncColorControl);
    syncContrast();

    each('[data-theme-mode-label]').forEach(function (label) {
      label.textContent = modeLabels[mode] || modeLabels.light;
    });
    if (customBlock) customBlock.hidden = mode !== 'custom';
  }

  each('input[name="theme-mode"]').forEach(function (input) {
    input.addEventListener('change', function () {
      if (!input.checked) return;
      manager.setMode(input.value);
      syncControls();
      updateStatus('تم تطبيق وضع ' + (modeLabels[input.value] || '') + ' فورياً');
    });
  });

  each('input[name="theme-density"]').forEach(function (input) {
    input.addEventListener('change', function () {
      if (input.checked) {
        manager.setDensity(input.value);
        updateStatus('تم تحديث كثافة العناصر');
      }
    });
  });

  each('input[name="theme-corner"]').forEach(function (input) {
    input.addEventListener('change', function () {
      if (input.checked) {
        manager.setCorner(input.value);
        updateStatus('تم تحديث استدارة الحواف');
      }
    });
  });

  each('input[name="theme-button-style"]').forEach(function (input) {
    input.addEventListener('change', function () {
      if (!input.checked) return;
      ensureCustomMode();
      manager.setButtonStyle(input.value);
      syncControls();
      updateStatus('تم تطبيق نمط الأزرار');
    });
  });

  if (hueSlider) {
    hueSlider.addEventListener('input', function () {
      manager.setHue(hueSlider.value);
      syncControls();
      updateStatus('تم تحديث لون التمييز');
    });
  }

  if (fontFamilySelect) {
    fontFamilySelect.addEventListener('change', function () {
      manager.setFontFamily(fontFamilySelect.value);
      updateStatus('تم تطبيق الخط فورياً');
    });
  }

  if (fontSizeSlider) {
    fontSizeSlider.addEventListener('input', function () {
      manager.setFontSize(fontSizeSlider.value);
      syncControls();
      updateStatus('تم تطبيق حجم الخط فورياً');
    });
  }

  each('[data-theme-hue-preset]').forEach(function (button) {
    button.addEventListener('click', function () {
      ensureCustomMode();
      manager.setHue(button.getAttribute('data-theme-hue-preset'));
      syncControls();
      updateStatus('تم تطبيق اللون الجاهز');
    });
  });

  each('[data-theme-color-preset]').forEach(function (button) {
    button.addEventListener('click', function () {
      var key = button.getAttribute('data-theme-color-preset');
      var config = colorControls[key];
      if (!config) return;
      ensureCustomMode();
      manager[config.setter](button.getAttribute('data-color'));
      syncControls();
      updateStatus('تم تطبيق اللون وحفظه');
    });
  });

  each('[data-theme-color-input]').forEach(function (input) {
    input.addEventListener('input', function () {
      var key = input.getAttribute('data-theme-color-input');
      var config = colorControls[key];
      if (!config) return;
      ensureCustomMode();
      manager[config.setter](input.value);
      syncControls();
      updateStatus('تم تطبيق اللون وحفظه');
    });
  });

  each('[data-theme-accordion]').forEach(function (details) {
    details.addEventListener('toggle', function () {
      if (!details.open) return;
      each('[data-theme-accordion]').forEach(function (other) {
        if (other !== details) other.open = false;
      });
    });
  });

  var resetBtn = panel.querySelector('[data-theme-reset]');
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      manager.setMode('light');
      manager.setHue(280);
      manager.setDensity('comfortable');
      manager.setCorner('soft');
      manager.setFontFamily('Cairo');
      manager.setFontSize(16);
      manager.setPageColor('#f7f9ff');
      manager.setCardColor('#ffffff');
      manager.setModalColor('#ffffff');
      manager.setBorderColor('#d1d5db');
      manager.setTextColor('#181c20');
      manager.setMutedColor('#4c4452');
      manager.setInverseTextColor('#ffffff');
      manager.setButtonColor('#7c3aed');
      manager.setButtonStyle('filled');
      panel.querySelectorAll('[data-theme-accordion]').forEach(function (details) {
        details.open = false;
      });
      syncControls();
      updateStatus('تمت استعادة إعدادات المظهر الافتراضية');
    });
  }

  var applyBtn = panel.querySelector('[data-theme-apply]');
  if (applyBtn) {
    applyBtn.addEventListener('click', function () {
      updateStatus('الإعدادات مطبّقة ومحفوظة');
      panel.hidePopover();
    });
  }

  panel.addEventListener('toggle', function (event) {
    if (event.newState === 'open') {
      syncControls();
      var checked = panel.querySelector('input[name="theme-mode"]:checked');
      if (checked) checked.focus();
    }
  });

  panel.addEventListener('click', function (event) {
    if (event.target.closest('[data-theme-panel-close]')) panel.hidePopover();
  });

  syncControls();
})();
