/**
 * Navigation - Unified header + mobile bottom nav + footer
 * Include on every page: <script src="../shared/nav.js" data-current="pageKey"></script>
 *
 * All main sections live on the unified portal (index.html#section).
 */
(function () {
  const script = document.currentScript;
  const current = script ? script.getAttribute('data-current') || 'home' : 'home';
  // data-minimal: header shows brand + login only (used by the unified portal,
  // where .portal-tabs provides the section navigation)
  const MINIMAL = script ? script.hasAttribute('data-minimal') : false;
  const ROOT = (window.Utils && window.Utils.publicRoot) ? Utils.publicRoot(script) : '';

  const NAV_LINKS = [
    { key: 'home', label: 'الرئيسية', icon: 'fa-house', href: 'index.html#home' },
    { key: 'timetable', label: 'الجداول', icon: 'fa-calendar-days', href: 'index.html#timetables' },
    { key: 'exams', label: 'الامتحانات', icon: 'fa-file-lines', href: 'index.html#exams' },
    { key: 'course', label: 'مواد دراسية', icon: 'fa-graduation-cap', href: 'index.html#courses' }
  ];

  // hash -> nav key, for active-state sync on the unified portal
  const HASH_TO_KEY = {
    home: 'home',
    timetables: 'timetable',
    exams: 'exams',
    library: 'course',
    courses: 'course'
  };

  function onPortal() {
    return /\/index\.html$/.test(window.location.pathname);
  }

  function activeKey() {
    if (onPortal()) {
      const h = (window.location.hash || '').replace('#', '');
      if (HASH_TO_KEY[h]) return HASH_TO_KEY[h];
      return 'home';
    }
    return current;
  }

  const BRAND = 'كلية التقنية الهندسية زوارة';

  function resolve(href) {
    if (window.Utils && window.Utils.resolveRootRelative) {
      return Utils.resolveRootRelative(href, ROOT);
    }
    return ROOT + href;
  }

  function buildHeader() {
    const act = activeKey();
    const loginLink = '<a href="/login" style="padding:8px 14px;border:1.5px solid var(--primary);border-radius:10px;color:var(--primary);font-weight:600"><i class="fa-solid fa-user-lock"></i> تسجيل الدخول</a>';
    if (MINIMAL) {
      // Portal pages: section navigation lives in .portal-tabs; header = brand + login only
      return `
      <header class="site-header">
        <div class="nav-container">
          <a href="${resolve('index.html')}" class="brand">
            <span class="logo"><img src="${resolve('../image/logo.png')}" alt="شعار كلية التقنية الهندسية زوارة"></span>
            <span class="brand-text">${BRAND}</span>
          </a>
          <div>${loginLink}</div>
        </div>
      </header>
    `;
    }
    const links = NAV_LINKS.map(l => {
      const drop = l.children
        ? '<div class="nav-drop"><div class="nav-drop-inner">' +
          l.children.map(c => `<a href="${resolve(c.href)}">${c.label}</a>`).join('') +
          '</div></div>'
        : '';
      return `<li class="${l.children ? 'has-drop' : ''}"><a href="${resolve(l.href)}" class="${l.key === act ? 'active' : ''}"><i class="fa-solid ${l.icon}"></i> ${l.label}</a>${drop}</li>`;
    }).join('');
    return `
      <header class="site-header">
        <div class="nav-container">
          <a href="${resolve('index.html')}" class="brand">
            <span class="logo"><img src="${resolve('../image/logo.png')}" alt="شعار كلية التقنية الهندسية زوارة"></span>
            <span class="brand-text">${BRAND}</span>
          </a>
          <nav>
            <ul class="nav-links">${links}
              <li>${loginLink}</li>
            </ul>
          </nav>
        </div>
      </header>
      <nav class="mobile-nav" aria-label="القائمة الرئيسية">
        <div class="mobile-nav-inner">
          ${NAV_LINKS.slice(0, 5).map(l => `
            <a href="${resolve(l.href)}" class="${l.key === act ? 'active' : ''}">
              <span class="mn-icon"><i class="fa-solid ${l.icon}"></i></span>
              ${l.label}
            </a>`).join('')}
        </div>
      </nav>
    `;
  }

  function buildFooter() {
    return `
      <footer class="site-footer">
        <div class="footer-inner">
          <div>
            <h3>${BRAND}</h3>
            <p style="font-size:.85rem;line-height:1.7;opacity:.85">منصة تعليمية متكاملة لأقسام الكلية — الجداول الدراسية، الامتحانات، والمكتبة الرقمية في مكان واحد.</p>
          </div>
          <div>
            <h3>روابط سريعة</h3>
            <a href="${resolve('index.html#home')}">الرئيسية</a>
            <a href="${resolve('index.html#timetables')}">الجداول</a>
            <a href="${resolve('index.html#exams')}">الامتحانات</a>
          </div>
          <div>
            <h3>للطلبة</h3>
            <a href="${resolve('index.html#courses')}">المواد الدراسية</a>
            <a href="${resolve('index.html#timetables')}">الجدول الأسبوعي</a>
          </div>
          <div>
            <h3>تواصل معنا</h3>
            <a href="tel:031000000"><i class="fa-solid fa-phone"></i> 031-000000</a>
            <a href="mailto:info@cte-zuwara.edu.ly"><i class="fa-solid fa-envelope"></i> info@cte-zuwara.edu.ly</a>
            <a href="https://maps.google.com/?q=Zuwara,Libya" target="_blank" rel="noopener"><i class="fa-solid fa-location-dot"></i> زوارة، ليبيا</a>
          </div>
        </div>
        <div class="footer-bottom">© 2026 ${BRAND} — جميع الحقوق محفوظة</div>
      </footer>
    `;
  }

  function inject() {
    const headerPlaceholder = document.getElementById('site-header');
    if (headerPlaceholder) headerPlaceholder.innerHTML = buildHeader();
    const footerPlaceholder = document.getElementById('site-footer');
    if (footerPlaceholder) footerPlaceholder.innerHTML = buildFooter();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }

  // Keep header/footer highlight in sync with portal section changes
  window.addEventListener('hashchange', inject);
})();
