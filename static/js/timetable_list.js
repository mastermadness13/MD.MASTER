(function () {
  var BOOT = window.TIMETABLE_LIST_BOOT || {};
  var URLS = BOOT.urls || {};
    function buildQuery(extra) {
      var params = new URLSearchParams(location.search);
      for (var k in extra) {
        if (extra[k] === '' || extra[k] === null) params.delete(k);
        else params.set(k, extra[k]);
      }
      return params.toString();
    }
  
    var dept = document.getElementById('deptFilter');
    if (dept) {
      dept.addEventListener('change', function () {
        location.search = buildQuery({ department: dept.value, semester: '', section: '' });
      });
    }
    var sem = document.getElementById('semesterFilter');
    if (sem) {
      sem.addEventListener('change', function () {
        location.search = buildQuery({ semester: sem.value });
      });
    }
    var sec = document.getElementById('sectionFilter');
    if (sec) {
      sec.addEventListener('change', function () {
        location.search = buildQuery({ section: sec.value });
      });
    }
  
window.deleteEntry = function (id, name) {
  if (!confirm('هل تريد حذف حصة "' + name + '" من الجدول؟')) return;
  fetch(URLS.deleteEntry, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
    },
    body: JSON.stringify({ lecture_id: id })
  }).then(function (r) { return r.json(); }).then(function (d) {
    alert(d.message || 'تمت العملية');
    if (d.ok) location.reload();
  }).catch(function () { alert('حدث خطأ أثناء الحذف'); });
};

})();
