/* Theme manager — single source of truth for colour mode, density and corner
   style. Replaces the light/dark-only logic that used to live in
   base_sidebar.js, and keeps the same global names (applyTheme, toggleTheme)
   so existing onclick handlers in templates keep working.

   Modes: light | dark | system | custom
   "system" tracks prefers-color-scheme live, including OS-level changes.
   "custom" lets the user pick an accent hue; density and corner style are
   orthogonal and apply in every mode. */

(function () {
  var MODE_KEY = 'ropely-theme';
  var PREF_KEY = 'ropely-theme-prefs';
  var MODES = ['light', 'dark', 'system', 'custom'];
  var DENSITIES = ['comfortable', 'compact'];
  var CORNERS = ['soft', 'sharp', 'round'];
  var FONT_FAMILIES = {
    'Cairo': '"Cairo", sans-serif',
    'Tajawal': '"Tajawal", sans-serif',
    'Almarai': '"Almarai", sans-serif',
    'IBM Plex Sans Arabic': '"IBM Plex Sans Arabic", sans-serif',
    'Noto Kufi Arabic': '"Noto Kufi Arabic", sans-serif'
  };
  var DEFAULT_FONT_FAMILY = 'Cairo';
  var DEFAULT_FONT_SIZE = 16;
  var DEFAULT_COLORS = {
    page: '#f7f9ff',
    card: '#ffffff',
    text: '#181c20',
    muted: '#4c4452',
    button: '#7c3aed'
  };
  var BUTTON_STYLES = ['filled', 'subtle', 'outline'];

  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function readJSON(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      if (!raw) return fallback;
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : fallback;
    } catch (e) {
      return fallback;
    }
  }

  function writeJSON(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  function readMode() {
    var saved;
    try { saved = localStorage.getItem(MODE_KEY); } catch (e) { saved = null; }
    return MODES.indexOf(saved) === -1 ? 'light' : saved;
  }

  function normalizeHexColor(value) {
    return typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value.toLowerCase() : null;
  }

  var prefs = readJSON(PREF_KEY, {});
  var mode = readMode();
  if (DENSITIES.indexOf(prefs.density) === -1) prefs.density = 'comfortable';
  if (CORNERS.indexOf(prefs.corner) === -1) prefs.corner = 'soft';
  var hue = typeof prefs.hue === 'number' && isFinite(prefs.hue)
    ? Math.max(0, Math.min(359, Math.round(prefs.hue)))
    : 280;
  prefs.hue = hue;

  function normalizeFontFamily(value) {
    if (typeof value !== 'string') return null;
    var normalized = value.trim().toLowerCase().replace(/[-_]+/g, ' ').replace(/\s+/g, ' ');
    var families = Object.keys(FONT_FAMILIES);
    for (var i = 0; i < families.length; i++) {
      if (families[i].toLowerCase() === normalized ||
          FONT_FAMILIES[families[i]].toLowerCase() === value.trim().toLowerCase()) return families[i];
    }
    return null;
  }

  function normalizeFontSize(value) {
    if (typeof value !== 'number' && typeof value !== 'string') return null;
    if (typeof value === 'string' && !/^(?:\d{1,2})(?:\.0|\.5)?$/.test(value.trim())) return null;
    if (typeof value === 'string') value = Number(value.trim());
    if (!isFinite(value) || value < 12 || value > 22) return null;
    return Math.abs(value * 2 - Math.round(value * 2)) < 0.000001 ? value : null;
  }

  prefs.fontFamily = normalizeFontFamily(prefs.fontFamily) || DEFAULT_FONT_FAMILY;
  prefs.fontSize = normalizeFontSize(prefs.fontSize);
  if (prefs.fontSize === null) prefs.fontSize = DEFAULT_FONT_SIZE;
  var darkCustomBase = mode === 'custom' && prefs.base === 'dark';
  prefs.pageColor = normalizeHexColor(prefs.pageColor) || (darkCustomBase ? '#14101c' : DEFAULT_COLORS.page);
  prefs.cardColor = normalizeHexColor(prefs.cardColor) || (darkCustomBase ? '#241e31' : DEFAULT_COLORS.card);
  prefs.textColor = normalizeHexColor(prefs.textColor) || (darkCustomBase ? '#ece6f4' : DEFAULT_COLORS.text);
  prefs.mutedColor = normalizeHexColor(prefs.mutedColor) || (darkCustomBase ? '#c9c0d9' : DEFAULT_COLORS.muted);
  prefs.modalColor = normalizeHexColor(prefs.modalColor) || prefs.cardColor;
  prefs.borderColor = normalizeHexColor(prefs.borderColor) || (darkCustomBase ? '#475569' : '#d1d5db');
  prefs.inverseTextColor = normalizeHexColor(prefs.inverseTextColor) ||
    readableColor('#ffffff', [prefs.textColor]);
  prefs.buttonColor = normalizeHexColor(prefs.buttonColor) || DEFAULT_COLORS.button;
  if (BUTTON_STYLES.indexOf(prefs.buttonStyle) === -1) prefs.buttonStyle = 'filled';

  function systemPrefersDark() {
    return !!(media && media.matches);
  }

  function resolveDark() {
    if (mode === 'dark') return true;
    if (mode === 'light') return false;
    if (mode === 'system') return systemPrefersDark();
    /* Custom mode keeps the resolved light/dark base selected by the user. */
    return prefs.base === 'dark';
  }

  function relativeLuminance(rgb) {
    function linearize(channel) {
      channel /= 255;
      return channel <= 0.04045 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4);
    }
    return 0.2126 * linearize(rgb[0]) + 0.7152 * linearize(rgb[1]) + 0.0722 * linearize(rgb[2]);
  }

  function hexRgb(hex) {
    return [
      parseInt(hex.slice(1, 3), 16),
      parseInt(hex.slice(3, 5), 16),
      parseInt(hex.slice(5, 7), 16)
    ];
  }

  function contrastRatio(first, second) {
    var firstLuminance = relativeLuminance(hexRgb(first));
    var secondLuminance = relativeLuminance(hexRgb(second));
    var brightest = Math.max(firstLuminance, secondLuminance);
    var darkest = Math.min(firstLuminance, secondLuminance);
    return (brightest + 0.05) / (darkest + 0.05);
  }

  function readableColor(candidate, backgrounds) {
    var valid = backgrounds.every(function (background) {
      return contrastRatio(candidate, background) >= 4.5;
    });
    if (valid) return candidate;

    var blackScore = Math.min.apply(null, backgrounds.map(function (background) {
      return contrastRatio('#000000', background);
    }));
    var whiteScore = Math.min.apply(null, backgrounds.map(function (background) {
      return contrastRatio('#ffffff', background);
    }));
    return blackScore >= whiteScore ? '#000000' : '#ffffff';
  }

  function getButtonForeground(color) {
    var luminance = relativeLuminance(hexRgb(color));
    var blackContrast = (luminance + 0.05) / 0.05;
    var whiteContrast = 1.05 / (luminance + 0.05);
    return blackContrast >= whiteContrast ? '#000000' : '#ffffff';
  }

  function customAccentRgb(dark) {
    var saturation = dark ? 0.68 : 0.58;
    var lightness = dark ? 0.66 : 0.42;
    var chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
    var hueSection = hue / 60;
    var secondary = chroma * (1 - Math.abs(hueSection % 2 - 1));
    var rgb;
    if (hueSection < 1) rgb = [chroma, secondary, 0];
    else if (hueSection < 2) rgb = [secondary, chroma, 0];
    else if (hueSection < 3) rgb = [0, chroma, secondary];
    else if (hueSection < 4) rgb = [0, secondary, chroma];
    else if (hueSection < 5) rgb = [secondary, 0, chroma];
    else rgb = [chroma, 0, secondary];
    var offset = lightness - chroma / 2;
    return [rgb[0], rgb[1], rgb[2]].map(function (channel) {
      return (channel + offset) * 255;
    });
  }

  function customButtonForeground(dark) {
    var luminance = relativeLuminance(customAccentRgb(dark));
    var blackContrast = (luminance + 0.05) / 0.05;
    var whiteContrast = 1.05 / (luminance + 0.05);
    return blackContrast >= whiteContrast ? '#000000' : '#ffffff';
  }

  var ICON = { light: 'light_mode', dark: 'dark_mode', system: 'routine', custom: 'palette' };
  var LABEL = {
    light: 'الوضع النهاري',
    dark: 'الوضع الليلي',
    system: 'حسب النظام',
    custom: 'وضع مخصص'
  };

  function syncToggleChrome(dark) {
    var sidebarIcon = document.getElementById('sidebarThemeIcon');
    var sidebarLabel = document.getElementById('sidebarThemeLabel');
    var topIcon = document.getElementById('themeToggleIconTopbar');

    if (sidebarLabel) {
      sidebarLabel.textContent = LABEL[mode];
    }
    var icon = ICON[mode];
    if (sidebarIcon) sidebarIcon.textContent = icon;
    if (topIcon) topIcon.textContent = icon;

    var toggles = document.querySelectorAll('[data-theme-toggle]');
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].setAttribute('aria-label', LABEL[mode] + (dark ? ' — مفعّل' : ' — متوقف'));
      toggles[i].setAttribute('aria-pressed', dark ? 'true' : 'false');
    }
  }

  function apply() {
    var doc = document.documentElement;
    var dark = resolveDark();
    var theme = dark ? 'dark' : 'light';

    doc.setAttribute('data-theme', theme);
    doc.setAttribute('data-theme-mode', mode);
    doc.setAttribute('data-density', prefs.density);
    doc.setAttribute('data-corner', prefs.corner);
    doc.style.setProperty('--user-hue', String(hue));
    doc.style.setProperty('--user-font-family', FONT_FAMILIES[prefs.fontFamily]);
    doc.style.setProperty('--user-font-size', prefs.fontSize + 'px');
    doc.style.fontSize = prefs.fontSize + 'px';
    doc.style.setProperty('--custom-button-bg', 'var(--user-accent)');
    doc.style.setProperty('--custom-button-fg', customButtonForeground(dark));
    doc.style.setProperty('--user-page-color', prefs.pageColor);
    doc.style.setProperty('--user-card-color', prefs.cardColor);
    doc.style.setProperty('--user-modal-color', prefs.modalColor);
    doc.style.setProperty('--user-border-color', prefs.borderColor);
    doc.style.setProperty('--user-text-color', readableColor(prefs.textColor, [prefs.pageColor]));
    doc.style.setProperty('--user-card-text-color', readableColor(prefs.textColor, [prefs.cardColor]));
    doc.style.setProperty('--user-modal-text-color', readableColor(prefs.textColor, [prefs.modalColor]));
    doc.style.setProperty('--user-muted-color', readableColor(prefs.mutedColor, [prefs.pageColor]));
    doc.style.setProperty('--user-card-muted-color', readableColor(prefs.mutedColor, [prefs.cardColor]));
    doc.style.setProperty('--user-modal-muted-color', readableColor(prefs.mutedColor, [prefs.modalColor]));
    doc.style.setProperty(
      '--user-inverse-text-color',
      readableColor(prefs.inverseTextColor, [readableColor(prefs.textColor, [prefs.pageColor])])
    );
    doc.style.setProperty('--user-button-color', prefs.buttonColor);
    doc.style.setProperty('--user-button-fg', getButtonForeground(prefs.buttonColor));
    doc.style.setProperty('--user-button-text', readableColor(prefs.buttonColor, [prefs.pageColor, prefs.cardColor]));
    doc.style.setProperty('--user-button-style', prefs.buttonStyle);
    doc.setAttribute('data-button-style', prefs.buttonStyle);

    /* Tailwind is configured with darkMode: 'class', so the .dark class has to
       mirror data-theme or every dark: utility stays inert. */
    doc.classList.toggle('dark', dark);

    /* Marks the resolved mode for the print layer, which always paints light. */
    doc.setAttribute('data-resolved-theme', theme);

    syncToggleChrome(dark);
  }

  function save() {
    try { localStorage.setItem(MODE_KEY, mode); } catch (e) {}
    writeJSON(PREF_KEY, prefs);
  }

  if (media) {
    var onChange = function () {
      if (mode === 'system') apply();
    };
    if (media.addEventListener) media.addEventListener('change', onChange);
    else if (media.addListener) media.addListener(onChange);
  }

  window.applyTheme = apply;

  window.toggleTheme = function () {
    /* Quick toggle keeps the historical two-state behaviour: it flips
       between light and dark and drops any custom hue. The full picker
       lives in the settings panel. */
    if (mode === 'system') {
      mode = systemPrefersDark() ? 'light' : 'dark';
    } else {
      mode = resolveDark() ? 'light' : 'dark';
      prefs.base = mode;
    }
    save();
    apply();
  };

  window.themeManager = {
    get mode() { return mode; },
    get prefs() { return prefs; },
    get resolved() { return resolveDark() ? 'dark' : 'light'; },
    setMode: function (next) {
      if (MODES.indexOf(next) === -1) return;
      if (next === 'custom' && prefs.base === undefined) {
        prefs.base = resolveDark() ? 'dark' : 'light';
      }
      if (next === 'light' || next === 'dark') prefs.base = next;
      mode = next;
      save();
      apply();
    },
    setDensity: function (next) {
      if (DENSITIES.indexOf(next) === -1) return;
      prefs.density = next;
      save();
      apply();
    },
    setCorner: function (next) {
      if (CORNERS.indexOf(next) === -1) return;
      prefs.corner = next;
      save();
      apply();
    },
    setHue: function (value) {
      hue = Math.max(0, Math.min(359, Math.round(Number(value) || 0)));
      prefs.hue = hue;
      save();
      apply();
    },
    setFontFamily: function (value) {
      var family = normalizeFontFamily(value);
      if (!family) return;
      prefs.fontFamily = family;
      save();
      apply();
    },
    setFontSize: function (value) {
      var size = normalizeFontSize(value);
      if (size === null) return;
      prefs.fontSize = size;
      save();
      apply();
    },
    setPageColor: function (value) {
      var color = normalizeHexColor(value);
      if (!color) return;
      prefs.pageColor = color;
      if (mode === 'custom') {
        prefs.base = relativeLuminance(hexRgb(color)) < 0.22 ? 'dark' : 'light';
      }
      save();
      apply();
    },
    setCardColor: function (value) {
      var color = normalizeHexColor(value);
      if (!color) return;
      prefs.cardColor = color;
      save();
      apply();
    },
    setModalColor: function (value) {
      var color = normalizeHexColor(value);
      if (!color) return;
      prefs.modalColor = color;
      save();
      apply();
    },
    setBorderColor: function (value) {
      var color = normalizeHexColor(value);
      if (!color) return;
      prefs.borderColor = color;
      save();
      apply();
    },
    setTextColor: function (value) {
      var color = normalizeHexColor(value);
      if (!color) return;
      prefs.textColor = color;
      save();
      apply();
    },
    setMutedColor: function (value) {
      var color = normalizeHexColor(value);
      if (!color) return;
      prefs.mutedColor = color;
      save();
      apply();
    },
    setInverseTextColor: function (value) {
      var color = normalizeHexColor(value);
      if (!color) return;
      prefs.inverseTextColor = color;
      save();
      apply();
    },
    setButtonColor: function (value) {
      var color = normalizeHexColor(value);
      if (!color) return;
      prefs.buttonColor = color;
      save();
      apply();
    },
    setButtonStyle: function (value) {
      if (BUTTON_STYLES.indexOf(value) === -1) return;
      prefs.buttonStyle = value;
      save();
      apply();
    }
  };

  apply();
})();
