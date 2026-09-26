(function () {
  var WEEKS_LIMIT = 12;
  var SECTIONS = [
    {
      prefix: 'theoretical',
      bodyId: 'ccTheoreticalCurriculumBody',
      totalId: 'ccTheoreticalWeeksTotal',
      addId: 'ccAddTheoreticalRow',
      limit: WEEKS_LIMIT
    },
    {
      prefix: 'practical',
      bodyId: 'ccPracticalCurriculumBody',
      totalId: 'ccPracticalWeeksTotal',
      addId: 'ccAddPracticalRow',
      limit: WEEKS_LIMIT
    }
  ];
  var SEMESTER_EN = {
    '1': 'first', '2': 'second', '3': 'third', '4': 'fourth',
    '5': 'fifth', '6': 'sixth', '7': 'seventh', '8': 'eighth'
  };
  var sheet = document.querySelector('.cc-sheet');
  var form = document.getElementById('courseContentForm');
  var theoreticalWeeksTotal = 0;
  var practicalWeeksTotal = 0;
  var translationTimers = {};
  var translationJobs = {};
  var translationVersions = {};
  var pendingTranslations = {};
  var initialized = false;

  /* ── Textareas: grow with content so no character is ever hidden ── */
  function autoResize(element) {
    if (!element) return;
    var previous = element.style.height;
    element.style.height = 'auto';
    var measured = element.scrollHeight;
    if (!measured) {
      /* Element is hidden or not laid out yet: keep the height we had. */
      element.style.height = previous || '';
      return;
    }
    var height = Math.max(measured, 24);
    element.style.setProperty('--cc-auto-height', height + 'px');
    element.style.height = height + 'px';
  }

  function resizeAllTextareas() {
    if (!sheet) return;
    sheet.querySelectorAll('textarea').forEach(autoResize);
  }

  function scheduleResize() {
    window.setTimeout(resizeAllTextareas, 0);
  }

  /* Multi-page print: measure only, never force a one-page shrink. */
  function preparePrint() {
    if (!sheet) return;
    resizeAllTextareas();
    sheet.style.setProperty('--cc-print-zoom', '1');
  }

  /* ── Auto translation (AR source -> EN target) ── */
  function sourceTarget(source) {
    if (!source || !sheet) return null;
    var field = source.getAttribute('data-translation-source');
    if (!field) return null;
    var targetName = field + '_en';
    var row = source.closest('tr');
    if (row) {
      return row.querySelector('[data-translation-target="' + targetName + '"]');
    }
    return sheet.querySelector('[data-translation-target="' + targetName + '"]');
  }

  function translationKey(source) {
    var field = source.getAttribute('data-translation-source') || '';
    return field + ':' + (source.getAttribute('data-translation-row') || '');
  }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    var input = document.querySelector('input[name="_csrf_token"]');
    return input ? input.value : '';
  }

  function translationEnabled() {
    return !!(sheet && form && sheet.getAttribute('data-translation-editable') === 'true');
  }

  function scheduleTranslation(source) {
    if (!translationEnabled()) return;
    var target = sourceTarget(source);
    var key = translationKey(source);
    if (translationTimers[key]) {
      window.clearTimeout(translationTimers[key]);
      delete translationTimers[key];
      delete translationJobs[key];
    }
    var version = (translationVersions[key] || 0) + 1;
    translationVersions[key] = version;
    if (!target || target.getAttribute('data-translation-manual') === 'true') return;
    var text = (source.value || '').trim();
    if (!text) return;
    translationJobs[key] = {
      source: source,
      target: target,
      key: key,
      version: version
    };
    translationTimers[key] = window.setTimeout(function () {
      delete translationTimers[key];
      var job = translationJobs[key];
      delete translationJobs[key];
      if (job) translateSource(job.source, job.target, job.key, job.version);
    }, 700);
  }

  function translateSource(source, target, key, version) {
    var text = (source.value || '').trim();
    if (!text) return Promise.resolve();
    if (target.getAttribute('data-translation-manual') === 'true') return Promise.resolve();

    var url = sheet.getAttribute('data-translation-url');
    var token = csrfToken();
    var request = window.fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': token
      },
      body: JSON.stringify({
        field: source.getAttribute('data-translation-source'),
        text: text,
        row_index: source.getAttribute('data-translation-row')
          ? parseInt(source.getAttribute('data-translation-row'), 10)
          : null
      })
    }).then(function (response) {
      if (!response.ok) throw new Error('translation request failed');
      return response.json();
    }).then(function (payload) {
      if (!payload || payload.ok !== true || !payload.data) return;
      if (translationVersions[key] !== version) return;
      if (target.getAttribute('data-translation-manual') === 'true') return;
      var translated = payload.data.text;
      if (typeof translated !== 'string' || !translated) return;
      target.value = translated;
      target.setAttribute('data-translation-auto', 'true');
      autoResize(target);
    }).catch(function () {
      return undefined;
    });

    pendingTranslations[key] = request;
    request.then(function () {
      if (pendingTranslations[key] === request) delete pendingTranslations[key];
    });
    return request;
  }

  function startScheduledTranslations() {
    Object.keys(translationTimers).forEach(function (key) {
      window.clearTimeout(translationTimers[key]);
      delete translationTimers[key];
      var job = translationJobs[key];
      delete translationJobs[key];
      if (job) translateSource(job.source, job.target, job.key, job.version);
    });
  }

  function flushTranslations() {
    startScheduledTranslations();
    if (!Object.keys(pendingTranslations).length) return Promise.resolve();
    return Promise.all(Object.keys(pendingTranslations).map(function (key) {
      return pendingTranslations[key];
    })).catch(function () {
      return undefined;
    }).then(function () {
      if (Object.keys(translationTimers).length || Object.keys(pendingTranslations).length) {
        return flushTranslations();
      }
      return undefined;
    });
  }

  function markExistingEnglishManual() {
    if (!sheet) return;
    sheet.querySelectorAll('[data-translation-target]').forEach(function (target) {
      if (target.value && target.value.trim()) {
        target.setAttribute('data-translation-manual', 'true');
      }
    });
  }

  function scheduleInitialTranslations() {
    if (!translationEnabled() || !sheet) return;
    sheet.querySelectorAll('[data-translation-source]').forEach(function (source) {
      var target = sourceTarget(source);
      if (!target || target.value.trim()) return;
      if (target.getAttribute('data-translation-manual') === 'true') return;
      if ((source.value || '').trim()) scheduleTranslation(source);
    });
  }

  function initTranslation() {
    if (!translationEnabled() || !sheet) return;
    sheet.addEventListener('input', function (event) {
      var target = event.target;
      if (!target || !target.matches) return;
      if (target.matches('[data-translation-target]')) {
        target.setAttribute('data-translation-manual', 'true');
        target.removeAttribute('data-translation-auto');
        autoResize(target);
        return;
      }
      if (target.matches('[data-translation-source]')) {
        scheduleTranslation(target);
      }
    });
  }

  /* ── Curriculum rows (theoretical + practical) ── */
  function sectionBody(section) {
    return document.getElementById(section.bodyId);
  }

  function rowInputs(row, name) {
    return row.querySelector('[name$="_curriculum_' + name + '[]"]');
  }

  function createCurriculumRow(section, shouldFocus) {
    var body = sectionBody(section);
    if (!body) return null;
    var row = document.createElement('tr');
    row.innerHTML =
      '<td class="cc-block-cell cc-en">' +
        '<input type="hidden" name="' + section.prefix + '_curriculum_id[]" value="">' +
        '<textarea name="' + section.prefix + '_curriculum_topic_en[]" dir="ltr" rows="2" placeholder="Topic (EN)"' +
        ' data-translation-target="' + section.prefix + '_curriculum_topic_en" data-translation-row=""></textarea>' +
      '</td>' +
      '<td class="cc-week-cell">' +
        '<input class="cc-cell-input cc-num week-input" type="number" name="' +
        section.prefix + '_curriculum_weeks[]" value="1" min="1" max="' +
        section.limit + '">' +
      '</td>' +
      '<td class="cc-block-cell cc-ar">' +
        '<textarea name="' + section.prefix + '_curriculum_topic[]" rows="2" placeholder="الموضوع"' +
        ' data-translation-source="' + section.prefix + '_curriculum_topic" data-translation-row=""></textarea>' +
      '</td>';
    body.appendChild(row);
    if (shouldFocus !== false) {
      var first = row.querySelector('textarea');
      if (first) first.focus();
    }
    return row;
  }

  function rowIsEmpty(row) {
    var topic = rowInputs(row, 'topic');
    return !(topic && topic.value && topic.value.trim());
  }

  function renumberCurriculumRows(section) {
    var body = sectionBody(section);
    if (!body) return;
    body.querySelectorAll('tr').forEach(function (row, index) {
      row.querySelectorAll('[data-translation-row]').forEach(function (element) {
        element.setAttribute('data-translation-row', String(index));
      });
    });
  }

  function recalcSection(section) {
    var body = sectionBody(section);
    if (!body) return 0;
    var total = 0;
    body.querySelectorAll('tr').forEach(function (row) {
      if (rowIsEmpty(row)) return;
      var weeks = rowInputs(row, 'weeks');
      total += parseInt(weeks && weeks.value || 0, 10) || 0;
    });
    var output = document.getElementById(section.totalId);
    if (output) {
      output.textContent = total;
      output.classList.toggle('cc-weeks-warning', total > section.limit);
    }
    var addButton = document.getElementById(section.addId);
    if (addButton) {
      var limitReached = total >= section.limit;
      addButton.disabled = limitReached;
      addButton.title = limitReached
        ? 'لا يمكن إضافة صف لأن مجموع الأسابيع بلغ 12 أسبوعًا'
        : '';
    }
    if (section.prefix === 'theoretical') theoreticalWeeksTotal = total;
    else if (section.prefix === 'practical') practicalWeeksTotal = total;
    return total;
  }

  function initSection(section) {
    var body = sectionBody(section);
    if (!body) return;
    if (translationEnabled()) {
      body.addEventListener('input', function (event) {
        autoResize(event.target);
        renumberCurriculumRows(section);
        recalcSection(section);
      });
    }
    body.addEventListener('input', function (event) {
      if (!event.target || !event.target.matches) return;
      if (event.target.matches('textarea')) autoResize(event.target);
      if (event.target.matches('.week-input')) recalcSection(section);
    });
    var addButton = document.getElementById(section.addId);
    if (addButton) {
      addButton.addEventListener('click', function () {
        if (recalcSection(section) >= section.limit) return;
        createCurriculumRow(section);
        renumberCurriculumRows(section);
        recalcSection(section);
      });
    }
    body.querySelectorAll('tr').forEach(function (row) {
      var weeks = rowInputs(row, 'weeks');
      if (weeks && !weeks.value) weeks.value = 1;
    });
    renumberCurriculumRows(section);
    recalcSection(section);
  }

  function initCurriculum() {
    SECTIONS.forEach(initSection);
  }

  /* ── Hours, credits, semester ── */
  function recalcHours() {
    if (!sheet) return;
    var names = ['theory_hours', 'practical_hours', 'tutorial_hours'];
    var total = 0;
    names.forEach(function (name) {
      var input = sheet.querySelector('[name="' + name + '"]');
      if (input) total += parseInt(input.value || 0, 10) || 0;
    });
    var totalInput = sheet.querySelector('[name="total_hours"]');
    if (totalInput) totalInput.value = total;
    ['theory_hours', 'practical_hours', 'tutorial_hours', 'total_hours', 'credits', 'semester'].forEach(function (name) {
      var main = sheet.querySelector('[name="' + name + '"]');
      if (!main) return;
      sheet.querySelectorAll('[data-mirror="' + name + '"]').forEach(function (mirror) {
        mirror.value = main.value;
      });
    });
    var semesterLabel = sheet.querySelector('[data-semester-en]');
    if (semesterLabel) {
      var select = sheet.querySelector('[name="semester"]');
      var value = select ? select.value : '';
      semesterLabel.textContent = SEMESTER_EN[value] || '—';
    }
  }

  function latinDigits(value) {
    return String(value || '')
      .replace(/[\u0660-\u0669]/g, function (digit) {
        return String.fromCharCode(digit.charCodeAt(0) - 0x0660 + 0x30);
      })
      .replace(/[\u06F0-\u06F9]/g, function (digit) {
        return String.fromCharCode(digit.charCodeAt(0) - 0x06F0 + 0x30);
      });
  }

  function initFormBehavior() {
    if (!form || !sheet) return;
    ['theory_hours', 'practical_hours', 'tutorial_hours', 'credits', 'semester'].forEach(function (name) {
      var input = sheet.querySelector('[name="' + name + '"]');
      if (!input) return;
      input.addEventListener('input', recalcHours);
      input.addEventListener('change', recalcHours);
    });
    sheet.addEventListener('input', function (event) {
      var input = event.target;
      if (!input || !input.matches || !input.matches('input[type="number"]')) return;
      var latin = latinDigits(input.value);
      if (latin !== input.value) {
        input.value = latin;
        recalcHours();
      }
    });
    form.addEventListener('submit', function (event) {
      if (theoreticalWeeksTotal > WEEKS_LIMIT || practicalWeeksTotal > WEEKS_LIMIT) {
        event.preventDefault();
        var message = 'مجموع الأسابيع يجب ألا يتجاوز 12 أسبوعًا: النظري (' +
          theoreticalWeeksTotal + ') والعملي (' + practicalWeeksTotal +
          ') — لا يمكن الحفظ أو الإرسال.';
        if (window.showNotification) window.showNotification(message, 'error', 6000);
        else alert(message);
        return;
      }
      var submitter = event.submitter;
      if (submitter && submitter.dataset && submitter.dataset.action) return;
      if (!Object.keys(translationTimers).length && !Object.keys(pendingTranslations).length) return;
      event.preventDefault();
      flushTranslations().then(function () {
        form.submit();
      });
    });
    recalcHours();
  }

  function initEnterNavigation() {
    if (!form) return;
    form.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' || event.target.tagName === 'TEXTAREA') return;
      var inputs = Array.prototype.slice.call(
        form.querySelectorAll('input:not([type=hidden]), select, textarea')
      ).filter(function (input) { return input.offsetParent !== null; });
      var index = inputs.indexOf(document.activeElement);
      if (index === -1) return;
      event.preventDefault();
      var direction = event.shiftKey ? -1 : 1;
      for (var offset = 1; offset < inputs.length; offset += 1) {
        var candidate = inputs[index + direction * offset];
        if (!candidate) continue;
        if (!candidate.value) {
          candidate.focus();
          return;
        }
      }
      var fallback = inputs[index + direction];
      if (fallback) fallback.focus();
    });
  }

  function init() {
    if (initialized) return;
    initialized = true;
    initCurriculum();
    initTranslation();
    initFormBehavior();
    initEnterNavigation();
    markExistingEnglishManual();
    scheduleInitialTranslations();
    resizeAllTextareas();
    if (window.ResizeObserver && sheet) {
      new ResizeObserver(function () {
        resizeAllTextareas();
      }).observe(sheet);
    }
    window.addEventListener('resize', scheduleResize);
    window.addEventListener('beforeprint', preparePrint);
    window.addEventListener('afterprint', function () {
      if (sheet) sheet.style.setProperty('--cc-print-zoom', '1');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.flushCourseContentTranslations = flushTranslations;

  window.downloadCourseSheet = function () {
    if (!sheet) return;
    Promise.resolve(flushTranslations()).then(function () {
      preparePrint();
      window.print();
    });
  };
})();
