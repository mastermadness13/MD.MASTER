
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
        window.location.reload();
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
