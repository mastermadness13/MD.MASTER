
var BOOT = window.ACADEMIC_CALENDAR_INDEX_BOOT || {};
var URLS = BOOT.urls || {};

function openCreateModal() {
  document.getElementById('createModal').style.display = 'block';
}
function closeCreateModal() {
  document.getElementById('createModal').style.display = 'none';
}
function openEditModal(id, startDate, endDate, examStart, examEnd, title) {
  document.getElementById('editForm').action = URLS.edit.replace('/0', '/' + id);
  document.getElementById('edit_start_date').value = startDate;
  document.getElementById('edit_end_date').value = endDate;
  document.getElementById('edit_exam_start_date').value = examStart;
  document.getElementById('edit_exam_end_date').value = examEnd;
  document.getElementById('editModalTitle').textContent = 'تعديل التواريخ: ' + title;
  document.getElementById('editModal').style.display = 'block';
}
function closeEditModal() {
  document.getElementById('editModal').style.display = 'none';
}
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') { closeEditModal(); closeCreateModal(); }
});
function togglePastSemesters() {
  var list = document.getElementById('pastSemestersList');
  var icon = document.getElementById('togglePastIcon');
  list.classList.toggle('hidden');
  icon.textContent = list.classList.contains('hidden') ? 'expand_more' : 'expand_less';
}
