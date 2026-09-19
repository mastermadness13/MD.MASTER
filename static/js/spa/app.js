/* SPA.app — bootstrap, shell, router, and universal content region. */
(function () {
  'use strict';

  var SESSION = null;
  var CONTENT_FETCHER_ROUTES = {};

  window.SPA = window.SPA || {};
  window.SPA.session = null;
  window.SPA.VIEWS = window.SPA.VIEWS || {};

  function escapeHtml(str) {
    if (!str && str !== 0) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  window.SPA.escapeHtml = escapeHtml;

  /* ------------------------------------------------------------ bootstrap */
  function bootstrap() {
    window.SPA.api.get('/api/auth/me').then(function (data) {
      SESSION = data;
      window.SPA.session = data;
      renderShell();
    }).catch(function () {
      renderLogin();
    });
  }

  /* --------------------------------------------------------------- login */
  function renderLogin() {
    var root = document.getElementById('app');
    root.innerHTML = '<div class="min-h-screen flex items-center justify-center p-4">' +
      '<div class="bg-white rounded-2xl shadow-lg p-8 w-full max-w-sm border border-outline">' +
      '<div class="text-center mb-6">' +
      '<span class="material-symbols-outlined text-5xl text-primary">school</span>' +
      '<h1 class="text-xl font-bold text-on-surface mt-2">كلية التقنية الهندسية زوارة</h1>' +
      '<p class="text-sm text-on-surface-variant mt-1">نظام إدارة الكلية</p>' +
      '</div>' +
      '<form id="spa-login-form">' +
      '<div class="mb-4">' +
      '<label class="block text-sm font-bold mb-1">اسم المستخدم</label>' +
      '<input name="username" type="text" required class="w-full px-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary">' +
      '</div>' +
      '<div class="mb-4">' +
      '<label class="block text-sm font-bold mb-1">كلمة المرور</label>' +
      '<input name="password" type="password" required class="w-full px-3 py-2 rounded-lg border border-outline text-sm focus:outline-none focus:ring-2 focus:ring-primary">' +
      '</div>' +
      '<div id="spa-login-error" class="hidden text-error text-sm font-bold mb-3"></div>' +
      '<button type="submit" class="w-full py-2.5 rounded-lg bg-primary text-on-primary font-bold text-sm hover:opacity-90">تسجيل الدخول</button>' +
      '</form></div></div>';

    document.getElementById('spa-login-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = e.target.querySelector('button[type=submit]');
      btn.disabled = true;
      window.SPA.api.post('/api/auth/login', {
        username: e.target.username.value.trim(),
        password: e.target.password.value,
        remember: true
      }).then(function () {
        window.location.reload();
      }).catch(function (err) {
        if (err.status === 429) {
          var box = document.getElementById('spa-login-error');
          box.classList.add('hidden');
          window.SPA.showToast(err.message, 'warning');
        } else {
          var box = document.getElementById('spa-login-error');
          box.textContent = err.message;
          box.classList.remove('hidden');
        }
        btn.disabled = false;
      });
    });
  }

  /* ---------------------------------------------------------------- shell */
  function renderShell() {
    var user = SESSION.user || {};
    var root = document.getElementById('app');
    root.innerHTML =
      '<header id="app-header" class="bg-white border-b border-outline-variant sticky top-0 z-30 shadow-sm">' +
      '<div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-4">' +
      '<div class="flex items-center gap-3">' +
      '<span class="material-symbols-outlined text-primary text-3xl">school</span>' +
      '<div>' +
      '<div class="font-bold text-on-surface leading-tight">كلية التقنية الهندسية زوارة</div>' +
      '<div class="text-xs text-on-surface-variant">نظام إدارة الكلية</div>' +
      '</div></div>' +
      '<div class="flex items-center gap-4">' +
      '<div class="text-left">' +
      '<div class="text-sm font-bold text-on-surface">' + escapeHtml(user.label || user.username) + '</div>' +
      '<div class="text-xs text-on-surface-variant">' + escapeHtml(SESSION.role_label || '') + '</div>' +
      '</div>' +
      '<button type="button" id="spa-theme-toggle" class="spa-icon-btn" title="تبديل المظهر">' +
      '<span class="material-symbols-outlined" id="spa-theme-icon">dark_mode</span></button>' +
      '<a href="/logout" class="inline-flex items-center gap-1.5 text-sm font-bold text-error hover:opacity-80 no-underline">' +
      '<span class="material-symbols-outlined text-lg">logout</span> خروج</a>' +
      '</div></div>' +
      '</header>' +
      '<div class="flex">' +
      '<aside id="app-sidebar" class="w-64 bg-white border-l border-outline-variant min-h-[calc(100vh-64px)] sticky top-[64px] hidden lg:block">' +
      '<div class="p-3 border-b border-outline-variant">' +
      '<div class="flex items-center gap-3 px-2 py-2">' +
      '<div class="w-9 h-9 rounded-full bg-primary flex items-center justify-center text-on-primary font-bold text-sm">' +
      escapeHtml((user.label || user.username || '').substring(0, 1)) + '</div>' +
      '<div class="overflow-hidden">' +
      '<div class="text-sm font-bold text-on-surface truncate">' + escapeHtml(user.label || user.username) + '</div>' +
      '<div class="text-xs text-on-surface-variant">' + escapeHtml(SESSION.role_label || '') + '</div>' +
      '</div></div></div>' +
      '<nav class="p-2" id="spa-nav"></nav>' +
      '</aside>' +
      '<main id="app-content" class="flex-1 max-w-7xl mx-auto px-4 py-6 min-h-[calc(100vh-64px)]"></main>' +
      '</div>';

    initTheme();
    renderNav();
    window.addEventListener('hashchange', handleRoute);
    handleRoute();
  }

  /* ---------------------------------------------------------------- nav */
  function renderNav() {
    var nav = document.getElementById('spa-nav');
    if (!nav) return;
    var items = SESSION.nav_items || [];
    var key = currentView();
    var html = items.map(function (item) {
      var isActive = key === item.key;
      var activeClass = isActive
        ? 'bg-primary/10 text-primary border-r-[3px] border-primary font-bold'
        : 'text-on-surface-variant hover:bg-surface-hover border-r-[3px] border-transparent';
      return '<a href="#/' + item.key + '" class="flex items-center gap-3 px-3 py-2.5 text-sm rounded-lg no-underline transition-colors ' + activeClass + '">' +
        '<span class="material-symbols-outlined text-xl">' + escapeHtml(item.icon) + '</span>' +
        '<span class="truncate">' + escapeHtml(item.label) + '</span></a>';
    }).join('');

    html += '<div class="mt-4 pt-4 border-t border-outline-variant px-3">' +
      '<a href="/logout" class="flex items-center gap-3 px-3 py-2.5 text-sm rounded-lg text-error hover:bg-red-50 no-underline">' +
      '<span class="material-symbols-outlined text-xl">logout</span><span>تسجيل الخروج</span></a></div>';

    nav.innerHTML = html;
  }

  function currentView() {
    return window.location.hash.replace(/^#\//, '') || 'dashboard';
  }

  /* ---------------------------------------------------------------- route */
  function handleRoute() {
    var viewEl = document.getElementById('app-content');
    if (!viewEl) return;
    var key = currentView();

    renderNav();

    var viewFn = window.SPA.VIEWS[key];
    if (viewFn) {
      viewFn(viewEl);
      return;
    }

    var fetcher = CONTENT_FETCHER_ROUTES[key];
    if (fetcher) {
      fetcher(viewEl);
      return;
    }

    var item = findNavItem(key);
    if (item && item.url) {
      fetchHTMLContent(item.url, viewEl);
      return;
    }

    viewEl.innerHTML = '<div class="flex items-center justify-center min-h-[50vh]">' +
      '<div class="text-center">' +
      '<span class="material-symbols-outlined text-6xl text-on-surface-variant/30">construction</span>' +
      '<p class="mt-4 text-lg font-bold text-on-surface-variant">هذه الواجهة قيد الإنشاء</p>' +
      '<p class="text-sm text-on-surface-variant mt-1">سيتم إضافتها قريباً</p></div></div>';
  }

  function findNavItem(key) {
    var items = SESSION.nav_items || [];
    for (var i = 0; i < items.length; i++) {
      if (items[i].key === key) return items[i];
    }
    return null;
  }

  /* -------------------------------------------------- HTML content fetcher */
  function fetchHTMLContent(url, container) {
    container.innerHTML = '<div class="flex items-center justify-center py-20">' +
      '<div class="text-on-surface-variant text-sm flex items-center gap-2">' +
      '<span class="material-symbols-outlined text-xl animate-spin">progress_activity</span>' +
      'جاري التحميل…</div></div>';

    fetch(url, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.text();
    }).then(function (html) {
      var parser = new DOMParser();
      var doc = parser.parseFromString(html, 'text/html');
      var content = doc.querySelector('#mainContent') || doc.querySelector('.main-content') || doc.querySelector('main');
      if (content) {
        container.innerHTML = content.innerHTML;
        interceptLinks(container);
        interceptForms(container);
        executeScripts(container);
      } else {
        container.innerHTML = html;
        interceptLinks(container);
        interceptForms(container);
        executeScripts(container);
      }
    }).catch(function (err) {
      container.innerHTML = '<div class="text-center py-20">' +
        '<span class="material-symbols-outlined text-5xl text-error/50">error</span>' +
        '<p class="mt-3 font-bold text-error">' + escapeHtml(err.message) + '</p>' +
        '<button onclick="location.reload()" class="mt-3 px-4 py-2 bg-primary text-on-primary rounded-lg text-sm font-bold">إعادة المحاولة</button></div>';
    });
  }

  function interceptLinks(container) {
    container.querySelectorAll('a[href]').forEach(function (a) {
      var href = a.getAttribute('href');
      if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('http')) return;
      if (a.target === '_blank') return;
      a.addEventListener('click', function (e) {
        e.preventDefault();
        fetchHTMLContent(href, container);
      });
    });
  }

  function interceptForms(container) {
    container.querySelectorAll('form').forEach(function (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var method = (form.method || 'POST').toUpperCase();
        var action = form.getAttribute('action') || window.location.pathname;
        var formData = new FormData(form);
        var isJSON = form.enctype === 'application/json';

        var fetchOpts = {
          method: method,
          credentials: 'same-origin',
          headers: {}
        };

        var csrfMeta = document.querySelector('meta[name="csrf-token"]');
        var csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
        if (csrfToken) {
          fetchOpts.headers['X-CSRFToken'] = csrfToken;
        }

        if (isJSON) {
          var data = {};
          formData.forEach(function (v, k) { data[k] = v; });
          fetchOpts.headers['Content-Type'] = 'application/json';
          fetchOpts.body = JSON.stringify(data);
        } else {
          fetchOpts.body = formData;
        }

        fetchOpts.headers['X-Requested-With'] = 'XMLHttpRequest';

        fetch(action, fetchOpts).then(function (res) {
          if (res.headers.get('content-type') && res.headers.get('content-type').indexOf('json') !== -1) {
            return res.json().then(function (json) {
              if (json.redirect) {
                fetchHTMLContent(json.redirect, container);
              } else if (json.ok === false) {
                showToast(json.message || 'حدث خطأ', 'error');
              } else {
                window.location.reload();
              }
            });
          }
          return res.text().then(function (html) {
            container.innerHTML = html;
            interceptLinks(container);
            interceptForms(container);
            executeScripts(container);
          });
        }).catch(function (err) {
          showToast(err.message || 'حدث خطأ', 'error');
        });
      });
    });
  }

  function executeScripts(container) {
    var scripts = container.querySelectorAll('script');
    scripts.forEach(function (old) {
      var s = document.createElement('script');
      s.textContent = old.textContent;
      old.parentNode.replaceChild(s, old);
    });
  }

  /* ------------------------------------------------------------- theme */
  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem('ropely-theme'); } catch (e) {}
    var dark = saved === 'dark';
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    var icon = document.getElementById('spa-theme-icon');
    if (icon) icon.textContent = dark ? 'light_mode' : 'dark_mode';
    var btn = document.getElementById('spa-theme-toggle');
    if (btn) {
      btn.addEventListener('click', function () {
        var current = document.documentElement.getAttribute('data-theme');
        var next = current === 'dark' ? 'light' : 'dark';
        try { localStorage.setItem('ropely-theme', next); } catch (e) {}
        document.documentElement.setAttribute('data-theme', next);
        var ic = document.getElementById('spa-theme-icon');
        if (ic) ic.textContent = next === 'dark' ? 'light_mode' : 'dark_mode';
      });
    }
  }

  /* ------------------------------------------------------------- toast */
  function showToast(message, type) {
    var container = document.getElementById('spa-toast-root');
    if (!container) {
      container = document.createElement('div');
      container.id = 'spa-toast-root';
      container.className = 'fixed top-4 left-1/2 -translate-x-1/2 z-[70] space-y-2';
      document.body.appendChild(container);
    }
    var icon = type === 'success' ? 'check_circle' : (type === 'error' ? 'error' : (type === 'warning' ? 'warning' : 'info'));
    var color = type === 'success' ? 'bg-emerald-600' : (type === 'error' ? 'bg-rose-600' : (type === 'warning' ? 'bg-amber-600' : 'bg-slate-700'));
    var toast = document.createElement('div');
    toast.className = 'flex items-center gap-2 text-white text-sm font-bold px-4 py-2.5 rounded-lg shadow-lg ' + color;
    toast.innerHTML = '<span class="material-symbols-outlined text-lg">' + icon + '</span><span>' + escapeHtml(message) + '</span>';
    container.appendChild(toast);
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 3500);
  }

  window.showToastSuccess = function (msg) { showToast(msg, 'success'); };
  window.showToastError = function (msg) { showToast(msg, 'error'); };
  window.showToastInfo = function (msg) { showToast(msg, 'info'); };

  window.SPA.fetchHTML = fetchHTMLContent;
  window.SPA.showToast = showToast;

  document.addEventListener('DOMContentLoaded', bootstrap);
})();
