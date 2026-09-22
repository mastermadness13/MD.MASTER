/**
 * Shared course-related UI helper functions.
 * Used by courses_list.js and teachers_super_admin_course_content.js
 */
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  var STATUS_LABELS = {
    'draft': 'مسودة',
    'published': 'منشور',
    'approved': 'منشور',
    'pending_rnd': 'قيد مراجعة R&D',
    'pending_hod': 'قيد مراجعة رئيس القسم',
    'pending_exam': 'قيد المراجعة النهائية',
    'rejected': 'مرفوض'
  };

  var STATUS_COLORS = {
    'draft': 'bg-surface-dim text-on-surface-variant',
    'published': 'bg-green-100 text-green-700',
    'approved': 'bg-green-100 text-green-700',
    'pending_rnd': 'bg-yellow-100 text-yellow-700',
    'pending_hod': 'bg-blue-100 text-blue-700',
    'pending_exam': 'bg-purple-100 text-purple-700',
    'rejected': 'bg-red-100 text-red-700'
  };

  var PDF_STATE_LABELS = {
    'available': 'الملف متاح للتحميل',
    'approved': 'معتمد/منشور',
    'pending_review': 'قيد المراجعة',
    'draft': 'مسودة',
    'rejected': 'مرفوض',
    'none': 'لا يوجد ملف'
  };

  var PDF_STATE_COLORS = {
    'available': 'bg-green-100 text-green-700',
    'approved': 'bg-green-100 text-green-700',
    'pending_review': 'bg-blue-100 text-blue-700',
    'draft': 'bg-surface-dim text-on-surface-variant',
    'rejected': 'bg-red-100 text-red-700',
    'none': 'bg-surface-zebra text-text-muted'
  };

  var PDF_STATE_ICONS = {
    'available': 'download_done',
    'approved': 'verified',
    'pending_review': 'hourglass_top',
    'draft': 'edit_document',
    'rejected': 'block',
    'none': 'file_off'
  };

  /**
   * Render a unified pdf_state badge (the file-status column).
   * @param {string} state - pdf_state key (available/approved/pending_review/draft/rejected/none)
   * @returns {string} HTML string
   */
  function pdfStateBadge(state) {
    var key = state || 'none';
    var label = PDF_STATE_LABELS[key] || key;
    var color = PDF_STATE_COLORS[key] || 'bg-surface-zebra text-text-muted';
    var icon = PDF_STATE_ICONS[key] || 'insert_drive_file';
    return '<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold whitespace-nowrap ' + color + '" title="' + esc(label) + '">' +
      '<span class="material-symbols-outlined text-[14px]">' + icon + '</span>' + esc(label) + '</span>';
  }

/**
   * True when a course row has any file/submission state (has-file filter).
   * @param {string} state - pdf_state key
   * @returns {boolean}
   */
  function pdfStateHasFile(state) {
    var key = state || 'none';
    return key !== 'none';
  }

  /**
   * Render a form status badge.
   * @param {string} status - The status key
   * @param {object} [metaMap] - Optional custom meta map with {label, class} per status
   * @returns {string} HTML string
   */
  function formStatusBadge(status, metaMap) {
    if (!status) {
      return '<span class="text-xs text-text-faint">لا يوجد نموذج بعد</span>';
    }
    if (metaMap && metaMap[status]) {
      var meta = metaMap[status];
      return '<span class="inline-block px-2.5 py-1 rounded-full text-xs font-bold whitespace-nowrap ' + esc(meta['class'] || '') + '">' + esc(meta.label || status) + '</span>';
    }
    var label = STATUS_LABELS[status] || status;
    var color = STATUS_COLORS[status] || 'bg-surface-dim text-on-surface-variant';
    return '<span class="inline-block px-2.5 py-1 rounded-full text-xs font-bold whitespace-nowrap ' + color + '">' + esc(label) + '</span>';
  }

  /**
   * Render teacher name badges.
   * @param {string[]} teachers - Array of teacher names
   * @returns {string} HTML string
   */
  function teachersCell(teachers) {
    if (!teachers || !teachers.length) {
      return '<span class="text-xs text-text-faint">—</span>';
    }
    return '<div class="flex flex-wrap gap-1">' + teachers.map(function (t) {
      return '<span class="inline-flex items-center gap-1 text-xs font-semibold text-text-secondary bg-surface-zebra px-2 py-0.5 rounded-full"><span class="material-symbols-outlined text-[14px] text-text-muted">person</span>' + esc(t) + '</span>';
    }).join(' ') + '</div>';
  }

  /**
   * Render department name badges.
   * @param {string[]} deptNames - Array of department names
   * @returns {string} HTML string
   */
  function deptBadges(deptNames) {
    if (!deptNames || !deptNames.length) {
      return '<span class="text-xs text-text-faint">—</span>';
    }
    return '<div class="flex flex-wrap gap-1">' + deptNames.map(function (d) {
      return '<span class="inline-flex items-center gap-1 text-xs font-semibold text-text-secondary bg-surface-zebra px-2 py-0.5 rounded-full">' + esc(d) + '</span>';
    }).join(' ') + '</div>';
  }

  /**
   * Render prerequisite badges.
   * @param {string[]} prereqs - Array of prerequisite codes
   * @returns {string} HTML string
   */
  function prereqBadges(prereqs) {
    if (!prereqs || !prereqs.length) {
      return '<span class="text-text-faint font-semibold">—</span>';
    }
    return prereqs.map(function (p) {
      return '<span class="inline-flex items-center gap-1 font-mono text-[11px] font-bold text-primary bg-primary-faint px-1.5 py-0.5 rounded border border-primary/20 mx-0.5">' + esc(p) + '</span>';
    }).join(' ');
  }

  // Expose globally
  window.CourseHelpers = {
    esc: esc,
    formStatusBadge: formStatusBadge,
    pdfStateBadge: pdfStateBadge,
    pdfStateHasFile: pdfStateHasFile,
    teachersCell: teachersCell,
    deptBadges: deptBadges,
    prereqBadges: prereqBadges,
    STATUS_LABELS: STATUS_LABELS,
    STATUS_COLORS: STATUS_COLORS,
    PDF_STATE_LABELS: PDF_STATE_LABELS,
    PDF_STATE_COLORS: PDF_STATE_COLORS
  };
})();
