/**
 * mobile_actions.js — app-like mobile interactions for record-list tables.
 *
 *  A. Tap a table row (phones) → bottom action sheet built from the row's
 *     own links/forms (عرض / تعديل / حذف …). No navigation away.
 *  B. Edit/View open in an in-page bottom-sheet popup: the target page is
 *     fetched, the main content region extracted, and its form submitted
 *     via fetch. Validation errors re-render inside the popup.
 *  C. Delete/archive asks a small confirm sheet, then runs the row's
 *     existing POST form via fetch.
 *  D. After success → toast + in-place refresh of #mainContent region.
 *  E. Wide tables get a "ملء الشاشة" chip: real fullscreen + landscape
 *     lock where supported (Android), pseudo-fullscreen + rotate hint on
 *     iPhone (Apple forbids orientation locks).
 *
 * Desktop (>768px) is untouched; everything is gated by media query.
 */
(function () {
  'use strict';

  if (!document.body || !document.getElementById('mainContent')) return;
  if (document.body.hasAttribute('data-skip-mobile-actions')) return;

  var mqPhone = window.matchMedia('(max-width: 768px)');

  /* Tables that are input canvases / special views — never row-menus */
  var TABLE_BLACKLIST = '.gradebook-table, .timetable, .timetable-grid, ' +
    '.matrix-grid, .cc-sheet table, [data-no-row-menu]';

  var ICON_AR = {
    person: 'الملف التفصيلي', visibility: 'عرض', visibility_off: 'إخفاء',
    edit: 'تعديل', edit_note: 'تعديل', pageview: 'عرض',
    archive: 'أرشفة', unarchive: 'استعادة', restore_from_trash: 'استعادة',
    delete: 'حذف', delete_forever: 'حذف نهائي',
    print: 'طباعة', download: 'تنزيل', upload_file: 'المرفق',
    description: 'التفاصيل', science: 'البحث', work: 'التكليفات',
    event_busy: 'الإجازات', quiz: 'الامتحانات', settings: 'إعدادات',
    assignment: 'التفاصيل', folder: 'الملفات', link: 'فتح'
  };

  /* ────────────────────────────────────────────────────────────────
     Shared helpers
  ──────────────────────────────────────────────────────────────── */

  function escapeHtml(str) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(String(str == null ? '' : str)));
    return d.innerHTML;
  }

  function stripScripts(root) {
    if (!root) return root;
    var scripts = root.querySelectorAll('script');
    for (var i = 0; i < scripts.length; i++) scripts[i].parentNode.removeChild(scripts[i]);
    return root;
  }

  function extractMainRegion(htmlText) {
    var doc = new DOMParser().parseFromString(htmlText, 'text/html');
    var region = doc.querySelector('#mainContent .main-content-inner');
    if (!region) return null;
    var clone = region.cloneNode(true);
    stripScripts(clone);
    /* remove app chrome that makes no sense inside a popup */
    ['#sidebarOverlay', '#backToTop'].forEach(function (sel) {
      var n = clone.querySelector(sel);
      if (n) n.parentNode.removeChild(n);
    });
    return clone;
  }

  function csrfFromMeta() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  }

  function toast(msg, type) {
    if (window.showToast) window.showToast(msg, type || 'success', 3500);
  }

  /* ────────────────────────────────────────────────────────────────
     In-place refresh of the current list page
  ──────────────────────────────────────────────────────────────── */

  var refreshing = false;

  function refreshInPlace() {
    if (refreshing) return;
    refreshing = true;
    var scrollEl = document.getElementById('mainContent');
    var st = scrollEl ? scrollEl.scrollTop : 0;
    fetch(location.href, { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('bad status');
        return r.text();
      })
      .then(function (html) {
        var fresh = extractMainRegion(html);
        var cur = document.querySelector('#mainContent .main-content-inner');
        if (fresh && cur) {
          cur.innerHTML = fresh.innerHTML;
          if (scrollEl) scrollEl.scrollTop = st;
        } else {
          location.reload();
        }
      })
      .catch(function () { location.reload(); })
      .then(function () {
        setTimeout(function () { refreshing = false; }, 300);
      });
  }

  /* ────────────────────────────────────────────────────────────────
     Bottom sheet primitives (action sheet + confirm sheet)
  ──────────────────────────────────────────────────────────────── */

  var sheetEl = null;

  function ensureSheet() {
    if (sheetEl) return sheetEl;
    sheetEl = document.createElement('div');
    sheetEl.className = 'ras-overlay';
    sheetEl.innerHTML =
      '<div class="ras-backdrop"></div>' +
      '<div class="ras-sheet" role="menu" aria-modal="true">' +
      '<div class="ras-handle"></div>' +
      '<div class="ras-title"></div>' +
      '<div class="ras-items"></div>' +
      '<button type="button" class="ras-cancel">إلغاء</button>' +
      '</div>';
    document.body.appendChild(sheetEl);
    sheetEl.querySelector('.ras-backdrop').addEventListener('click', closeSheet);
    sheetEl.querySelector('.ras-cancel').addEventListener('click', closeSheet);
    return sheetEl;
  }

  function openSheet(title, items) {
    if (!items || !items.length) return;
    var el = ensureSheet();
    el.querySelector('.ras-title').textContent = title || 'إجراءات';
    var box = el.querySelector('.ras-items');
    box.innerHTML = '';
    items.forEach(function (it) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'ras-item' + (it.danger ? ' ras-danger' : '');
      b.innerHTML =
        '<span class="material-symbols-outlined ras-icon">' + escapeHtml(it.icon || 'chevron_left') + '</span>' +
        '<span class="ras-label">' + escapeHtml(it.label) + '</span>' +
        '<span class="material-symbols-outlined ras-chevron">chevron_left</span>';
      b.addEventListener('click', function () {
        closeSheet();
        setTimeout(function () { it.run(); }, 120);
      });
      box.appendChild(b);
    });
    el.classList.add('show');
    document.body.classList.add('sheet-open');
  }

  function closeSheet() {
    if (!sheetEl) return;
    sheetEl.classList.remove('show');
    document.body.classList.remove('sheet-open');
  }

  function showConfirm(opts) {
    openSheet(opts.title || 'تأكيد الإجراء', [
      {
        label: opts.confirmLabel || 'تأكيد الحذف',
        icon: opts.icon || 'delete_forever',
        danger: true,
        run: opts.onConfirm
      },
      { label: 'إلغاء', icon: 'close', run: function () {} }
    ]);
    /* put cancel styling on the second item instead of danger */
    var items = sheetEl.querySelectorAll('.ras-item');
    if (items[1]) items[1].classList.remove('ras-danger');
  }

  /* ────────────────────────────────────────────────────────────────
     Row action extraction
  ──────────────────────────────────────────────────────────────── */

  function iconOf(el) {
    var ic = el.querySelector('.material-symbols-outlined');
    if (ic) {
      var name = (ic.textContent || '').trim();
      if (/^[a-z_]{3,30}$/.test(name)) return name;
    }
    return '';
  }

  function labelFor(icon, el, fallback) {
    var t = el.getAttribute('title') || el.getAttribute('aria-label');
    if (t) return t;
    if (icon && ICON_AR[icon]) return ICON_AR[icon];
    var txt = (el.textContent || '').trim();
    if (txt && txt.length <= 20) return txt;
    return fallback || 'فتح';
  }

  function collectRowActions(tr) {
    var items = [];
    var seen = {};

    tr.querySelectorAll('a[href]').forEach(function (a) {
      var href = a.getAttribute('href') || '';
      if (!href || href === '#') return;
      var icon = iconOf(a);
      var txt = (a.textContent || '').trim();
      var titled = !!(a.getAttribute('title') || a.getAttribute('aria-label'));
      var iconOnly = !!icon && txt.length <= 24 && !/\s/.test(txt.replace(/[_a-z]/g, ''));
      if (!titled && !iconOnly && !(icon && ICON_AR[icon])) return; /* plain text links stay native */
      var key = 'a:' + href;
      if (seen[key]) return;
      seen[key] = 1;
      var external = a.target === '_blank' || (a.origin && a.origin !== location.origin);
      items.push({
        label: labelFor(icon, a, 'فتح'),
        icon: icon || 'open_in_new',
        run: function () {
          if (external) { window.open(href, '_blank', 'noopener'); return; }
          openPopup(labelFor(icon, a, 'عرض'), href);
        }
      });
    });

    tr.querySelectorAll('form').forEach(function (f) {
      var action = f.getAttribute('action');
      var method = (f.getAttribute('method') || 'get').toLowerCase();
      if (!action || method !== 'post' || f.closest('[data-no-row-menu]')) return;
      var btn = f.querySelector('button[type="submit"], button:not([type]) , input[type="submit"]');
      if (!btn) return;
      var key = 'f:' + action;
      if (seen[key]) return;
      seen[key] = 1;
      var icon = iconOf(btn) || iconOf(f);
      var lbl = labelFor(icon, btn.getAttribute('title') ? btn : f, 'تنفيذ');
      var dangerous = /delete|archive|remove|trash|cancel/i.test(icon) ||
        /حذف|أرشفة|إزالة|رفض/.test(lbl) ||
        /confirm/i.test(f.getAttribute('onsubmit') || '');
      var msg = 'هل أنت متأكد من تنفيذ هذا الإجراء؟';
      var m = (f.getAttribute('onsubmit') || '').match(/confirm\(\s*['"]([\s\S]*?)['"]\s*\)/);
      if (m && m[1]) msg = m[1];

      items.push({
        label: lbl,
        icon: icon || (dangerous ? 'delete' : 'play_arrow'),
        danger: dangerous,
        run: function () {
          showConfirm({
            title: lbl,
            message: undefined,
            confirmLabel: lbl,
            icon: icon || 'delete_forever',
            onConfirm: function () { submitHiddenForm(f); }
          });
          /* swap generic title line with the form's own confirm text */
          if (m && m[1] && sheetEl) sheetEl.querySelector('.ras-title').textContent = m[1];
        }
      });
    });

    tr.querySelectorAll('button[data-view], button[data-edit], button[data-del], button[data-restore], button[data-user-id], button[onclick]')
      .forEach(function (b) {
        var icon = iconOf(b);
        var titled = !!(b.getAttribute('title') || b.getAttribute('aria-label'));
        if (!titled && !icon) return;
        var key = 'b:' + (b.dataset.view || b.dataset.edit || b.dataset.del || b.dataset.restore || icon || Math.random());
        if (seen[key]) return;
        seen[key] = 1;
        items.push({
          label: labelFor(icon, b),
          icon: icon || 'touch_app',
          run: function () { if (typeof b.click === 'function') b.click(); }
        });
      });

    return items;
  }

  function submitHiddenForm(form) {
    var fd = new FormData(form);
    if (!fd.has('_csrf_token')) fd.append('_csrf_token', csrfFromMeta());
    fetch(form.action, { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(function (r) {
        if (r.redirected || r.ok) {
          toast('تم تنفيذ الإجراء بنجاح', 'success');
          refreshInPlace();
        } else {
          throw new Error('status ' + r.status);
        }
      })
      .catch(function () {
        toast('تعذر تنفيذ الإجراء، سيتم المحاولة بالطريقة العادية', 'error');
        /* last resort: behave exactly like the original form */
        var clone = form.cloneNode(true);
        clone.style.display = 'none';
        document.body.appendChild(clone);
        clone.submit();
        setTimeout(function () { clone.parentNode.removeChild(clone); }, 5000);
      });
  }

  /* ────────────────────────────────────────────────────────────────
     Row tap → action sheet
  ──────────────────────────────────────────────────────────────── */

  function rowOf(target) {
    var tr = target.closest ? target.closest('tr') : null;
    if (!tr) return null;
    var table = tr.closest('table');
    if (!table || tr.closest(TABLE_BLACKLIST)) return null;
    if (table.closest('.modal, .mp-overlay, .ras-overlay, [data-no-row-menu]')) return null;
    return tr;
  }

  document.addEventListener('click', function (e) {
    if (!mqPhone.matches || !sheetElOpenable(e)) return;
    if (e.target.closest('a, button, input, select, textarea, label, form, [data-row-menu-ignore]')) return;
    var tr = rowOf(e.target);
    if (!tr) return;
    var actions = collectRowActions(tr);
    if (!actions.length) return;
    e.preventDefault();
    var headCell = tr.querySelector('td:nth-child(2)');
    var title = ((headCell ? headCell.textContent : '') || '').trim().replace(/\s+/g, ' ').slice(0, 42);
    highlightRow(tr);
    openSheet(title || 'إجراءات السجل', actions);
  }, true);

  function sheetElOpenable() { return true; }

  var highlightedTd = null;
  function highlightRow(tr) {
    if (highlightedTd) highlightedTd.classList.remove('row-active');
    highlightedTd = tr;
    tr.classList.add('row-active');
    setTimeout(function () { tr.classList.remove('row-active'); }, 900);
  }

  /* ────────────────────────────────────────────────────────────────
     Content popup (edit / view without leaving the page)
  ──────────────────────────────────────────────────────────────── */

  var popupEl = null;

  function ensurePopup() {
    if (popupEl) return popupEl;
    popupEl = document.createElement('div');
    popupEl.className = 'mp-overlay';
    popupEl.innerHTML =
      '<div class="mp-backdrop"></div>' +
      '<div class="mp-panel" role="dialog" aria-modal="true">' +
      '<div class="mp-head">' +
      '<span class="material-symbols-outlined mp-title-icon">edit_note</span>' +
      '<span class="mp-title"></span>' +
      '<button type="button" class="mp-close material-symbols-outlined" aria-label="إغلاق">close</button>' +
      '</div>' +
      '<div class="mp-body"><div class="mp-loading"><span class="mp-spinner"></span>جارٍ التحميل…</div>' +
      '<div class="mp-content"></div></div>' +
      '</div>';
    document.body.appendChild(popupEl);
    popupEl.querySelector('.mp-backdrop').addEventListener('click', closePopup);
    popupEl.querySelector('.mp-close').addEventListener('click', closePopup);

    /* delegated submit handling for any form injected into the popup */
    popupEl.addEventListener('submit', function (e) {
      var form = e.target.closest('.mp-content form');
      if (!form) return;
      e.preventDefault();
      submitPopupForm(form);
    });
    return popupEl;
  }

  function openPopup(title, url) {
    var el = ensurePopup();
    el.querySelector('.mp-title').textContent = title || '';
    var content = el.querySelector('.mp-content');
    content.innerHTML = '';
    el.querySelector('.mp-loading').style.display = 'flex';
    el.classList.add('show');
    document.body.classList.add('popup-open');

    fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) {
        if (!r.ok) throw new Error('status ' + r.status);
        return r.text();
      })
      .then(function (html) {
        var region = extractMainRegion(html);
        if (!region) { location.href = url; return; }
        el.querySelector('.mp-loading').style.display = 'none';
        content.innerHTML = region.innerHTML;
        enhanceInjected(content);
      })
      .catch(function () {
        toast('تعذر فتح النافذة، جارٍ فتح الصفحة…', 'error');
        location.href = url;
      });
  }

  function closePopup() {
    if (!popupEl) return;
    popupEl.classList.remove('show');
    document.body.classList.remove('popup-open');
  }

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (popupEl && popupEl.classList.contains('show')) closePopup();
    else if (sheetEl && sheetEl.classList.contains('show')) closeSheet();
  });

  function submitPopupForm(form) {
    var btn = form.querySelector('button[type="submit"]');
    if (btn) btn.disabled = true;
    var fd = new FormData(form);
    if (!fd.has('_csrf_token')) fd.append('_csrf_token', csrfFromMeta());

    fetch(form.action, { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(function (r) { return r.text().then(function (t) { return { r: r, t: t }; }); })
      .then(function (res) {
        if (btn) btn.disabled = false;
        var redirected = res.r.redirected;
        var finalUrl = res.r.url || '';
        var actionPath = new URL(form.action, location.href).pathname;
        var landedSame = finalUrl.indexOf(actionPath) !== -1;
        if (redirected || (!landedSame && res.r.ok)) {
          closePopup();
          toast('تم الحفظ بنجاح', 'success');
          refreshInPlace();
        } else if (res.r.ok) {
          /* 200 response: either a validation re-render of the form,
             or a success page rendered in place — tell them apart */
          var region = extractMainRegion(res.t);
          var looksLikeForm = region && region.querySelector('form');
          if (region && looksLikeForm) {
            popupEl.querySelector('.mp-content').innerHTML = region.innerHTML;
            enhanceInjected(popupEl.querySelector('.mp-content'));
            popupEl.querySelector('.mp-body').scrollTop = 0;
            toast('يرجى مراجعة الحقول المطلوبة', 'warning');
          } else {
            closePopup(); toast('تم الحفظ بنجاح', 'success'); refreshInPlace();
          }
        } else {
          throw new Error('status ' + res.r.status);
        }
      })
      .catch(function () {
        if (btn) btn.disabled = false;
        toast('تعذر الحفظ، تحقق من الاتصال وحاول مجدداً', 'error');
      });
  }

  /* re-init TomSelect on selects the original pages enhanced */
  function enhanceInjected(root) {
    if (typeof TomSelect !== 'function') return;
    root.querySelectorAll('select[multiple]').forEach(function (sel) {
      if (sel.tomselect || sel.closest('.ts-wrapper')) return;
      try { new TomSelect(sel, { plugins: ['remove_button'], maxOptions: 300 }); } catch (err) {}
    });
  }

  /* ────────────────────────────────────────────────────────────────
     Fullscreen "flip" mode for wide tables
  ──────────────────────────────────────────────────────────────── */

  var TFS_ANCHOR = '.table-scroll-wrap, .table-container';

  function injectFullscreenButtons(root) {
    var scope = root || document;
    scope.querySelectorAll(TFS_ANCHOR).forEach(function (wrap) {
      if (wrap.closest('[data-no-fullscreen], .modal, .mp-overlay, .cc-sheet, .document-page')) return;
      if (wrap.previousElementSibling && wrap.previousElementSibling.classList.contains('tfs-btn')) return;
      var table = wrap.querySelector('table');
      if (!table) return;
      var wide = table.scrollWidth > wrap.clientWidth + 8 || table.querySelector('[data-wide-table]');
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'tfs-btn material-symbols-outlined';
      btn.title = 'عرض الجدول بملء الشاشة';
      btn.textContent = 'fullscreen';
      btn.setAttribute('aria-label', 'عرض الجدول بملء الشاشة');
      btn.addEventListener('click', function () { enterTableFullscreen(wrap); });
      wrap.parentNode.insertBefore(btn, wrap);
      if (!wide) btn.classList.add('tfs-optional');
    });
  }

  var tfsActive = null;
  var rotateHintShownAt = 0;

  function enterTableFullscreen(wrap) {
    if (tfsActive) exitTableFullscreen();

    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'tfs-close material-symbols-outlined';
    closeBtn.textContent = 'close';
    closeBtn.title = 'إغلاق ملء الشاشة';
    closeBtn.addEventListener('click', exitTableFullscreen);

    var nativeFs = wrap.requestFullscreen || wrap.webkitRequestFullscreen || wrap.msRequestFullscreen;
    if (nativeFs) {
      var req = nativeFs.call(wrap, { navigationUI: 'hide' });
      Promise.resolve(req).catch(function () {}).then(function () {
        wrap.classList.add('tfs-on');
        wrap.insertBefore(closeBtn, wrap.firstChild);
        tfsActive = wrap;
        lockLandscape();
      });
    } else {
      /* iPhone Safari: no element fullscreen → pseudo mode */
      wrap.classList.add('tfs-on', 'tfs-fake');
      wrap.insertBefore(closeBtn, wrap.firstChild);
      document.body.classList.add('tfs-lock');
      tfsActive = wrap;
      lockLandscape();
    }
  }

  function lockLandscape() {
    var so = screen.orientation;
    if (so && typeof so.lock === 'function') {
      so.lock('landscape').catch(function () { showRotateHintOnce(); });
    } else {
      showRotateHintOnce();
    }
  }

  function showRotateHintOnce() {
    var now = Date.now();
    if (now - rotateHintShownAt < 8000) return;
    rotateHintShownAt = now;
    var hint = document.createElement('div');
    hint.className = 'rotate-hint';
    hint.innerHTML = '<span class="material-symbols-outlined">screen_rotation</span> أدر جهازك أفقياً لعرض الجدول كاملاً';
    document.body.appendChild(hint);
    setTimeout(function () { hint.classList.add('show'); }, 10);
    setTimeout(function () {
      hint.classList.remove('show');
      setTimeout(function () { hint.parentNode.removeChild(hint); }, 400);
    }, 3800);
  }

  function exitTableFullscreen() {
    if (!tfsActive) return;
    var wrap = tfsActive;
    tfsActive = null;
    var c = wrap.querySelector('.tfs-close');
    if (c) c.parentNode.removeChild(c);
    wrap.classList.remove('tfs-on', 'tfs-fake');
    document.body.classList.remove('tfs-lock');
    if (document.fullscreenElement || document.webkitFullscreenElement) {
      (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    }
    var so = screen.orientation;
    if (so && typeof so.unlock === 'function') { try { so.unlock(); } catch (err) {} }
  }

  document.addEventListener('fullscreenchange', function () {
    if (!document.fullscreenElement && tfsActive &&
        tfsActive.classList.contains('tfs-on') && !tfsActive.classList.contains('tfs-fake')) {
      exitTableFullscreen();
    }
  });

  /* ────────────────────────────────────────────────────────────────
     Boot
  ──────────────────────────────────────────────────────────────── */

  function boot() {
    injectFullscreenButtons(document);

    var main = document.getElementById('mainContent');
    if (main && window.MutationObserver) {
      var t = null;
      new MutationObserver(function () {
        clearTimeout(t);
        t = setTimeout(function () { injectFullscreenButtons(document); }, 250);
      }).observe(main, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
