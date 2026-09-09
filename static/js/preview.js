// Shared JavaScript utilities for preview pages

// Get initials from Arabic name
function getInitials(name) {
  if (!name) return '??';
  var parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return parts[0].charAt(0) + parts[1].charAt(0);
  }
  return parts[0].substring(0, 2);
}

// Generate avatar color based on name string
function getAvatarColor(name) {
  var colors = [
    'bg-blue-500', 'bg-green-500', 'bg-purple-500', 'bg-pink-500',
    'bg-indigo-500', 'bg-teal-500', 'bg-orange-500', 'bg-cyan-500'
  ];
  var hash = 0;
  for (var i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

// Render pagination controls
function renderPagination(containerId, totalPages, currentPage, onPageClick) {
  var container = document.getElementById(containerId);
  if (!container) return;
  
  var html = '';
  
  // Previous button
  html += '<button class="pagination-btn ' + (currentPage <= 1 ? 'opacity-50 cursor-not-allowed' : '') + '" ' + (currentPage <= 1 ? 'disabled' : '') + ' onclick="' + onPageClick + '(' + (currentPage - 1) + ')">';
  html += '<span class="material-symbols-outlined text-sm">chevron_right</span>';
  html += '</button>';
  
  // Page numbers
  var startPage = Math.max(1, currentPage - 2);
  var endPage = Math.min(totalPages, startPage + 4);
  startPage = Math.max(1, endPage - 4);
  
  for (var i = startPage; i <= endPage; i++) {
    html += '<button class="pagination-btn ' + (i === currentPage ? 'active' : '') + '" onclick="' + onPageClick + '(' + i + ')">' + i + '</button>';
  }
  
  // Next button
  html += '<button class="pagination-btn ' + (currentPage >= totalPages ? 'opacity-50 cursor-not-allowed' : '') + '" ' + (currentPage >= totalPages ? 'disabled' : '') + ' onclick="' + onPageClick + '(' + (currentPage + 1) + ')">';
  html += '<span class="material-symbols-outlined text-sm">chevron_left</span>';
  html += '</button>';
  
  container.innerHTML = html;
}

// Show empty state
function showEmptyState(tableBodyId, message) {
  var tbody = document.getElementById(tableBodyId);
  if (!tbody) return;
  
  var colspan = tbody.closest('table').querySelector('thead tr').children.length;
  tbody.innerHTML = '<tr><td colspan="' + colspan + '" class="px-6 py-12 text-center">' +
    '<div class="flex flex-col items-center justify-center text-gray-400">' +
    '<span class="material-symbols-outlined text-5xl mb-3">group_off</span>' +
    '<p class="text-lg font-medium">' + message + '</p>' +
    '<p class="text-sm mt-1">لم يتم العثور على نتائج تطابق البحث</p>' +
    '</div></td></tr>';
}

/* ── Attribute-driven form validation ─────────────────────────
   Any form with the `data-validate-form` attribute is validated
   on submit. Each field may declare `data-validate` with rules
   separated by `|`:
     required          — field must not be empty
     email             — must look like an email address
     phone             — digits, spaces, +, - , parentheses (8–15)
     match:fieldName   — must equal another field's value
   A `data-label` provides the Arabic label used in error messages.
*/
function formFieldError(field) {
  var group = field.closest('.form-group');
  var error = group && group.querySelector('.form-error');
  if (!error) {
    error = document.createElement('p');
    error.className = 'form-error';
    if (group) {
      group.appendChild(error);
    } else {
      field.insertAdjacentElement('afterend', error);
    }
  }
  return error;
}

function validateField(field, label) {
  var rules = (field.getAttribute('data-validate') || '').split('|');
  var value = (field.value || '').trim();
  var error = '';

  rules.forEach(function(rule) {
    if (!rule || error) return;
    if (rule === 'required' && !value) {
      error = label + ' مطلوب';
    } else if (rule === 'email' && value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
      error = 'صيغة البريد الإلكتروني غير صحيحة في ' + label;
    } else if (rule === 'phone' && value && !/^[0-9+\-\s()]{8,15}$/.test(value)) {
      error = 'صيغة رقم الهاتف غير صحيحة في ' + label;
    } else if (rule.indexOf('match:') === 0) {
      var targetName = rule.split(':')[1];
      var target = field.form && field.form.querySelector('[name="' + targetName + '"], #' + targetName);
      if (target && value !== (target.value || '').trim()) {
        error = label + ' لا يطابق الحقل المقابل';
      }
    }
  });

  var errorEl = formFieldError(field);
  if (error) {
    errorEl.textContent = error;
    field.classList.add('border-[var(--error)]');
    return false;
  }
  errorEl.textContent = '';
  field.classList.remove('border-[var(--error)]');
  return true;
}

// Returns true when the form is valid, false otherwise.
function validateForm(form) {
  var valid = true;
  var firstInvalid = null;

  form.querySelectorAll('[data-validate]').forEach(function(field) {
    if (field.disabled || field.type === 'hidden') return;
    var label = field.getAttribute('data-label') || (field.name || 'الحقل').replace(/_/g, ' ');
    var fieldOk = validateField(field, label);
    if (!fieldOk) {
      valid = false;
      if (!firstInvalid) firstInvalid = field;
    }
  });

  if (firstInvalid) firstInvalid.focus();
  return valid;
}

// Auto-bind submit handling for every data-validate-form.
document.addEventListener('submit', function(e) {
  var form = e.target;
  if (!form || !form.hasAttribute('data-validate-form')) return;

  e.preventDefault();
  if (validateForm(form)) {
    var msg = form.getAttribute('data-success-message') || 'تم الحفظ بنجاح';
    alert(msg);
  }
});
