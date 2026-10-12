/**
 * Unified Search Component — debounced AJAX search with real-time updates.
 *
 * Usage: Call `SearchComponent.init(config)` on each list page.
 * Or use the inline `data-search-*` attributes for auto-initialization.
 *
 * Config:
 *   formSelector:      CSS selector for the search form
 *   inputSelector:     CSS selector for the search input
 *   tableSelector:     CSS selector for the table to update
 *   paginationSelector: CSS selector for the pagination wrapper
 *   countSelector:     CSS selector for the result count badge
 *   clearSelector:     CSS selector for the clear button
 *   spinnerSelector:   CSS selector for the loading spinner
 *   debounceMs:        Debounce delay (default 300)
 *   urlBuilder:        Function(params) -> URL for AJAX fetch
 *   resetSelector:     CSS selector for the "reset all filters" button
 *   formAction:        Explicit submit target for the AJAX URL
 *   onComplete:        Callback after results rendered
 */

const SearchComponent = (function () {
  let _config = {};
  let _debounceTimer = null;
  let _abortController = null;
  let _lastQuery = '';
  let _form = null;

  function init(config) {
    _config = Object.assign({
      formSelector: '.search-form',
      inputSelector: '.search-input',
      tableSelector: '.search-table',
      paginationSelector: '.search-pagination',
      countSelector: '.search-results-count',
      clearSelector: '.search-clear',
      spinnerSelector: '.search-spinner',
      filterSelectors: {},
      debounceMs: 300,
      urlBuilder: null,
      resetSelector: null,   // button that clears the search + all filters
      formAction: null,      // explicit submit target for the AJAX URL
      onComplete: null,
    }, config);

    const form = document.querySelector(_config.formSelector);
    if (!form) return;
    _form = form;

    const input = form.querySelector(_config.inputSelector);
    const clearBtn = form.querySelector(_config.clearSelector);
    const filters = {};
    Object.entries(_config.filterSelectors).forEach(([key, sel]) => {
      filters[key] = form.querySelector(sel);
    });

    // Input debounce
    if (input) {
      input.addEventListener('input', function () {
        _updateClearVisibility(this);
        _debouncedSearch();
      });

      // Enter key
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
          this.value = '';
          _updateClearVisibility(this);
          _debouncedSearch();
        }
        if (e.key === 'Enter') {
          e.preventDefault();
          _debouncedSearch(true); // immediate
        }
      });
    }

    // Clear button
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        if (input) {
          input.value = '';
          _updateClearVisibility(input);
          input.focus();
        }
        _debouncedSearch(true);
      });
    }

    // /  زر إعادة التعيين: يمسح النص ويعيد الفلاتر إلى الافتراضي ويحدّث مرة واحدة
    if (_config.resetSelector) {
      const resetBtn = form.querySelector(_config.resetSelector);
      if (resetBtn) {
        resetBtn.addEventListener('click', function () {
          if (_debounceTimer) { clearTimeout(_debounceTimer); _debounceTimer = null; }
          if (input) { input.value = ''; _updateClearVisibility(input); }
          Object.keys(filters).forEach(function (key) {
            var sel = filters[key];
            if (sel && sel.options && sel.options.length) sel.selectedIndex = 0;
          });
          _performSearch(true);
        });
      }
    }

    // Filter changes trigger immediate search
    Object.values(filters).forEach(sel => {
      if (sel) {
        sel.addEventListener('change', function () {
          _debouncedSearch(true);
        });
      }
    });

    // Keyboard shortcut: / to focus search
    document.addEventListener('keydown', function (e) {
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const active = document.activeElement;
        if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.tagName === 'SELECT')) return;
        e.preventDefault();
        if (input) input.focus({ preventScroll: true });
      }
    });

    // Initial state
    if (input) _updateClearVisibility(input);
  }

  function _updateClearVisibility(input) {
    const root = _form || document;
    const clearBtn = root.querySelector(_config.clearSelector);
    if (clearBtn) {
      clearBtn.style.display = input.value ? 'flex' : 'none';
    }
  }

  function _debouncedSearch(immediate) {
    if (_debounceTimer) clearTimeout(_debounceTimer);
    if (immediate) {
      _performSearch();
    } else {
      _debounceTimer = setTimeout(_performSearch, _config.debounceMs);
    }
  }

  function _performSearch(force) {
    const form = document.querySelector(_config.formSelector);
    if (!form) return;

    const input = form.querySelector(_config.inputSelector);
    const search = input ? input.value.trim() : '';

    // Collect filter values
    const params = {};
    if (search) params.search = search;

    Object.entries(_config.filterSelectors).forEach(([key, sel]) => {
      const el = form.querySelector(sel);
      if (el && el.value) params[key] = el.value;
    });

    // Also get date if present
    const dateInput = form.querySelector('.search-date');
    if (dateInput && dateInput.value) params.date = dateInput.value;

    // Preserve current page=1 on new search
    params.page = '1';

    // Build URL
    let url;
    if (_config.urlBuilder) {
      url = _config.urlBuilder(params);
    } else {
      const baseUrl = _config.formAction || form.getAttribute('action') || window.location.pathname;
      const qs = new URLSearchParams(params).toString();
      url = baseUrl + '?' + qs;
    }

    // Abort previous request
    if (_abortController) _abortController.abort();
    _abortController = new AbortController();

    // Show spinner
    _showSpinner(true);

    // Check if query changed
    const queryKey = JSON.stringify(params);
    if (!force && queryKey === _lastQuery) {
      _showSpinner(false);
      return;
    }
    _lastQuery = queryKey;

    // Push state (URL bar updates)
    window.history.replaceState({}, '', url);

    // Fetch via AJAX
    fetch(url, {
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'text/html',
      },
      signal: _abortController.signal,
    })
      .then(resp => {
        if (!resp.ok) throw new Error('Network response was not ok');
        return resp.text();
      })
      .then(html => {
        _renderResults(html);
        _showSpinner(false);
        if (_config.onComplete) _config.onComplete();
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.error('Search error:', err);
          _showSpinner(false);
        }
      });
  }

  function _renderResults(html) {
    // Parse the HTML response
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    // Update table body
    const newTable = doc.querySelector(_config.tableSelector);
    const currentTable = document.querySelector(_config.tableSelector);
    if (newTable && currentTable) {
      // Replace table content (thead stays, tbody replaces)
      const newBody = newTable.querySelector('tbody');
      const currentBody = currentTable.querySelector('tbody');
      if (newBody && currentBody) {
        currentBody.innerHTML = newBody.innerHTML;
      }
      // Also update thead if columns might change
      const newHead = newTable.querySelector('thead');
      const currentHead = currentTable.querySelector('thead');
      if (newHead && currentHead) {
        currentHead.innerHTML = newHead.innerHTML;
      }
    }

    // Update pagination
    const newPagination = doc.querySelector(_config.paginationSelector);
    const currentPagination = document.querySelector(_config.paginationSelector);
    if (newPagination && currentPagination) {
      currentPagination.innerHTML = newPagination.innerHTML;
    } else if (!newPagination && currentPagination) {
      currentPagination.innerHTML = '';
    } else if (newPagination && !currentPagination) {
      // Insert pagination after table
      currentTable.parentNode.insertBefore(newPagination, currentTable.nextSibling);
    }

    // Update count badge
    const newCount = doc.querySelector(_config.countSelector);
    const currentCount = (_form || document).querySelector(_config.countSelector);
    if (newCount && currentCount) {
      // /  نحدّث النص فقط حتى لا نمسح أيقونة الشارة
      const newVal = newCount.querySelector('[data-count-value]');
      const curVal = currentCount.querySelector('[data-count-value]');
      if (newVal && curVal) {
        curVal.textContent = newVal.textContent;
      } else {
        currentCount.textContent = newCount.textContent;
      }
      currentCount.style.display = newCount.textContent.trim() ? 'inline-flex' : 'none';
    } else if (newCount && !currentCount) {
      // Create count badge
      const badge = document.createElement('span');
      badge.className = 'search-results-count';
      badge.textContent = newCount.textContent;
      const searchBar = document.querySelector('.search-bar');
      if (searchBar) searchBar.appendChild(badge);
    }

    // Update empty state
    const newEmpty = doc.querySelector('.search-empty');
    const currentEmpty = document.querySelector('.search-empty');
    if (newEmpty && currentEmpty) {
      currentEmpty.innerHTML = newEmpty.innerHTML;
    }

    // Update URL for bookmarkability (already done before fetch)
  }

  function _showSpinner(show) {
    const root = _form || document;
    const spinner = root.querySelector(_config.spinnerSelector);
    if (spinner) {
      spinner.classList.toggle('active', show);
      spinner.style.display = show ? '' : 'none';
    }
  }

  // Auto-initialize from data attributes
  function autoInit() {
    document.querySelectorAll('[data-search-form]').forEach(form => {
      const cfg = {
        formSelector: '#' + form.id || '.search-form',
        inputSelector: form.dataset.searchInput || '.search-input',
        tableSelector: form.dataset.searchTable || '.search-table',
        paginationSelector: form.dataset.searchPagination || '.search-pagination',
        countSelector: form.dataset.searchCount || '.search-results-count',
        clearSelector: form.dataset.searchClear || '.search-clear',
        spinnerSelector: form.dataset.searchSpinner || '.search-spinner',
        debounceMs: parseInt(form.dataset.searchDebounce) || 300,
      };

      // Filter selectors from data attributes
      if (form.dataset.searchFilters) {
        const filterPairs = form.dataset.searchFilters.split(',');
        filterPairs.forEach(pair => {
          const [key, sel] = pair.split(':');
          if (key && sel) cfg.filterSelectors[key.trim()] = sel.trim();
        });
      }

      init(cfg);
    });
  }

  // Public API
  return {
    init,
    autoInit,
    search: function () { _performSearch(true); },
    reset: function () { _performSearch(true); },
  };
})();

// Auto-initialize on DOM ready
document.addEventListener('DOMContentLoaded', function () {
  SearchComponent.autoInit();
});
