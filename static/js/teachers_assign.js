var BOOT = window.TEACHERS_ASSIGN_BOOT || {};
var URLS = BOOT.urls || {};
var CSRF = BOOT.csrfToken || '';
/* Teacher names and academic numbers come from GET /teachers/api/teacher-pool
 * and are only .strip()'d on the way into the database, so they must be
 * escaped before they are concatenated into markup. */
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
// ── Assign Teacher Side Drawer ──
var assignDebounce = null;
function openAssignDrawer() {
  var d = document.getElementById('assignDrawer');
  if (!d) return;
  d.classList.remove('hidden');
  requestAnimationFrame(function() {
    var overlay = document.getElementById('assignOverlay');
    var panel = document.getElementById('assignPanel');
    if (overlay) overlay.style.opacity = '1';
    if (panel) panel.style.transform = 'translateX(0)';
  });
  setTimeout(function() {
    var inp = document.getElementById('assignSearchInput');
    if (inp) inp.focus();
  }, 350);
}
function closeAssignDrawer() {
  var d = document.getElementById('assignDrawer');
  if (!d) return;
  var overlay = document.getElementById('assignOverlay');
  var panel = document.getElementById('assignPanel');
  if (overlay) overlay.style.opacity = '0';
  if (panel) panel.style.transform = 'translateX(100%)';
  setTimeout(function() { d.classList.add('hidden'); }, 300);
}
function currentDeptId() {
  var sel = document.getElementById('assignDeptSelect');
  return sel ? sel.value : (BOOT.defaultDept || '');
}
function searchPool(q) {
  var results = document.getElementById('assignResults');
  if (!results) return;
  if (!q || q.length < 2) { results.innerHTML = '<p class="text-sm text-on-surface-variant text-center py-12">اكتب للبحث...</p>'; return; }
  var deptId = currentDeptId();
  if (!deptId) { results.innerHTML = '<p class="text-sm text-on-surface-variant text-center py-12">حدد القسم المستهدف أولاً...</p>'; return; }
  results.innerHTML = '<p class="text-sm text-on-surface-variant text-center py-8">جاري البحث...</p>';
  fetch(URLS.pool + '?search=' + encodeURIComponent(q) + '&dept_id=' + encodeURIComponent(deptId), {
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  }).then(function(r){ return r.json(); }).then(function(data) {
    if (!data.length) { results.innerHTML = '<p class="text-sm text-on-surface-variant text-center py-12">لا يوجد أساتذة متاحين</p>'; return; }
    var html = '';
    data.forEach(function(t) {
      html += '<div class="flex items-center justify-between gap-3 py-3 px-1">';
      html += '<div class="flex items-center gap-3 min-w-0">';
      html += '<span class="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-sm shrink-0">' + esc(t.name ? t.name.charAt(0) : '?') + '</span>';
      html += '<div class="min-w-0"><p class="font-bold text-on-surface text-sm truncate">' + esc(t.name) + '</p>';
      html += '<p class="text-xs text-on-surface-variant" dir="ltr">' + esc(t.academic_number || '') + '</p></div></div>';
      html += '<form method="post" action="' + URLS.assign + '" style="display:inline">';
      html += '<input type="hidden" name="_csrf_token" value="' + (CSRF || '') + '">';
      html += '<input type="hidden" name="teacher_id" value="' + t.id + '">';
      html += '<input type="hidden" name="department_id" value="' + deptId + '">';
      html += '<button type="submit" class="shrink-0 px-3 py-1.5 rounded-lg bg-primary text-on-primary text-xs font-bold hover:bg-primary/90 transition">إضافة</button>';
      html += '</form></div>';
    });
    results.innerHTML = html;
  }).catch(function() {
    results.innerHTML = '<p class="text-sm text-red-600 text-center py-8">حدث خطأ أثناء البحث</p>';
  });
}
document.addEventListener('DOMContentLoaded', function() {
  var inp = document.getElementById('assignSearchInput');
  if (!inp) return;
  inp.addEventListener('input', function() {
    clearTimeout(assignDebounce);
    assignDebounce = setTimeout(function() { searchPool(inp.value.trim()); }, 300);
  });
  var sel = document.getElementById('assignDeptSelect');
  if (sel) {
    sel.addEventListener('change', function() {
      if (inp.value.trim().length >= 2) {
        clearTimeout(assignDebounce);
        assignDebounce = setTimeout(function() { searchPool(inp.value.trim()); }, 200);
      }
    });
  }
});
