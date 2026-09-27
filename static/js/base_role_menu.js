
  function toggleRoleMenu() {
    var menu = document.getElementById('roleMenu');
    if (!menu) return;
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
  }
  document.addEventListener('click', function (e) {
    var sw = document.getElementById('roleSwitcher');
    var menu = document.getElementById('roleMenu');
    if (sw && menu && menu.style.display === 'block' && !sw.contains(e.target)) {
      menu.style.display = 'none';
    }
  });

  function setUserMenuOpen(open) {
    var menu = document.getElementById('userMenu');
    var button = document.getElementById('userMenuBtn');
    if (!menu || !button) return;
    menu.style.display = open ? 'block' : 'none';
    button.setAttribute('aria-expanded', String(open));
  }

  window.toggleUserMenu = function () {
    var menu = document.getElementById('userMenu');
    if (!menu) return;
    setUserMenuOpen(menu.style.display === 'none');
  };

  window.closeUserMenu = function () {
    setUserMenuOpen(false);
  };

  document.addEventListener('click', function (e) {
    var wrapper = document.getElementById('userMenuDropdown');
    var menu = document.getElementById('userMenu');
    if (wrapper && menu && menu.style.display === 'block' && !wrapper.contains(e.target)) {
      setUserMenuOpen(false);
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var menu = document.getElementById('userMenu');
    if (!menu || menu.style.display !== 'block') return;
    setUserMenuOpen(false);
    var button = document.getElementById('userMenuBtn');
    if (button) button.focus();
  });

  var ROLE_SWITCH_LOADING_LABEL = window.ROLE_SWITCH_LABEL || 'جاري التبديل...';

  function setRoleSwitchLoading(btn, loading) {
    var label = btn.querySelector('.role-switch-label');
    var icon = btn.querySelector('.role-switch-spinner');
    if (loading) {
      btn.setAttribute('data-submitting', '1');
      btn.disabled = true;
      if (icon) icon.style.display = 'inline-block';
      if (label) label.textContent = ROLE_SWITCH_LOADING_LABEL;
    } else {
      btn.removeAttribute('data-submitting');
      btn.disabled = false;
      if (icon) icon.style.display = 'none';
    }
  }

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!(form instanceof HTMLFormElement) || form.getAttribute('data-role-switch') !== '1') return;
    if (form.getAttribute('data-submitting') === '1') {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    var btn = document.getElementById('roleSwitchBtn');
    if (btn) setRoleSwitchLoading(btn, true);

    fetch(form.action, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json'
      },
      body: new FormData(form),
      credentials: 'same-origin'
    }).then(function (resp) {
      return resp.json().then(function (data) {
        return { status: resp.status, data: data };
      });
    }).then(function (res) {
      if (res.data && res.data.ok) {
        var loading = document.getElementById('roleSwitchLoading');
        if (loading) {
          loading.classList.remove('hidden');
          loading.classList.add('flex');
        }
        var redirectUrl = res.data.redirect_url;
        if (redirectUrl) {
          window.location.assign(redirectUrl);
        } else {
          window.location.reload();
        }
        return;
      }
      if (btn) setRoleSwitchLoading(btn, false);
      var msg = (res.data && res.data.message) || 'فشل تغيير الواجهة';
      if (window.showToastError) window.showToastError(msg);
      else alert(msg);
    }).catch(function () {
      if (btn) setRoleSwitchLoading(btn, false);
      if (window.showToastError) window.showToastError('تعذر الاتصال بالخادم، حاول مجدداً');
    });
  });
