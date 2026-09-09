/**
 * Utilities - Shared helper functions for all public pages
 */
const Utils = {
  /**
   * Escape HTML to prevent XSS
   */
  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  },

  /**
   * Format a time string (HH:MM or HH:MM:SS) to display format
   */
  formatTime(time) {
    if (!time) return '';
    const parts = String(time).split(':');
    if (parts.length >= 2) {
      return `${parts[0]}:${parts[1]}`;
    }
    return time;
  },

  /**
   * Get today's Arabic weekday name
   */
  getArabicWeekday() {
    const days = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
    return days[new Date().getDay()];
  },

  /**
   * Get today's English weekday key (sunday..saturday)
   */
  getWeekdayKey() {
    const days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
    return days[new Date().getDay()];
  },

  /**
   * Get the weekdays array used in timetable (sun-sat)
   */
  getWeekdays() {
    return [
      { key: 'sunday', label: 'الأحد', short: 'أحد' },
      { key: 'monday', label: 'الاثنين', short: 'اثنين' },
      { key: 'tuesday', label: 'الثلاثاء', short: 'ثلاثاء' },
      { key: 'wednesday', label: 'الأربعاء', short: 'أربعاء' },
      { key: 'thursday', label: 'الخميس', short: 'خميس' },
      { key: 'friday', label: 'الجمعة', short: 'جمعة' },
      { key: 'saturday', label: 'السبت', short: 'سبت' }
    ];
  },

  /**
   * Build a URL preserving the ?dept= query param
   */
  withDeptParam(url) {
    const params = new URLSearchParams(window.location.search);
    const dept = params.get('dept');
    if (dept) {
      const sep = url.includes('?') ? '&' : '?';
      return `${url}${sep}dept=${encodeURIComponent(dept)}`;
    }
    return url;
  },

  /**
   * Show a loading state on an element
   */
  showLoading(el, message) {
    if (!el) return;
    el.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>${message || 'جاري التحميل...'}</p></div>`;
  },

  /**
   * Show an error state on an element
   */
  showError(el, message) {
    if (!el) return;
    el.innerHTML = `<div class="error-state"><p>${message || 'حدث خطأ في تحميل البيانات'}</p></div>`;
  },

  /**
   * Empty state
   */
  showEmpty(el, message) {
    if (!el) return;
    el.innerHTML = `<div class="empty-state"><p>${message || 'لا توجد بيانات'}</p></div>`;
  },

  /**
   * Debounce function
   */
  debounce(fn, delay = 300) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  },

  /**
   * Convert time "HH:MM" to minutes for sorting
   */
  timeToMinutes(time) {
    if (!time) return 0;
    const parts = String(time).split(':');
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1] || '0', 10);
  },

  /**
   * Compute the relative path prefix from the current page to the public root
   * (the folder that contains /shared/). Pass the script element that lives
   * in /shared/, e.g. document.currentScript for nav.js / data-client.js.
   */
  publicRoot(scriptEl) {
    if (!scriptEl || !scriptEl.src) return '';
    const src = scriptEl.src;
    const hostStart = src.indexOf('//') + 2;
    const path = src.substring(hostStart);
    const slashIdx = path.indexOf('/');
    const absSrc = slashIdx >= 0 ? path.substring(slashIdx) : path;
    const sharedIdx = absSrc.indexOf('/shared/');
    const publicAbs = sharedIdx >= 0 ? absSrc.substring(0, sharedIdx + 1) : '';
    const pageAbs = window.location.pathname;
    const pageDir = pageAbs.substring(0, pageAbs.lastIndexOf('/') + 1);
    const dirSegs = pageDir.split('/').filter(Boolean);
    const pubSegs = publicAbs.split('/').filter(Boolean);
    let common = 0;
    const maxLen = Math.min(dirSegs.length, pubSegs.length);
    while (common < maxLen && dirSegs[common] === pubSegs[common]) common++;
    let rel = '';
    for (let i = common; i < dirSegs.length; i++) rel += '../';
    for (let i = common; i < pubSegs.length; i++) rel += pubSegs[i] + '/';
    return rel;
  },

  /**
   * Resolve a public-root-relative target path (e.g. "pages/department.html")
   * to a URL relative to the CURRENT page. `rootPrefix` is the prefix from the
   * current page back to the public root (as returned by publicRoot()).
   */
  resolveRootRelative(target, rootPrefix) {
    const pageAbs = window.location.pathname;
    const pageDir = pageAbs.substring(0, pageAbs.lastIndexOf('/') + 1);
    const targetAbs = pageDir + (rootPrefix || '') + target;
    const out = [];
    for (const s of targetAbs.split('/').filter(Boolean)) {
      if (s === '..') out.pop();
      else if (s !== '.') out.push(s);
    }
    const tgtSegs = out;
    const dirSegs = pageDir.split('/').filter(Boolean);
    let common = 0;
    const maxLen = Math.min(dirSegs.length, tgtSegs.length);
    while (common < maxLen && dirSegs[common] === tgtSegs[common]) common++;
    let rel = '';
    for (let i = common; i < dirSegs.length; i++) rel += '../';
    for (let i = common; i < tgtSegs.length; i++) {
      rel += tgtSegs[i];
      if (i < tgtSegs.length - 1) rel += '/';
    }
    return rel;
  },

  /**
   * FontAwesome icon for a department id/name
   */
  deptIcon(dept) {
    const map = {
      1: 'fa-school',
      2: 'fa-tower-broadcast',
      3: 'fa-microchip',
      4: 'fa-helmet-safety',
      5: 'fa-building-columns',
      6: 'fa-oil-well',
      9: 'fa-flask',
      10: 'fa-gavel'
    };
    if (dept && dept.id) return map[dept.id] || 'fa-school';
    const name = dept && dept.name ? dept.name : '';
    if (name.includes('حاسوب')) return 'fa-microchip';
    if (name.includes('اتصال')) return 'fa-tower-broadcast';
    if (name.includes('مدني')) return 'fa-helmet-safety';
    if (name.includes('معماري')) return 'fa-building-columns';
    if (name.includes('نفط')) return 'fa-oil-well';
    if (name.includes('بحث')) return 'fa-flask';
    if (name.includes('امتحان')) return 'fa-gavel';
    return 'fa-school';
  },

  /**
   * Color helpers
   */
  getContrastColor(hex) {
    if (!hex) return '#ffffff';
    const r = parseInt(hex.substr(1, 2), 16);
    const g = parseInt(hex.substr(3, 2), 16);
    const b = parseInt(hex.substr(5, 2), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.5 ? '#1f2937' : '#ffffff';
  },

  /**
   * Hex to rgba with alpha
   */
  hexToRgba(hex, alpha = 0.15) {
    if (!hex) return `rgba(79,70,229,${alpha})`;
    const r = parseInt(hex.substr(1, 2), 16);
    const g = parseInt(hex.substr(3, 2), 16);
    const b = parseInt(hex.substr(5, 2), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
};

window.Utils = Utils;