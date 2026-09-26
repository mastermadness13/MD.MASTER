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
  var hue = typeof prefs.hue === 'number' && isFinite(prefs.hue) ? prefs.hue : 280;

  function systemPrefersDark() {
    return !!(media && media.matches);
  }

  function resolveDark() {
    if (mode === 'dark') return true;
    if (mode === 'system') return systemPrefersDark();
    /* light and custom both follow the user's explicit light/dark pick. */
    return prefs.base === 'dark';
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
    }
  };

  apply();
})();
