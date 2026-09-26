/* Optional auto-print for the dedicated /print/* routes.
 *
 * Printing is opt-in: append ?autoprint=1 to the URL to open the browser
 * dialog on arrival. Otherwise, the page waits for the user to click its
 * print button.
 *
 * Scope and safety:
 *   - Only paths under /print/ qualify. The faculty-performance flow lives at
 *     /faculty-performance/print/<id> and is deliberately a preview -> print
 *     two-step, so it is excluded by construction rather than by a flag.
 *   - ?autoprint=1 explicitly enables auto-print for one visit.
 *   - A [data-no-autoprint] element anywhere in the document always opts out.
 *   - A short per-URL cooldown stops a refresh from re-opening the dialog in
 *     the user's face, while still allowing a deliberate re-print later.
 */

(function () {
  'use strict';

  var PREFIX = '/print/';
  var COOLDOWN_MS = 30000;
  var SETTLE_MS = 150;

  function shouldAutoPrint() {
    var path = window.location.pathname;
    if (path.indexOf(PREFIX) !== 0) return false;

    var flag = new URLSearchParams(window.location.search).get('autoprint');
    if (flag !== '1') return false;
    return !document.querySelector('[data-no-autoprint]');
  }

  function recentlyPrinted() {
    var key = 'printauto:' + window.location.pathname + window.location.search;
    try {
      var last = parseInt(sessionStorage.getItem(key) || '0', 10);
      if (last && Date.now() - last < COOLDOWN_MS) return true;
      sessionStorage.setItem(key, String(Date.now()));
    } catch (e) {
      /* Private mode or a full quota: fall through and print anyway. */
    }
    return false;
  }

  function fire() {
    if (!shouldAutoPrint() || recentlyPrinted()) return;
    window.print();
  }

  function run() {
    /* Fonts and late layout shifts both change pagination, so wait for the
       document to finish loading and for webfonts before opening the dialog. */
    var ready = document.fonts && document.fonts.ready
      ? document.fonts.ready
      : Promise.resolve();
    ready.then(function () {
      setTimeout(fire, SETTLE_MS);
    });
  }

  if (document.readyState === 'complete') {
    run();
  } else {
    window.addEventListener('load', run);
  }
})();
