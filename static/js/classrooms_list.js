var BOOT = window.CLASSROOMS_LIST_BOOT || {};
var CSRF = BOOT.csrfToken || '';

SearchComponent.init({
  formSelector: '#roomsSearchForm',
  inputSelector: '.search-input',
  tableSelector: '.search-table',
  countSelector: '.search-results-count',
  clearSelector: '.search-clear',
  spinnerSelector: '.search-spinner',
  paginationSelector: '.search-pagination',
  debounceMs: 300,
  onComplete: function () { if (typeof window.syncRoomBulk === 'function') window.syncRoomBulk(); },
});

if (BOOT.canManage) {
// ===== Bulk select + delete (beside select-all) =====
var roomDeleteForm = document.getElementById('bulkDeleteForm');

function syncRoomBulk() {
  var cbs = Array.prototype.slice.call(document.querySelectorAll('.room-select'));
  var selected = cbs.filter(function (cb) { return cb.checked; }).length;
  var selectAll = document.getElementById('roomSelectAll');
  var deleteBtn = document.getElementById('roomHeaderDeleteBtn');
  if (deleteBtn) deleteBtn.style.display = selected > 0 ? 'inline-flex' : 'none';
  if (selectAll) {
    selectAll.checked = cbs.length > 0 && selected === cbs.length;
    selectAll.indeterminate = selected > 0 && selected < cbs.length;
  }
  if (roomDeleteForm) {
    roomDeleteForm.innerHTML = '<input type="hidden" name="_csrf_token" value="' + CSRF + '">';
    cbs.forEach(function (cb) {
      if (cb.checked) {
        var inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'room_ids';
        inp.value = cb.value;
        roomDeleteForm.appendChild(inp);
      }
    });
  }
}

function onRoomCheck() { syncRoomBulk(); }

function toggleRoomSelectAll() {
  var selectAll = document.getElementById('roomSelectAll');
  document.querySelectorAll('.room-select').forEach(function (c) { c.checked = selectAll.checked; });
  syncRoomBulk();
}

var roomSelectAllEl = document.getElementById('roomSelectAll');
if (roomSelectAllEl) {
  roomSelectAllEl.addEventListener('change', toggleRoomSelectAll);
}

var roomHeaderDeleteBtn = document.getElementById('roomHeaderDeleteBtn');
if (roomHeaderDeleteBtn) {
  roomHeaderDeleteBtn.addEventListener('click', function () {
    var selected = document.querySelectorAll('.room-select:checked').length;
    if (!selected) return;
    if (!confirm('تأكيد حذف القاعات المحددة؟')) return;
    if (roomDeleteForm) roomDeleteForm.submit();
  });
}

document.addEventListener('change', function (e) {
  var t = e.target;
  if (t && t.classList && t.classList.contains('room-select')) { onRoomCheck(); }
});
window.onRoomCheck = onRoomCheck;
window.toggleRoomSelectAll = toggleRoomSelectAll;
window.syncRoomBulk = syncRoomBulk;
}

function openRoomModal(kind) {
  document.getElementById('roomModalOverlay').classList.remove('hidden');
  document.getElementById('roomModal').classList.remove('hidden');
  var title = document.getElementById('roomModalTitle');
  if (title && !kind) title.textContent = 'إضافة قاعة / معمل';
  if (kind) {
    var typeSel = document.getElementById('room_type_id');
    var want = kind === 'lab' ? 'معمل' : 'قاعة';
    if (title) title.textContent = kind === 'lab' ? 'إضافة معمل' : 'إضافة قاعة';
    if (typeSel) {
      for (var i = 0; i < typeSel.options.length; i++) {
        var opt = typeSel.options[i];
        if (opt.text.indexOf(want) !== -1 && !(kind === 'hall' && opt.text.indexOf('معمل') !== -1)) {
          typeSel.selectedIndex = i;
          break;
        }
      }
    }
  }
  document.getElementById('name').focus();
}
function closeRoomModal() {
  document.getElementById('roomModalOverlay').classList.add('hidden');
  document.getElementById('roomModal').classList.add('hidden');
}

if (BOOT.autoOpen) {
openRoomModal();
}
