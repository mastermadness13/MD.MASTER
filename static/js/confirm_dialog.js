/* Shared confirmation dialog (Apple-style destructive confirmation).
   Two modes:
   1. Any <form data-confirm-message="..."> is intercepted; on submit the dialog
      opens and confirming fires the native submit via form.submit().
   2. window.confirmThenSubmit(formId, message) for buttons that submit a form
      programmatically (e.g. reset-password flows).
   Optional attributes: data-confirm-title, data-confirm-label, data-confirm-danger.
   Focus moves to Cancel on open and returns to the trigger on close. */
(function () {
  var overlay = document.getElementById('confirmDialog');
  if (!overlay) return;

  var titleEl = document.getElementById('confirmDialogTitle');
  var msgEl = document.getElementById('confirmDialogMessage');
  var iconEl = document.getElementById('confirmDialogIcon');
  var okBtn = document.getElementById('confirmDialogOk');
  var cancelBtn = document.getElementById('confirmDialogCancel');
  var dialog = overlay.querySelector('.confirm-dialog');

  var pendingForm = null;
  var pendingCallback = null;
  var lastFocus = null;

  function open(opts) {
    if (titleEl) titleEl.textContent = opts.title || 'تأكيد';
    if (msgEl) msgEl.textContent = opts.message || 'هل أنت متأكد؟';
    if (okBtn) okBtn.textContent = opts.label || 'تأكيد';
    var danger = opts.danger !== false;
    if (okBtn) {
      okBtn.classList.toggle('btn-error', danger);
      okBtn.classList.toggle('btn-primary', !danger);
    }
    if (iconEl) {
      iconEl.textContent = danger ? 'warning' : 'help';
    }
    dialog.classList.toggle('is-confirm', !danger);
    overlay.classList.add('show');
    overlay.setAttribute('aria-hidden', 'false');
    lastFocus = document.activeElement;
    if (cancelBtn) cancelBtn.focus();
  }

  function close(restoreFocus) {
    overlay.classList.remove('show');
    overlay.setAttribute('aria-hidden', 'true');
    pendingForm = null;
    pendingCallback = null;
    if (restoreFocus !== false && lastFocus && lastFocus.focus) {
      try { lastFocus.focus(); } catch (e) { /* noop */ }
    }
    lastFocus = null;
  }

  function onConfirm() {
    if (pendingForm) {
      var f = pendingForm;
      pendingForm = null;
      // Remove the guard so the native submit below does not re-open the dialog.
      f.removeAttribute('data-confirm-message');
      try { f.submit(); } catch (e) { console.error('confirm submit failed', e); }
      close(false);
    } else if (pendingCallback) {
      var cb = pendingCallback;
      pendingCallback = null;
      close(false);
      cb();
    } else {
      close();
    }
  }

  if (okBtn) okBtn.addEventListener('click', onConfirm);
  if (cancelBtn) cancelBtn.addEventListener('click', function () { close(); });

  if (overlay) {
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) close();
    });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && overlay.classList.contains('show')) {
      close();
    }
  });

  // Intercept any form that opts in via data-confirm-message.
  document.addEventListener('submit', function (e) {
    var form = e.target && e.target.closest ? e.target.closest('form[data-confirm-message]') : null;
    if (!form) return;
    e.preventDefault();
    pendingForm = form;
    pendingCallback = null;
    open({
      title: form.getAttribute('data-confirm-title') || undefined,
      message: form.getAttribute('data-confirm-message') || undefined,
      label: form.getAttribute('data-confirm-label') || undefined,
      danger: (form.getAttribute('data-confirm-danger') || 'true') !== 'false'
    });
  }, true);

  // Programmatic variant: confirm, then submit the named form.
  window.confirmThenSubmit = function (formId, message, opts) {
    var f = document.getElementById(formId);
    if (!f) return;
    pendingForm = f;
    pendingCallback = null;
    open({
      message: message || 'هل تريد المتابعة؟',
      label: (opts && opts.label) || 'تأكيد',
      danger: !(opts && opts.danger === false)
    });
  };

  // Fully generic variant: confirm, then run a callback.
  window.askConfirm = function (opts) {
    pendingForm = null;
    pendingCallback = (opts && typeof opts.onConfirm === 'function') ? opts.onConfirm : null;
    open(opts || {});
  };
})();