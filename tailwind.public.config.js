/**
 * Tailwind config for the PUBLIC site (static/public/).
 *
 * PORTED VERBATIM from the inline `tailwind = { config: ... }` block that
 * static/public/pages/department-info.html used to hand to the Play CDN.
 *
 * This palette is deliberately NOT the app's: the public site uses
 * primary #500088 with a surface/text/border scale that the authenticated UI
 * does not have. Do not merge these two configs — they are two design
 * systems that happen to share a name.
 *
 * Scope is one page: department-info.html plus the shared JS it loads.
 */
import forms from '@tailwindcss/forms';
import containerQueries from '@tailwindcss/container-queries';

export default {
  darkMode: 'class',
  content: [
    './static/public/pages/department-info.html',
    './static/public/shared/*.js',
  ],
  theme: {
    extend: {
      fontFamily: { sans: ['Hanken Grotesk', 'Tajawal', 'sans-serif'] },
      colors: {
        primary: { DEFAULT: '#500088', light: '#64229b', faint: '#f1dbff', container: '#f1dbff' },
        surface: { DEFAULT: '#ffffff', hover: '#f7f9ff', zebra: '#ebeef3', dim: '#f7f9ff' },
        text: { primary: '#181c20', secondary: '#4c4452', muted: '#7d7483', faint: '#94a3b8' },
        border: { DEFAULT: '#e0e3e8', accent: '#cfc2d3', subtle: '#ebeef3' }
      }
    }
  },
  plugins: [forms, containerQueries],
};
