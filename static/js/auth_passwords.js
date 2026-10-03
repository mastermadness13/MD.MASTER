/* Shared auth password helpers — change-password & reset-password pages. */

function togglePassword(inputId) {
  var input = document.getElementById(inputId);
  if (!input) return;
  var btn = input.parentElement && input.parentElement.querySelector('.auth-password-toggle');
  var icon = btn && btn.querySelector('.material-symbols-outlined');
  var showing = input.type === 'text';
  input.type = showing ? 'password' : 'text';
  if (icon) icon.textContent = showing ? 'visibility' : 'visibility_off';
  if (btn) btn.setAttribute('aria-label', showing ? 'إظهار كلمة المرور' : 'إخفاء كلمة المرور');
}

function passwordRequirements(pw) {
  return {
    length: Array.from(pw).length >= 8,
    upper: /\p{Lu}/u.test(pw),
    lower: /\p{Ll}/u.test(pw),
    digit: /\p{N}/u.test(pw)
  };
}

function passwordScore(requirements) {
  return Object.keys(requirements).filter(function (key) {
    return requirements[key];
  }).length;
}

function setReqOk(id, ok) {
  var el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('strength-req-ok', ok);
  var icon = el.querySelector('.material-symbols-outlined');
  if (icon) icon.textContent = ok ? 'check_circle' : 'radio_button_unchecked';
}

function updateStrength(input) {
  var requirements = passwordRequirements(input.value || '');
  var s = passwordScore(requirements);

  var label = document.getElementById('strength-label');
  var names = ['ضعيفة', 'متوسطة', 'متوسطة', 'جيدة', 'قوية'];
  if (label) label.textContent = names[s] || names[0];

  for (var i = 1; i <= 4; i++) {
    var seg = document.getElementById('seg-' + i);
    if (!seg) continue;
    seg.classList.toggle('on', i <= s);
    seg.classList.toggle('warn', i <= s && s < 3);
    seg.classList.toggle('strong', i <= s && s === 4);
  }

  setReqOk('req-length', requirements.length);
  setReqOk('req-upper', requirements.upper);
  setReqOk('req-lower', requirements.lower);
  setReqOk('req-digit', requirements.digit);
}

function showFieldError(field, msg) {
  var group = field.closest('.form-group');
  var error = group && group.querySelector('.form-error');
  if (!error) {
    error = document.createElement('p');
    error.className = 'form-error';
    if (group) group.appendChild(error);
    else field.insertAdjacentElement('afterend', error);
  }
  error.textContent = msg;
  field.classList.add('auth-invalid');
}

function clearFieldError(field) {
  var group = field.closest('.form-group');
  var error = group && group.querySelector('.form-error');
  if (error) error.textContent = '';
  field.classList.remove('auth-invalid');
}

function checkConfirmMatch(input) {
  var targetName = input.getAttribute('data-confirm-match');
  var target = targetName && input.form && input.form.querySelector('[name="' + targetName + '"]');
  var value = (input.value || '').trim();
  var other = target ? (target.value || '').trim() : '';
  if (value && other && value !== other) {
    showFieldError(input, (input.getAttribute('data-label') || 'تأكيد كلمة المرور') + ' لا يطابق الحقل المقابل');
  } else {
    clearFieldError(input);
  }
}

document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-password-strength]').forEach(function (input) {
    input.addEventListener('input', function () { updateStrength(input); });
    updateStrength(input);
  });

  document.querySelectorAll('[data-confirm-match]').forEach(function (input) {
    input.addEventListener('input', function () { checkConfirmMatch(input); });
  });

  // Submit-time guards for auth forms (preview.js does not load on auth pages).
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || !form.hasAttribute('data-validate-form')) return;

    var firstInvalid = null;
    form.querySelectorAll('[required]').forEach(function (field) {
      if (field.disabled || field.type === 'hidden' || field.type === 'submit') return;
      var label = field.getAttribute('data-label') || (field.name || 'الحقل').replace(/_/g, ' ');
      if (!(field.value || '').trim()) {
        showFieldError(field, label + ' مطلوب');
        if (!firstInvalid) firstInvalid = field;
      } else {
        clearFieldError(field);
      }
    });

    form.querySelectorAll('[data-confirm-match]').forEach(function (field) {
      var targetName = field.getAttribute('data-confirm-match');
      var target = targetName && form.querySelector('[name="' + targetName + '"]');
      var valid = (field.value || '').trim() && target && (field.value || '').trim() === (target.value || '').trim();
      if (!valid) {
        showFieldError(field, (field.getAttribute('data-label') || 'تأكيد كلمة المرور') + ' لا يطابق الحقل المقابل');
        if (!firstInvalid) firstInvalid = field;
      }
    });

    if (firstInvalid) {
      e.preventDefault();
      firstInvalid.focus();
    }
  });
});