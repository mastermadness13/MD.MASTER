SearchComponent.init({
  formSelector: '#classroomRequestsSearchForm',
  inputSelector: '.search-input',
  tableSelector: '.search-table',
  countSelector: '.search-results-count',
  clearSelector: '.search-clear',
  spinnerSelector: '.search-spinner',
  paginationSelector: '.search-pagination',
  debounceMs: 300,
});

window.reqComment = function (event, action) {
  var msg = action === 'approve' ? 'إضافة ملاحظة للموافقة؟' : 'إضافة سبب الرفض؟';
  var comment = prompt(msg, '');
  if (comment === null) return false;
  var form = event.target.closest('form');
  var input = document.createElement('input');
  input.type = 'hidden';
  input.name = 'hod_comment';
  input.value = comment;
  form.appendChild(input);
  return true;
};
