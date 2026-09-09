/**
 * CourseIconPicker — shared, dependency-free icon picker for course icons.
 *
 * Usage:
 *   var picker = window.CourseIconPicker.create(el, { value: '📖', onChange: fn });
 *   picker.getValue(); // current icon
 *   picker.setValue('🔬'); // set + re-render selected state
 *
 * Options:
 *   value     initial icon (default '📖')
 *   onChange  callback(icon) after a user pick
 *   preview   show a live preview above the grid (default true)
 *
 * The picker uses <button> elements only (no hidden radios/labels), so it never
 * triggers focus-scroll or layout shifts. The active state is a simple colour
 * change (no transform), keeping the grid size stable.
 */
window.CourseIconPicker = (function () {
  'use strict';

  var DEFAULT_ICON = '📖';

  var ICONS = [
    '📖', '📚', '📐', '📏', '📊', '📈',
    '🔬', '🔭', '🧪', '⚗️', '⚙️', '🛠️',
    '🔧', '🪛', '⚡', '💡', '🔌', '🔋',
    '🖥️', '💻', '📱', '📡', '🛰️', '📶',
    '🌐', '🔒', '🔑', '🗄️', '📁', '📝',
    '✏️', '🗺️', '🧭', '🏗️', '🏭', '🏢',
    '🚗', '🚢', '🛢️', '⛽', '🧮', '⚖️',
    '🧰', '🎛️', '📽️', '🎓', '🏫', '🩺', '🧱'
  ];

  function create(container, opts) {
    opts = opts || {};
    var value = opts.value || DEFAULT_ICON;
    var onChange = typeof opts.onChange === 'function' ? opts.onChange : null;

    container.classList.add('icon-picker');
    container.innerHTML = '';

    var preview = null;
    if (opts.preview !== false) {
      preview = document.createElement('span');
      preview.className = 'icon-picker-preview';
      preview.setAttribute('aria-hidden', 'true');
      container.appendChild(preview);
    }

    var grid = document.createElement('div');
    grid.className = 'icon-picker-grid';
    container.appendChild(grid);

    var buttons = [];
    ICONS.forEach(function (ic) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'icon-opt';
      b.textContent = ic;
      b.title = ic;
      b.setAttribute('aria-pressed', 'false');
      b.addEventListener('click', function () {
        setValue(ic);
        if (onChange) onChange(ic);
      });
      grid.appendChild(b);
      buttons.push(b);
    });

    function setValue(v) {
      value = v || DEFAULT_ICON;
      if (preview) preview.textContent = value;
      for (var i = 0; i < buttons.length; i++) {
        var active = buttons[i].textContent === value;
        buttons[i].classList.toggle('active', active);
        buttons[i].setAttribute('aria-pressed', active ? 'true' : 'false');
      }
    }

    function getValue() {
      return value;
    }

    setValue(value);
    return { getValue: getValue, setValue: setValue };
  }

  return {
    ICONS: ICONS,
    DEFAULT_ICON: DEFAULT_ICON,
    create: create
  };
})();
