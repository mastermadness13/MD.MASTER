/* SPA.modal — lightweight overlay modal for the SPA views. */
(function () {
  'use strict';

  var root = null;
  var current = null;

  function buildFrame(title) {
    var frame = document.createElement('div');
    frame.className = 'modal-overlay spa-modal-overlay show';
    frame.style.cssText = 'display:flex;align-items:center;justify-content:center;z-index:60;';
    frame.setAttribute('role', 'dialog');
    frame.setAttribute('aria-modal', 'true');
    frame.innerHTML =
      '<div class="spa-modal-card">' +
      '<div class="spa-modal-header">' +
      '<h3 class="spa-modal-title">' + (title || '') + '</h3>' +
      '<button type="button" class="spa-modal-close" data-spa-modal-close>&times;</button>' +
      '</div>' +
      '<div class="spa-modal-body"></div>' +
      '</div>';
    return frame;
  }

  function open(opts) {
    opts = opts || {};
    close();
    root = document.createElement('div');
    root.id = 'spa-modal-root';
    document.body.appendChild(root);
    root.appendChild(buildFrame(opts.title));
    var frame = root.querySelector('.spa-modal-card');
    frame.querySelector('.spa-modal-body').appendChild(opts.body);
    document.body.style.overflow = 'hidden';
    current = {
      frame: frame,
      options: opts,
      close: close,
      setBusy: function (busy) {
        var btn = frame.querySelector('.spa-modal-footer [data-spa-save]');
        if (btn) { btn.disabled = busy; btn.dataset.busy = busy ? '1' : ''; }
      }
    };
    frame.querySelector('[data-spa-modal-close]').addEventListener('click', close);
    frame.addEventListener('click', function (e) {
      if (e.target === frame) close();
    });
    if (opts.onOpen) opts.onOpen(current);
    return current;
  }

  function close() {
    if (root && root.parentNode) {
      root.parentNode.removeChild(root);
    }
    root = null;
    current = null;
    document.body.style.overflow = '';
  }

  function showError(message) {
    var body = current && current.frame.querySelector('.spa-modal-body');
    if (!body) return;
    var old = body.querySelector('.spa-modal-error');
    if (old) old.remove();
    var el = document.createElement('div');
    el.className = 'spa-modal-error';
    el.textContent = message;
    body.prepend(el);
  }

  window.SPA = window.SPA || {};
  window.SPA.modal = { open: open, close: close, showError: showError };
})();
