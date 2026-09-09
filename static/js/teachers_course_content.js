
(function () {
  var BOOT = window.TEACHERS_COURSE_CONTENT_BOOT || {};
  var URLS = BOOT.urls || {};
  var overlay = document.getElementById('uploadModalOverlay');
  var form = document.getElementById('uploadForm');
  var fileInput = document.getElementById('uploadFileInput');
  var courseId = document.getElementById('uploadCourseId');
  var submissionId = document.getElementById('uploadSubmissionId');
  var nameEl = document.getElementById('uploadCourseName');
  var codeEl = document.getElementById('uploadCourseCode');
  var metaEl = document.getElementById('uploadCourseMeta');
  var fileRow = document.getElementById('uploadFileName');
  var dropZone = document.getElementById('uploadDropZone');
  var dropText = document.getElementById('uploadDropText');
  var dropIcon = document.getElementById('uploadDropIcon');
  var MAX_MB = 16;

  window.closeUploadModal = function () {
    if (!overlay) return;
    overlay.style.display = 'none';
    overlay.classList.add('hidden');
    form.reset();
  };

  window.openUploadModal = function (btn) {
    courseId.value = btn.getAttribute('data-course-id') || '';
    submissionId.value = btn.getAttribute('data-submission-id') || '';
    nameEl.textContent = btn.getAttribute('data-course-name') || '—';
    var meta = [];
    var dept = btn.getAttribute('data-dept');
    var sem = btn.getAttribute('data-semester');
    if (dept) meta.push(dept);
    if (sem) meta.push(sem);
    codeEl.textContent = btn.getAttribute('data-course-code') || '';
    metaEl.textContent = meta.length ? ' · ' + meta.join(' · ') : '';
    if (btn.getAttribute('data-mode') === 'form') {
      form.action = URLS.courseContent;
    } else {
      form.action = URLS.syllabusUpload;
    }
    fileInput.value = '';
    fileRow.classList.add('hidden');
    dropText.textContent = 'اختر ملف PDF';
    dropIcon.textContent = 'picture_as_pdf';
    overlay.classList.remove('hidden');
    overlay.style.display = 'flex';
  };

  document.querySelectorAll('[data-open-upload]').forEach(function (btn) {
    btn.addEventListener('click', function () { window.openUploadModal(btn); });
  });

  function showFile() {
    var f = fileInput.files && fileInput.files[0];
    if (!f) return;
    var label = dropZone ? dropZone.querySelector('input') : null;
    fileRow.classList.remove('hidden');
    fileRow.querySelector('span.truncate').textContent = f.name;
    dropText.textContent = f.name;
    dropIcon.textContent = 'description';
  }

  if (fileInput) fileInput.addEventListener('change', showFile);

  if (dropZone && fileInput) {
    dropZone.addEventListener('dragover', function (e) {
      e.preventDefault();
      dropZone.classList.add('border-primary/50', 'bg-primary/5');
    });
    dropZone.addEventListener('dragleave', function () {
      dropZone.classList.remove('border-primary/50', 'bg-primary/5');
    });
    dropZone.addEventListener('drop', function (e) {
      e.preventDefault();
      dropZone.classList.remove('border-primary/50', 'bg-primary/5');
      if (e.dataTransfer.files && e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        showFile();
      }
    });
  }

  if (form) {
    form.addEventListener('submit', function (e) {
      var f = fileInput.files && fileInput.files[0];
      if (!f) {
        e.preventDefault();
        alert('يرجى اختيار ملف PDF أولاً');
        return;
      }
      if (!(/\.pdf$/i.test(f.name))) {
        e.preventDefault();
        alert('يجب أن يكون الملف بصيغة PDF');
        return;
      }
      if (f.size > MAX_MB * 1024 * 1024) {
        e.preventDefault();
        alert('حجم الملف أكبر من ' + MAX_MB + ' ميجابايت');
        return;
      }
    });
  }
})();
