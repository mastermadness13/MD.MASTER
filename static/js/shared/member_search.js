/**
 * Filters .member-item elements by a search input and updates a counter.
 * Used by faculty performance leaves_index and member_reports pages.
 */
(function () {
  'use strict';
  var input = document.getElementById('memberSearch');
  if (!input) return;
  var counter = document.getElementById('memberCount');
  var items = Array.prototype.slice.call(document.querySelectorAll('.member-item'));
  input.addEventListener('input', function () {
    var q = input.value.trim().toLowerCase();
    var visible = 0;
    items.forEach(function (li) {
      var hit = !q || (li.getAttribute('data-search') || '').toLowerCase().indexOf(q) !== -1;
      li.classList.toggle('hidden', !hit);
      if (hit) visible++;
    });
    if (counter) counter.textContent = visible + ' عضو';
  });
})();
