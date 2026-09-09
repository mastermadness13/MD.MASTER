/**
 * Main Application JavaScript
 * Shared utilities for modal, sidebar, CSRF, back-to-top.
 */
(function () {
  'use strict';

  /* ── DOM Ready ── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function init() {
    initSidebar();
    initModals();
    initBackToTop();
    initCSRF();
  }

  /* ── Sidebar ── */
  function initSidebar() {
    var toggle = document.querySelector('[data-sidebar-toggle]');
    var close = document.querySelector('[data-sidebar-close]');

    function openSidebar() { document.body.classList.add('sidebar-open'); }
    function closeSidebar() { document.body.classList.remove('sidebar-open'); }

    if (toggle) {
      toggle.addEventListener('click', function (e) {
        e.stopPropagation();
        document.body.classList.contains('sidebar-open') ? closeSidebar() : openSidebar();
      });
    }
    if (close) {
      close.addEventListener('click', closeSidebar);
    }
  }

  /* ── Modals ── */
  function initModals() {
    // Close modals on backdrop click
    document.addEventListener('click', function (e) {
      if (e.target.classList.contains('modal-overlay')) {
        closeModalFromElement(e.target);
      }
    });
  }

  function openModalFromElement(el) {
    if (el) { el.classList.add('show'); document.body.style.overflow = 'hidden'; }
  }

  function closeModalFromElement(el) {
    if (el) { el.classList.remove('show'); document.body.style.overflow = ''; }
  }

  window.openModal = function (modalId) {
    var el = document.getElementById(modalId);
    openModalFromElement(el);
  };

  window.closeModal = function (modalId) {
    var el = document.getElementById(modalId);
    closeModalFromElement(el);
  };

  /* ── Back to Top ── */
  function initBackToTop() {
    var btn = document.getElementById('backToTop');
    if (!btn) return;

    var scrollEl = document.getElementById('mainContent') || window;

    scrollEl.addEventListener('scroll', function () {
      var scrollTop = scrollEl === window ? window.scrollY : scrollEl.scrollTop;
      btn.style.display = scrollTop > 400 ? 'flex' : 'none';
    });

    btn.addEventListener('click', function () {
      if (scrollEl === window) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } else {
        scrollEl.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });
  }

  /* ── CSRF Token ── */
  function initCSRF() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (!meta) return;
    var token = meta.getAttribute('content');

    document.querySelectorAll('form').forEach(function (form) {
      var existing = form.querySelector('input[name="_csrf_token"]');
      if (!existing) {
        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = '_csrf_token';
        input.value = token;
        form.appendChild(input);
      }
    });
  }

})();

/* ── Toast Notification System ── */
(function () {
  'use strict';

  var container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    container.setAttribute('aria-live', 'polite');
    container.setAttribute('aria-relevant', 'additions');
    document.body.appendChild(container);
  }

  var icons = {
    success: 'check_circle',
    error: 'error',
    warning: 'warning',
    info: 'info'
  };

  window.showToast = function (message, type, duration) {
    type = type || 'info';
    duration = duration || 4000;

    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.setAttribute('role', 'alert');

    toast.innerHTML =
      '<span class="material-symbols-outlined toast-icon">' + (icons[type] || 'info') + '</span>' +
      '<span class="toast-message">' + escapeHtml(message) + '</span>' +
      '<button class="toast-close material-symbols-outlined" aria-label="إغلاق">close</button>';

    var closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', function () {
      removeToast(toast);
    });

    container.appendChild(toast);

    if (duration > 0) {
      setTimeout(function () {
        removeToast(toast);
      }, duration);
    }

    var announcer = document.getElementById('srAnnouncer');
    if (!announcer) {
      announcer = document.createElement('div');
      announcer.id = 'srAnnouncer';
      announcer.className = 'sr-only';
      announcer.setAttribute('aria-live', 'assertive');
      document.body.appendChild(announcer);
    }
    announcer.textContent = message;
  };

  function removeToast(toast) {
    if (toast.classList.contains('removing')) return;
    toast.classList.add('removing');
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 300);
  }

  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  window.showToastSuccess = function (msg, dur) { window.showToast(msg, 'success', dur); };
  window.showToastError = function (msg, dur) { window.showToast(msg, 'error', dur); };
  window.showToastWarning = function (msg, dur) { window.showToast(msg, 'warning', dur); };
  window.showToastInfo = function (msg, dur) { window.showToast(msg, 'info', dur); };

})();
