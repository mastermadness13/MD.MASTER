/**
 * Fits a print document into exactly one A4 page (210mm x 297mm).
 *
 * CSS alone cannot shrink a form that is taller than the page, so the
 * overflow rule would just cut the bottom off. Instead the wrapper is scaled
 * to the ratio that fits and the sheet keeps the page size, so nothing is
 * clipped and the result is still a single sheet.
 *
 * Contract: the sheet is `.document-page`, the scalable content is its
 * first element child (the template's `doc_body` block). The sheet's own
 * padding is left alone, so the measurement uses the box's client area.
 *
 * Used by faculty_performance/_print_document.html, which is the parent of
 * the print/report pages.
 */
(function () {
  'use strict';

  function sheet() {
    return document.querySelector('.document-page');
  }

  function target(page) {
    return page ? page.firstElementChild : null;
  }

  function clearFit(page, box) {
    if (!page || !box) return;
    box.style.transform = '';
    box.style.transformOrigin = '';
    box.style.width = '';
    box.style.height = '';
  }

  function fit() {
    var page = sheet();
    var box = target(page);
    if (!page || !box) return;

    box.style.transform = 'none';
    box.style.width = '';
    box.style.height = '';

    var availW = page.clientWidth;
    var availH = page.clientHeight;
    if (!availW || !availH) return;

    /* Fit both axes, but never below 0.4: past that the text is no longer
       legible, and a clipped print is a worse failure than a second page. */
    var MIN_SCALE = 0.4;
    var scale = Math.min(1, availW / box.scrollWidth, availH / box.scrollHeight);
    if (scale < MIN_SCALE) scale = MIN_SCALE;
    if (scale >= 1) {
      clearFit(page, box);
      return;
    }

    /* Give the scaled copy the width it had before, so line wrapping is
       unchanged; the scale then shrinks the whole thing onto the sheet. */
    box.style.transformOrigin = 'top right';
    box.style.transform = 'scale(' + scale + ')';
    box.style.width = (100 / scale) + '%';
    box.style.height = (100 / scale) + '%';
  }

  function printDocument() {
    /* Fonts and images both move the layout, so measure only once the
       document is settled. */
    var ready = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    ready.then(function () {
      requestAnimationFrame(function () {
        fit();
        setTimeout(function () { window.print(); }, 60);
      });
    });
  }

  function refit() {
    /* Fonts can land after load and change the height. */
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  }

  window.printDocument = printDocument;
  window.addEventListener('beforeprint', fit);
  window.addEventListener('load', refit);
  document.addEventListener('DOMContentLoaded', refit);
  /* afterprint resets the sheet so the on-screen layout is untouched. */
  window.addEventListener('afterprint', function () {
    var page = sheet();
    clearFit(page, target(page));
  });
})();
