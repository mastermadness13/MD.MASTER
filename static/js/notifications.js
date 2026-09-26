/**
 * Notifications Module
 * Handles notification dropdown, badge count, and real-time updates.
 */
(function () {
  'use strict';

  var notifBadge = document.getElementById('notifBadge');
  var notifList = document.getElementById('notifList');
  var markAllBtn = document.getElementById('markAllRead');
  var bellBtn = document.getElementById('notifBellBtn');
  var dropdown = bellBtn ? bellBtn.closest('.notif-dropdown') : null;

  var notifications = [];
  var unreadCount = 0;

  var TYPE_ICONS = {
    success: 'check_circle',
    warning: 'warning',
    error: 'error',
    info: 'info',
    schedule: 'calendar_today',
    grades: 'school',
    exams: 'quiz',
    files: 'attach_file',
    attendance: 'fact_check'
  };

  var TYPE_COLORS = {
    success: '#16a34a',
    warning: '#ca8a04',
    error: '#dc2626',
    info: '#320058',
    schedule: '#2563eb',
    grades: '#7d3fb5',
    exams: '#ea580c',
    files: '#0891b2',
    attendance: '#059669'
  };

  function fetchNotifications() {
    fetch('/api/notifications', { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (body) {
        /* The API wraps every payload in {ok, data}; the unwrapped shape is
           under .data. Reading the top level silently yields no notifications. */
        if (!body || !body.ok) return;
        var data = body.data || {};
        notifications = data.notifications || [];
        unreadCount = data.unread_count || 0;
        renderNotifications();
        updateBadge();
      })
      .catch(function () {});
  }

  function renderNotifications() {
    if (!notifList) return;

    if (notifications.length === 0) {
      notifList.innerHTML = '<div class="notif-empty">لا توجد إشعارات</div>';
      return;
    }

    var html = '';
    var shown = notifications.slice(0, 10);
    shown.forEach(function (n) {
      var icon = TYPE_ICONS[n.type] || 'info';
      var color = TYPE_COLORS[n.type] || '#320058';
      var unreadClass = n.is_read ? '' : ' notif-unread';
      var time = n.created_at || '';
      if (time.length > 16) time = time.substring(0, 16);

      html += '<div class="notif-item' + unreadClass + '">' +
        '<div class="notif-item-icon" style="color:' + color + '">' +
          '<span class="material-symbols-outlined">' + icon + '</span>' +
        '</div>' +
        '<div class="notif-item-body">' +
          '<div class="notif-item-text">' + escapeHtml(n.title || n.message) + '</div>' +
          (n.message && n.title ? '<div class="notif-item-sub">' + escapeHtml(n.message) + '</div>' : '') +
          '<div class="notif-item-time">' + escapeHtml(time) + '</div>' +
        '</div>' +
        '</div>';
    });
    notifList.innerHTML = html;
  }

  var lastUnread = -1;

  function updateBadge() {
    if (notifBadge) {
      if (unreadCount > 0) {
        var increased = lastUnread >= 0 && unreadCount > lastUnread;
        notifBadge.textContent = unreadCount > 99 ? '99+' : unreadCount;
        notifBadge.style.display = 'flex';
        notifBadge.setAttribute('aria-hidden', 'true');
        if (increased) {
          notifBadge.classList.remove('notif-badge-pop');
          void notifBadge.offsetWidth;
          notifBadge.classList.add('notif-badge-pop');
        }
      } else {
        notifBadge.style.display = 'none';
      }
    }
    /* The badge itself is aria-hidden (a bare number is meaningless), so the
       count has to reach assistive tech through the button's accessible name. */
    if (bellBtn) {
      bellBtn.setAttribute(
        'aria-label',
        unreadCount > 0
          ? 'الإشعارات، ' + unreadCount + ' إشعار غير مقروء'
          : 'الإشعارات'
      );
    }
    lastUnread = unreadCount;
  }

  function markAllRead() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    var token = meta ? meta.getAttribute('content') : '';
    fetch('/api/notifications/read', {
      method: 'POST',
      headers: {
        'X-CSRFToken': token,
        /* Required: without an Accept of application/json the CSRF failure
           path answers with a 302 redirect to the dashboard instead of a 403
           JSON body, and fetch would follow it and report success. */
        'Accept': 'application/json'
      }
    })
      .then(function (r) { return r.json(); })
      .then(function (body) {
        /* Only clear the UI once the server has actually confirmed. */
        if (!body || !body.ok) return;
        notifications.forEach(function (n) { n.is_read = 1; });
        unreadCount = 0;
        renderNotifications();
        updateBadge();
      })
      .catch(function () {});
  }

  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  if (notifList) {
    fetchNotifications();
    setInterval(fetchNotifications, 30000);
  }

  /* The stylesheet already reveals the menu on :hover and :focus-within.
     This adds the click/touch path and keeps aria-expanded honest. */
  function setOpen(open) {
    if (!dropdown || !bellBtn) return;
    dropdown.classList.toggle('open', open);
    bellBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  if (bellBtn && dropdown) {
    bellBtn.addEventListener('click', function (event) {
      event.stopPropagation();
      setOpen(!dropdown.classList.contains('open'));
    });

    document.addEventListener('click', function (event) {
      if (dropdown.classList.contains('open') && !dropdown.contains(event.target)) {
        setOpen(false);
      }
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && dropdown.classList.contains('open')) {
        setOpen(false);
        bellBtn.focus();
      }
    });

    /* Following a notification link should not leave the menu stuck open. */
    if (notifList) {
      notifList.addEventListener('click', function (event) {
        if (event.target.closest('a')) setOpen(false);
      });
    }
  }

  if (markAllBtn) {
    markAllBtn.addEventListener('click', markAllRead);
  }

  window.__notifications = {
    fetch: fetchNotifications,
    render: renderNotifications,
    markAllRead: markAllRead
  };
})();
