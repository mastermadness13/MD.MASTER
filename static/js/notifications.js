/**
 * Notifications Module
 * Handles notification dropdown, badge count, and real-time updates.
 */
(function () {
  'use strict';

  var notifBadge = document.getElementById('notifBadge');
  var notifList = document.getElementById('notifList');
  var markAllBtn = document.getElementById('markAllRead');

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
    fetch('/api/notifications')
      .then(function (r) { return r.json(); })
      .then(function (data) {
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
    if (!notifBadge) return;
    if (unreadCount > 0) {
      var increased = lastUnread >= 0 && unreadCount > lastUnread;
      notifBadge.textContent = unreadCount > 99 ? '99+' : unreadCount;
      notifBadge.style.display = 'flex';
      if (increased) {
        notifBadge.classList.remove('notif-badge-pop');
        void notifBadge.offsetWidth;
        notifBadge.classList.add('notif-badge-pop');
      }
    } else {
      notifBadge.style.display = 'none';
    }
    lastUnread = unreadCount;
  }

  function markAllRead() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    var token = meta ? meta.getAttribute('content') : '';
    fetch('/api/notifications/read', {
      method: 'POST',
      headers: { 'X-CSRFToken': token }
    })
      .then(function () {
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

  if (markAllBtn) {
    markAllBtn.addEventListener('click', markAllRead);
  }

  window.__notifications = {
    fetch: fetchNotifications,
    render: renderNotifications,
    markAllRead: markAllRead
  };
})();
