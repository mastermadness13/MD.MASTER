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

  var prefs = readJSON(PREF_KEY, {});
  var mode = readMode();
  if (DENSITIES.indexOf(prefs.density) === -1) prefs.density = 'comfortable';
  if (CORNERS.indexOf(prefs.corner) === -1) prefs.corner = 'soft';
  var hue = typeof prefs.hue === 'number' && isFinite(prefs.hue)
    ? Math.max(0, Math.min(359, Math.round(prefs.hue)))
    : 280;

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
    if (!isFinite(value) || value < 13 || value > 20) return null;
    return Math.abs(value * 2 - Math.round(value * 2)) < 0.000001 ? value : null;
  }

  prefs.fontFamily = normalizeFontFamily(prefs.fontFamily) || DEFAULT_FONT_FAMILY;
  prefs.fontSize = normalizeFontSize(prefs.fontSize);
  if (prefs.fontSize === null) prefs.fontSize = DEFAULT_FONT_SIZE;

  function systemPrefersDark() {
    return !!(media && media.matches);
  }

  function resolveDark() {
    if (mode === 'dark') return true;
    if (mode === 'system') return systemPrefersDark();
    /* light and custom both follow the user's explicit light/dark pick. */
    return prefs.base === 'dark';
  }

  function relativeLuminance(rgb) {
    function linearize(channel) {
      channel /= 255;
      return channel <= 0.04045 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4);
    }
    return 0.2126 * linearize(rgb[0]) + 0.7152 * linearize(rgb[1]) + 0.0722 * linearize(rgb[2]);
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
    doc.style.setProperty('--custom-button-bg', 'var(--user-accent)');
    doc.style.setProperty('--custom-button-fg', customButtonForeground(dark));

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
      if (mode === 'light') prefs.base = 'light';
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
      if (next !== 'custom') prefs.base = resolveDark() ? 'dark' : 'light';
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
    }
  };

  apply();
})();
