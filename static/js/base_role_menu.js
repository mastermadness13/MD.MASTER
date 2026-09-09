
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
