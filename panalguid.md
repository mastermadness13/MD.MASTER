<!DOCTYPE html>

<html dir="rtl" lang="ar"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>لوحة تخصيص المظهر والمعاينة الحية</title>
<!-- Google Fonts for Arabic -->
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Almarai:wght@400;700;800&amp;family=Cairo:wght@400;500;600;700;800&amp;family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&amp;family=Noto+Kufi+Arabic:wght@400;600;700&amp;family=Tajawal:wght@400;500;700;800&amp;display=swap" rel="stylesheet"/>
<!-- Material Symbols Outlined -->
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" rel="stylesheet"/>
<!-- Tailwind CSS CDN -->
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          fontFamily: {
            cairo: ['Cairo', 'sans-serif'],
            tajawal: ['Tajawal', 'sans-serif'],
            almarai: ['Almarai', 'sans-serif'],
            ibm: ['"IBM Plex Sans Arabic"', 'sans-serif'],
            noto: ['"Noto Kufi Arabic"', 'sans-serif'],
          }
        }
      }
    }
  </script>
<style>
    :root {
      --primary-hue: 280;
      --app-font: 'Cairo', system-ui, -apple-system, sans-serif;
      --app-font-size: 16px;
      --app-radius: 14px;
      --density-py: 1rem;
      --density-px: 1.25rem;
      --density-gap: 1.25rem;
      --accent-color: hsl(var(--primary-hue), 76%, 54%);
      --accent-light: hsla(var(--primary-hue), 76%, 54%, 0.12);
      --accent-border: hsla(var(--primary-hue), 76%, 54%, 0.3);
      --accent-hover: hsl(var(--primary-hue), 76%, 46%);

      /* Live Canvas Custom Palette Variables */
      --preview-bg: #f8fafc;
      --preview-card-bg: #ffffff;
      --preview-card-border: rgba(226, 232, 240, 0.9);
      --preview-nav-bg: #ffffff;
      --preview-border-color: rgba(226, 232, 240, 0.9);
      --preview-text-main: #0f172a;
      --preview-text-muted: #64748b;
      --preview-input-bg: #f1f5f9;
      --preview-subtle-bg: rgba(241, 245, 249, 0.85);

      /* Dynamic Button Theming */
      --btn-primary-bg: #7c3aed;
      --btn-primary-text: #ffffff;
      --btn-primary-border: transparent;
      --btn-primary-hover: #6d28d9;
      --btn-primary-shadow: 0 2px 6px -1px rgba(124, 58, 237, 0.35);
    }

    body {
      font-family: 'Cairo', system-ui, -apple-system, sans-serif;
    }

    .material-symbols-outlined {
      font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
      vertical-align: middle;
    }

    /* Live preview reactive styles */
    #liveCanvas {
      font-family: var(--app-font);
      font-size: var(--app-font-size);
      background-color: var(--preview-bg) !important;
      color: var(--preview-text-main) !important;
      border-color: var(--preview-border-color) !important;
      transition: all 0.25s ease;
    }

    #liveCanvas #liveNavbar {
      background-color: var(--preview-nav-bg) !important;
      border-color: var(--preview-border-color) !important;
    }

    #liveCanvas .preview-card {
      border-radius: var(--app-radius);
      padding: var(--density-py) var(--density-px);
      background-color: var(--preview-card-bg) !important;
      border-color: var(--preview-card-border) !important;
      color: var(--preview-text-main);
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    }

    #liveCanvas .preview-text-main {
      color: var(--preview-text-main) !important;
    }

    #liveCanvas .preview-text-muted {
      color: var(--preview-text-muted) !important;
    }

    #liveCanvas .preview-input-field {
      background-color: var(--preview-input-bg) !important;
      color: var(--preview-text-main) !important;
      border-color: var(--preview-border-color) !important;
    }

    #liveCanvas .preview-subtle-strip {
      background-color: var(--preview-subtle-bg) !important;
      border-color: var(--preview-border-color) !important;
    }

    #liveCanvas .preview-table-row {
      border-color: var(--preview-border-color) !important;
    }

    .preview-rounded {
      border-radius: var(--app-radius);
    }

    .preview-accent-bg {
      background-color: var(--accent-color) !important;
    }

    .preview-accent-text {
      color: var(--accent-color) !important;
    }

    .preview-accent-tint {
      background-color: var(--accent-light) !important;
    }

    .preview-accent-border {
      border-color: var(--accent-border) !important;
    }

    .preview-accent-ring:focus {
      outline: none;
      box-shadow: 0 0 0 3px var(--accent-border);
    }

    /* Live preview reactive buttons */
    .preview-btn-main {
      background-color: var(--btn-primary-bg) !important;
      color: var(--btn-primary-text) !important;
      border-color: var(--btn-primary-border) !important;
      box-shadow: var(--btn-primary-shadow) !important;
      transition: all 0.2s ease;
    }
    .preview-btn-main:hover {
      background-color: var(--btn-primary-hover) !important;
      opacity: 0.95;
    }

    .preview-btn-action-text {
      color: var(--btn-primary-bg) !important;
      transition: color 0.2s ease;
    }
    .preview-btn-action-text:hover {
      opacity: 0.8;
    }

    /* Gradient Hue Track */
    .hue-slider {
      background: linear-gradient(to left, 
        hsl(0, 85%, 55%),
        hsl(40, 95%, 50%),
        hsl(80, 80%, 45%),
        hsl(160, 80%, 40%),
        hsl(200, 90%, 48%),
        hsl(280, 80%, 55%),
        hsl(320, 85%, 55%),
        hsl(360, 85%, 55%)
      );
    }

    input[type=range] {
      accent-color: var(--accent-color);
    }

    /* Color picker input hidden trigger */
    input[type="color"]::-webkit-color-swatch-wrapper {
      padding: 0;
    }
    input[type="color"]::-webkit-color-swatch {
      border: none;
      border-radius: 9999px;
    }

    /* Custom subtle scrollbar */
    .custom-scrollbar::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }
    .custom-scrollbar::-webkit-scrollbar-track {
      background: transparent;
    }
    .custom-scrollbar::-webkit-scrollbar-thumb {
      background: rgba(148, 163, 184, 0.35);
      border-radius: 9999px;
    }
    .custom-scrollbar::-webkit-scrollbar-thumb:hover {
      background: rgba(148, 163, 184, 0.6);
    }

    /* Accordion styles */
    .accordion-content {
      max-height: 0;
      overflow: hidden;
      transition: max-height 0.3s cubic-bezier(0, 1, 0, 1), opacity 0.25s ease, padding 0.25s ease;
      opacity: 0;
    }
    .accordion-item.is-open .accordion-content {
      max-height: 380px;
      opacity: 1;
      transition: max-height 0.35s ease-in-out, opacity 0.25s ease, padding 0.25s ease;
    }
    .accordion-item.is-open .accordion-chevron {
      transform: rotate(180deg);
    }
    .accordion-item.is-open {
      border-color: rgba(168, 85, 247, 0.4);
      background-color: #ffffff;
      box-shadow: 0 4px 12px -2px rgba(124, 58, 237, 0.08);
    }
  </style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen flex flex-col antialiased selection:bg-purple-500 selection:text-white">
<!-- Top App Navigation Bar -->
<header class="h-16 border-b border-slate-800/80 bg-slate-900/90 backdrop-blur-md sticky top-0 z-30 px-4 sm:px-8 flex items-center justify-between">
<div class="flex items-center gap-3">
<div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-600 via-indigo-600 to-pink-500 flex items-center justify-center text-white shadow-lg shadow-purple-900/30">
<span class="material-symbols-outlined text-2xl">tune</span>
</div>
<div>
<h1 class="text-base font-bold text-slate-100 flex items-center gap-2">
          استوديو تخصيص واجهات النظام
          <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">إصدار 2.5 الحصري</span>
</h1>
<p class="text-xs text-slate-400 hidden sm:block">تحكم كامل بالمظهر مع نافذة محاكاة لحظية (Real-time Dual View)</p>
</div>
</div>
<!-- Quick Status Pills -->
<div class="flex items-center gap-3">
<div class="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/90 border border-slate-700/60 text-xs">
<span class="relative flex h-2.5 w-2.5">
<span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
<span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
</span>
<span class="text-slate-300">المزامنة الحية مفعلة</span>
</div>
<button class="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 hover:border-slate-600 transition-colors flex items-center gap-1.5" id="quickResetBtn" type="button">
<span class="material-symbols-outlined text-sm">refresh</span>
        إعادة ضبط
      </button>
</div>
</header>
<!-- Dual Layout Container -->
<main class="flex-1 w-full max-w-[1720px] mx-auto p-3 sm:p-5 lg:p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
<!-- ==========================================
         RIGHT PANEL: THEME SETTINGS (4 Cols)
         ========================================== -->
<aside class="lg:col-span-4 xl:col-span-4 w-full">
<div class="theme-panel relative w-full bg-white text-slate-800 rounded-2xl shadow-xl shadow-slate-950/20 border border-slate-200/90 overflow-hidden flex flex-col transition-all" id="themePanel">
<!-- Header -->
<div class="theme-panel-head flex items-center justify-between px-5 py-4 border-b border-slate-100 bg-slate-50/80">
<div class="flex items-center gap-2.5">
<span class="w-8 h-8 rounded-lg flex items-center justify-center text-white shadow-sm preview-accent-bg">
<span aria-hidden="true" class="material-symbols-outlined text-xl">palette</span>
</span>
<div>
<h2 class="theme-panel-title text-base font-bold text-slate-900" id="themePanelTitle">
                المظهر وتخصيص الواجهة
              </h2>
<p class="text-[11px] text-slate-500">خصّص الألوان والخطوط والبطاقات والأزرار فورياً</p>
</div>
</div>
<button class="theme-panel-close text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 p-1.5 rounded-full transition-all flex items-center justify-center" title="إغلاق اللوحة" type="button">
<span aria-hidden="true" class="material-symbols-outlined text-xl">close</span>
</button>
</div>
<!-- Scrollable Body -->
<div class="theme-panel-body p-5 space-y-4 overflow-y-auto max-h-[calc(100vh-14rem)] custom-scrollbar">
<!-- Fieldset: Mode Selection -->
<fieldset class="theme-fieldset border-none p-0 m-0">
<div class="flex items-center justify-between mb-2">
<legend class="theme-legend text-xs font-bold text-slate-600 uppercase tracking-wider">الوضع العام</legend>
<span class="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-purple-50 text-purple-700" id="activeModeBadge">نهاري</span>
</div>
<div class="theme-segmented grid grid-cols-4 gap-1.5 p-1 bg-slate-100 rounded-xl" role="radiogroup">
<label class="theme-option cursor-pointer">
<input checked="" class="theme-radio peer sr-only" name="theme-mode" type="radio" value="light"/>
<span class="theme-option-face flex flex-col items-center justify-center py-2 px-1 rounded-lg text-xs font-medium text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span aria-hidden="true" class="material-symbols-outlined text-lg mb-1">light_mode</span>
<span>نهاري</span>
</span>
</label>
<label class="theme-option cursor-pointer">
<input class="theme-radio peer sr-only" name="theme-mode" type="radio" value="dark"/>
<span class="theme-option-face flex flex-col items-center justify-center py-2 px-1 rounded-lg text-xs font-medium text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span aria-hidden="true" class="material-symbols-outlined text-lg mb-1">dark_mode</span>
<span>ليلي</span>
</span>
</label>
<label class="theme-option cursor-pointer">
<input class="theme-radio peer sr-only" name="theme-mode" type="radio" value="system"/>
<span class="theme-option-face flex flex-col items-center justify-center py-2 px-1 rounded-lg text-xs font-medium text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span aria-hidden="true" class="material-symbols-outlined text-lg mb-1">routine</span>
<span>تلقائي</span>
</span>
</label>
<label class="theme-option cursor-pointer">
<input class="theme-radio peer sr-only" name="theme-mode" type="radio" value="custom"/>
<span class="theme-option-face flex flex-col items-center justify-center py-2 px-1 rounded-lg text-xs font-medium text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span aria-hidden="true" class="material-symbols-outlined text-lg mb-1">palette</span>
<span>مخصص</span>
</span>
</label>
</div>
</fieldset>
<!-- ========================================================
     COLLAPSIBLE COLOR PALETTES ACCORDION CONTAINER
     Saves vertical space; expands smoothly on click.
======================================================== -->
<div class="space-y-2 pt-1" id="colorsAccordionGroup">
<div class="flex items-center justify-between pb-1 px-0.5">
<span class="text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
<span class="material-symbols-outlined text-sm text-purple-600">tune</span>
<span>لوحة الألوان المتقدمة</span>
</span>
<span class="text-[10px] text-slate-400 font-medium">اضغط لتخصيص الألوان</span>
</div>
<!-- Accordion 1: Accent Color -->
<div class="accordion-item border border-slate-200 rounded-xl bg-slate-50/70 transition-all overflow-hidden is-open" data-accordion="accent">
<button class="accordion-toggle w-full flex items-center justify-between px-3.5 py-2.5 text-right hover:bg-slate-100/60 transition-colors" type="button">
<div class="flex items-center gap-2.5">
<span class="w-6 h-6 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center">
<span class="material-symbols-outlined text-sm">palette</span>
</span>
<span class="text-xs font-bold text-slate-800">لون التمييز (Accent Color)</span>
</div>
<div class="flex items-center gap-2">
<span class="w-4 h-4 rounded-full border border-white shadow-sm" id="accordionAccentDot" style="background-color: hsl(280, 76%, 54%);"></span>
<output class="text-[11px] font-mono font-bold px-1.5 py-0.5 rounded preview-accent-tint preview-accent-text" id="themeHueValue">280°</output>
<span class="material-symbols-outlined text-slate-400 text-base accordion-chevron transition-transform duration-200">expand_more</span>
</div>
</button>
<div class="accordion-content">
<div class="p-3.5 pt-1.5 border-t border-slate-100/80 bg-white">
<div class="theme-hue-row flex items-center gap-3 mb-3">
<input aria-label="درجة لون التمييز" class="hue-slider w-full h-3 rounded-lg appearance-none cursor-pointer shadow-inner" id="themeHue" max="359" min="0" step="1" type="range" value="280"/>
</div>
<!-- Swatches -->
<div aria-label="ألوان جاهزة" class="theme-swatches grid grid-cols-6 gap-2" id="swatchesContainer" role="group">
<button aria-label="بنفسجي" class="theme-swatch group relative aspect-square rounded-full ring-2 ring-offset-2 ring-purple-600 transition-transform active:scale-95 shadow-sm flex items-center justify-center" data-hue="280" style="background-color: #7c3aed;" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark font-bold">check</span>
</button>
<button aria-label="أزرق" class="theme-swatch group relative aspect-square rounded-full hover:scale-105 transition-transform active:scale-95 shadow-sm flex items-center justify-center" data-hue="220" style="background-color: #2563eb;" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="أخضر مزرق" class="theme-swatch group relative aspect-square rounded-full hover:scale-105 transition-transform active:scale-95 shadow-sm flex items-center justify-center" data-hue="172" style="background-color: #0d9488;" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="برتقالي" class="theme-swatch group relative aspect-square rounded-full hover:scale-105 transition-transform active:scale-95 shadow-sm flex items-center justify-center" data-hue="38" style="background-color: #d97706;" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="أحمر" class="theme-swatch group relative aspect-square rounded-full hover:scale-105 transition-transform active:scale-95 shadow-sm flex items-center justify-center" data-hue="350" style="background-color: #e11d48;" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="رمادي كحلي" class="theme-swatch group relative aspect-square rounded-full hover:scale-105 transition-transform active:scale-95 shadow-sm flex items-center justify-center" data-hue="215" style="background-color: #475569;" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
</div>
</div>
</div>
</div>
<!-- Accordion 2: Cards & Boards -->
<div class="accordion-item border border-slate-200 rounded-xl bg-slate-50/70 transition-all overflow-hidden" data-accordion="cards">
<button class="accordion-toggle w-full flex items-center justify-between px-3.5 py-2.5 text-right hover:bg-slate-100/60 transition-colors" type="button">
<div class="flex items-center gap-2.5">
<span class="w-6 h-6 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center">
<span class="material-symbols-outlined text-sm">view_compact_alt</span>
</span>
<span class="text-xs font-bold text-slate-800">ألوان اللوحات والبطاقات (Cards)</span>
</div>
<div class="flex items-center gap-2">
<span class="w-4 h-4 rounded-full border border-slate-300 shadow-sm" id="accordionCardDot" style="background-color: #ffffff;"></span>
<output class="text-[11px] font-mono font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600" id="cardHexLabel">#ffffff</output>
<span class="material-symbols-outlined text-slate-400 text-base accordion-chevron transition-transform duration-200">expand_more</span>
</div>
</button>
<div class="accordion-content">
<div class="p-3.5 pt-2 border-t border-slate-100/80 bg-white">
<div class="grid grid-cols-6 gap-2 items-center" id="cardSwatchesContainer" role="group">
<!-- White Card -->
<button aria-label="أبيض ناصع" class="card-swatch relative aspect-square rounded-xl border-2 border-purple-600 ring-2 ring-purple-600/30 transition-all shadow-sm flex items-center justify-center" data-border="#e2e8f0" data-card="#ffffff" style="background-color: #ffffff;" title="أبيض ناصع" type="button">
<span class="material-symbols-outlined text-slate-800 text-sm checkmark font-bold">check</span>
</button>
<!-- Light Soft Cream -->
<button aria-label="كريمي دافئ" class="card-swatch relative aspect-square rounded-xl border-2 border-slate-200 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-border="#f1ece1" data-card="#fffdfa" style="background-color: #fffdfa;" title="كريمي ناعم" type="button">
<span class="material-symbols-outlined text-amber-900 text-sm checkmark hidden font-bold">check</span>
</button>
<!-- Muted Grey / Subtle -->
<button aria-label="رمادي هادئ" class="card-swatch relative aspect-square rounded-xl border-2 border-slate-200 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-border="#e2e8f0" data-card="#f8fafc" style="background-color: #f8fafc;" title="رمادي هادئ" type="button">
<span class="material-symbols-outlined text-slate-700 text-sm checkmark hidden font-bold">check</span>
</button>
<!-- Ice / Blue Subtle Tint -->
<button aria-label="سماوي ثلجي" class="card-swatch relative aspect-square rounded-xl border-2 border-slate-200 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-border="#bfdbfe" data-card="#f0f7ff" style="background-color: #f0f7ff;" title="سماوي ثلجي" type="button">
<span class="material-symbols-outlined text-sky-800 text-sm checkmark hidden font-bold">check</span>
</button>
<!-- Slate Dark Card -->
<button aria-label="كحلي داكن" class="card-swatch relative aspect-square rounded-xl border-2 border-slate-700 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-border="#334155" data-card="#1e293b" style="background-color: #1e293b;" title="كحلي داكن" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<!-- Custom Color Picker for Cards -->
<label class="relative aspect-square rounded-xl border-2 border-dashed border-slate-300 hover:border-purple-500 bg-slate-50 hover:bg-purple-50/50 flex flex-col items-center justify-center cursor-pointer transition-all group" title="اختيار لون لوحة مخصص">
<span class="material-symbols-outlined text-slate-500 group-hover:text-purple-600 text-base">palette</span>
<input class="sr-only" id="customCardPicker" type="color" value="#ffffff"/>
</label>
</div>
</div>
</div>
</div>
<!-- Accordion 3: Buttons Color & Style -->
<div class="accordion-item border border-slate-200 rounded-xl bg-slate-50/70 transition-all overflow-hidden" data-accordion="buttons">
<button class="accordion-toggle w-full flex items-center justify-between px-3.5 py-2.5 text-right hover:bg-slate-100/60 transition-colors" type="button">
<div class="flex items-center gap-2.5">
<span class="w-6 h-6 rounded-lg bg-pink-100 text-pink-700 flex items-center justify-center">
<span class="material-symbols-outlined text-sm">smart_button</span>
</span>
<span class="text-xs font-bold text-slate-800">ألوان وتنسيق الأزرار (Buttons)</span>
</div>
<div class="flex items-center gap-2">
<span class="w-4 h-4 rounded-full border border-white shadow-sm" id="accordionBtnDot" style="background-color: #7c3aed;"></span>
<output class="text-[11px] font-mono font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600" id="btnHexLabel">#7c3aed</output>
<span class="material-symbols-outlined text-slate-400 text-base accordion-chevron transition-transform duration-200">expand_more</span>
</div>
</button>
<div class="accordion-content">
<div class="p-3.5 pt-2 border-t border-slate-100/80 bg-white">
<!-- Button Style Variants -->
<div class="theme-segmented grid grid-cols-3 gap-1.5 p-1 bg-slate-100 rounded-xl mb-2.5" role="radiogroup">
<label class="theme-option cursor-pointer">
<input checked="" class="peer sr-only" name="btn-style" type="radio" value="filled"/>
<span class="theme-option-face flex items-center justify-center py-1.5 px-2 rounded-lg text-xs font-semibold text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span>صلب (Filled)</span>
</span>
</label>
<label class="theme-option cursor-pointer">
<input class="peer sr-only" name="btn-style" type="radio" value="subtle"/>
<span class="theme-option-face flex items-center justify-center py-1.5 px-2 rounded-lg text-xs font-semibold text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span>ناعم (Subtle)</span>
</span>
</label>
<label class="theme-option cursor-pointer">
<input class="peer sr-only" name="btn-style" type="radio" value="outline"/>
<span class="theme-option-face flex items-center justify-center py-1.5 px-2 rounded-lg text-xs font-semibold text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span>مفرغ (Outline)</span>
</span>
</label>
</div>
<!-- Button Color Swatches Presets -->
<div class="grid grid-cols-7 gap-2 items-center" id="btnColorSwatchesContainer" role="group">
<button aria-label="بنفسجي أساسي" class="btn-color-swatch relative aspect-square rounded-xl border-2 border-purple-600 ring-2 ring-purple-600/30 transition-all shadow-sm flex items-center justify-center" data-btn-color="#7c3aed" data-btn-hover="#6d28d9" style="background-color: #7c3aed;" title="بنفسجي نابض" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark font-bold">check</span>
</button>
<button aria-label="أسود داكن" class="btn-color-swatch relative aspect-square rounded-xl border-2 border-slate-300 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-btn-color="#0f172a" data-btn-hover="#1e293b" style="background-color: #0f172a;" title="أسود كحلي صلب" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="أزرق نيلي" class="btn-color-swatch relative aspect-square rounded-xl border-2 border-slate-300 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-btn-color="#2563eb" data-btn-hover="#1d4ed8" style="background-color: #2563eb;" title="أزرق نيلي" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="أخضر زمردي" class="btn-color-swatch relative aspect-square rounded-xl border-2 border-slate-300 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-btn-color="#059669" data-btn-hover="#047857" style="background-color: #059669;" title="أخضر زمردي" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="أحمر قرمزي" class="btn-color-swatch relative aspect-square rounded-xl border-2 border-slate-300 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-btn-color="#e11d48" data-btn-hover="#be123c" style="background-color: #e11d48;" title="أحمر قرمزي" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="برتقالي مالي" class="btn-color-swatch relative aspect-square rounded-xl border-2 border-slate-300 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-btn-color="#ea580c" data-btn-hover="#c2410c" style="background-color: #ea580c;" title="برتقالي ناري" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<!-- Custom Button Color Picker -->
<label class="relative aspect-square rounded-xl border-2 border-dashed border-slate-300 hover:border-purple-500 bg-slate-50 hover:bg-purple-50/50 flex flex-col items-center justify-center cursor-pointer transition-all group" title="تحديد لون زر مخصص">
<span class="material-symbols-outlined text-slate-500 group-hover:text-purple-600 text-base">colorize</span>
<input class="sr-only" id="customBtnColorPicker" type="color" value="#7c3aed"/>
</label>
</div>
</div>
</div>
</div>
<!-- Accordion 4: Background Color -->
<div class="accordion-item border border-slate-200 rounded-xl bg-slate-50/70 transition-all overflow-hidden" data-accordion="background">
<button class="accordion-toggle w-full flex items-center justify-between px-3.5 py-2.5 text-right hover:bg-slate-100/60 transition-colors" type="button">
<div class="flex items-center gap-2.5">
<span class="w-6 h-6 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center">
<span class="material-symbols-outlined text-sm">wallpaper</span>
</span>
<span class="text-xs font-bold text-slate-800">لون الخلفية (Background)</span>
</div>
<div class="flex items-center gap-2">
<span class="w-4 h-4 rounded-full border border-slate-300 shadow-sm" id="accordionBgDot" style="background-color: #f8fafc;"></span>
<output class="text-[11px] font-mono font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600" id="bgHexLabel">#f8fafc</output>
<span class="material-symbols-outlined text-slate-400 text-base accordion-chevron transition-transform duration-200">expand_more</span>
</div>
</button>
<div class="accordion-content">
<div class="p-3.5 pt-2 border-t border-slate-100/80 bg-white">
<div class="grid grid-cols-7 gap-2 items-center" id="bgSwatchesContainer" role="group">
<button aria-label="أبيض ناصع" class="bg-swatch relative aspect-square rounded-xl border-2 border-slate-200 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-bg="#ffffff" data-border="#e2e8f0" data-card="#f8fafc" data-nav="#ffffff" data-theme="light" style="background-color: #ffffff;" title="أبيض ناصع" type="button">
<span class="material-symbols-outlined text-slate-700 text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="رمادي سحابي فاتح" class="bg-swatch relative aspect-square rounded-xl border-2 border-purple-600 ring-2 ring-purple-600/30 transition-all shadow-sm flex items-center justify-center" data-bg="#f8fafc" data-border="#e2e8f0" data-card="#ffffff" data-nav="#ffffff" data-theme="light" style="background-color: #f8fafc;" title="رمادي هادئ" type="button">
<span class="material-symbols-outlined text-slate-700 text-sm checkmark font-bold">check</span>
</button>
<button aria-label="كريمي دافئ" class="bg-swatch relative aspect-square rounded-xl border-2 border-amber-100 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-bg="#fcfbf7" data-border="#e7e5e4" data-card="#ffffff" data-nav="#ffffff" data-theme="light" style="background-color: #fcfbf7;" title="كريمي دافئ" type="button">
<span class="material-symbols-outlined text-stone-700 text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="أزرق ثلجي فاتح" class="bg-swatch relative aspect-square rounded-xl border-2 border-sky-100 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-bg="#f0f9ff" data-border="#bae6fd" data-card="#ffffff" data-nav="#ffffff" data-theme="light" style="background-color: #f0f9ff;" title="أزرق ثلجي" type="button">
<span class="material-symbols-outlined text-sky-800 text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="كحلي عميق" class="bg-swatch relative aspect-square rounded-xl border-2 border-slate-700 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-bg="#0f172a" data-border="#334155" data-card="#1e293b" data-nav="#0f172a" data-theme="dark" style="background-color: #0f172a;" title="كحلي عميق" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="فحمي داكن" class="bg-swatch relative aspect-square rounded-xl border-2 border-zinc-700 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-bg="#18181b" data-border="#3f3f46" data-card="#27272a" data-nav="#18181b" data-theme="dark" style="background-color: #18181b;" title="فحمي داكن" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<!-- Custom Color Picker -->
<label class="relative aspect-square rounded-xl border-2 border-dashed border-slate-300 hover:border-purple-500 bg-slate-50 hover:bg-purple-50/50 flex flex-col items-center justify-center cursor-pointer transition-all group" title="اختيار لون خلفية مخصص">
<span class="material-symbols-outlined text-slate-500 group-hover:text-purple-600 text-base">colorize</span>
<input class="sr-only" id="customBgPicker" type="color" value="#f8fafc"/>
</label>
</div>
</div>
</div>
</div>
<!-- Accordion 5: Text Color & Contrast -->
<div class="accordion-item border border-slate-200 rounded-xl bg-slate-50/70 transition-all overflow-hidden" data-accordion="text">
<button class="accordion-toggle w-full flex items-center justify-between px-3.5 py-2.5 text-right hover:bg-slate-100/60 transition-colors" type="button">
<div class="flex items-center gap-2.5">
<span class="w-6 h-6 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center">
<span class="material-symbols-outlined text-sm">format_color_text</span>
</span>
<span class="text-xs font-bold text-slate-800">لون النصوص والتباين (Text)</span>
</div>
<div class="flex items-center gap-2">
<span class="w-4 h-4 rounded-full border border-slate-300 shadow-sm" id="accordionTextDot" style="background-color: #0f172a;"></span>
<output class="text-[11px] font-mono font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600" id="textHexLabel">#0f172a</output>
<span class="material-symbols-outlined text-slate-400 text-base accordion-chevron transition-transform duration-200">expand_more</span>
</div>
</button>
<div class="accordion-content">
<div class="p-3.5 pt-2 border-t border-slate-100/80 bg-white">
<div class="flex items-center justify-between mb-2">
<span class="text-[11px] text-slate-500">مقياس التباين والقراءة:</span>
<span class="text-[10px] font-semibold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200" id="contrastBadge">تباين ممتاز AAA</span>
</div>
<div class="grid grid-cols-6 gap-2 items-center" id="textSwatchesContainer" role="group">
<button aria-label="أسود عميق" class="text-swatch relative aspect-square rounded-xl border-2 border-purple-600 ring-2 ring-purple-600/30 transition-all shadow-sm flex items-center justify-center" data-color="#0f172a" data-muted="#64748b" style="background-color: #0f172a;" title="أسود كحلي عميق" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark font-bold">check</span>
</button>
<button aria-label="رمادي حيادي داكن" class="text-swatch relative aspect-square rounded-xl border-2 border-slate-300 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-color="#334155" data-muted="#64748b" style="background-color: #334155;" title="رمادي داكن" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="فحمي ناعم" class="text-swatch relative aspect-square rounded-xl border-2 border-slate-300 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-color="#475569" data-muted="#94a3b8" style="background-color: #475569;" title="فحمي ناعم" type="button">
<span class="material-symbols-outlined text-white text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="رمادي فاتح" class="text-swatch relative aspect-square rounded-xl border-2 border-slate-300 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-color="#cbd5e1" data-muted="#94a3b8" style="background-color: #cbd5e1;" title="رمادي فاتح" type="button">
<span class="material-symbols-outlined text-slate-800 text-sm checkmark hidden font-bold">check</span>
</button>
<button aria-label="أبيض نقي" class="text-swatch relative aspect-square rounded-xl border-2 border-slate-300 hover:border-purple-400 transition-all shadow-sm flex items-center justify-center" data-color="#ffffff" data-muted="#94a3b8" style="background-color: #ffffff;" title="أبيض نقي (للشاشات الداكنة)" type="button">
<span class="material-symbols-outlined text-slate-900 text-sm checkmark hidden font-bold">check</span>
</button>
<!-- Custom Text Color Picker -->
<label class="relative aspect-square rounded-xl border-2 border-dashed border-slate-300 hover:border-purple-500 bg-slate-50 hover:bg-purple-50/50 flex flex-col items-center justify-center cursor-pointer transition-all group" title="تحديد لون نص مخصص">
<span class="material-symbols-outlined text-slate-500 group-hover:text-purple-600 text-base">format_paint</span>
<input class="sr-only" id="customTextColorPicker" type="color" value="#0f172a"/>
</label>
</div>
</div>
</div>
</div>
</div>
<!-- Typography Section (Font Family & Prominent Font Size Control) -->
<div class="p-3.5 bg-slate-50/80 rounded-xl border border-slate-200/80 space-y-3.5">
<!-- Font Family Fieldset -->
<fieldset class="theme-fieldset border-none p-0 m-0">
<div class="flex items-center justify-between mb-1.5">
<legend class="theme-legend text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
<span class="material-symbols-outlined text-sm text-purple-600">font_download</span>
<span>نوع الخط العربي</span>
</legend>
</div>
<div class="relative">
<select class="w-full appearance-none bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-xs font-semibold text-slate-800 hover:border-slate-300 focus:outline-none preview-accent-ring transition-all cursor-pointer shadow-sm" id="themeFontSelect">
<option selected="" value="Cairo">Cairo (القاهرة) - عصري ومتوازن</option>
<option value="Tajawal">Tajawal (تجوال) - أنيق ومقروء</option>
<option value="Almarai">Almarai (المراعي) - هندسي وواضح</option>
<option value="IBM Plex Sans Arabic">IBM Plex Sans Arabic - تقني ومتقن</option>
<option value="Noto Kufi Arabic">Noto Kufi Arabic - كوفي معاصر</option>
</select>
<div class="pointer-events-none absolute inset-y-0 left-0 flex items-center px-3 text-slate-400">
<span class="material-symbols-outlined text-base">expand_more</span>
</div>
</div>
</fieldset>
<!-- Font Size Fieldset (PROMINENT CONTROL) -->
<fieldset class="theme-fieldset border-none p-0 m-0">
<div class="flex items-center justify-between mb-1.5">
<legend class="theme-legend text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
<span class="material-symbols-outlined text-sm text-purple-600">format_size</span>
<span>حجم الخط الأساسي (Font Size)</span>
</legend>
<output class="theme-font-size-value text-xs font-mono font-bold text-purple-700 bg-purple-50 border border-purple-200/60 px-2 py-0.5 rounded-md" id="themeFontSizeValue">16 px</output>
</div>
<div class="theme-font-size-row flex items-center gap-2.5 bg-white p-2 rounded-xl border border-slate-200/80 shadow-sm">
<span class="text-xs font-bold text-slate-400 px-1 select-none">A-</span>
<input class="w-full h-2 rounded-lg bg-slate-200 appearance-none cursor-pointer" id="themeFontSize" max="22" min="12" step="0.5" type="range" value="16"/>
<span class="text-sm font-bold text-slate-700 px-1 select-none">A+</span>
</div>
</fieldset>
</div>
<!-- Density Fieldset -->
<fieldset class="theme-fieldset border-none p-0 m-0">
<legend class="theme-legend text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">كثافة العناصر وتباعدها</legend>
<div class="theme-segmented grid grid-cols-2 gap-2 p-1 bg-slate-100 rounded-xl">
<label class="theme-option cursor-pointer">
<input checked="" class="peer sr-only" name="theme-density" type="radio" value="comfortable"/>
<span class="theme-option-face flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-semibold text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span class="material-symbols-outlined text-sm">view_agenda</span>
<span>مريح (واسع)</span>
</span>
</label>
<label class="theme-option cursor-pointer">
<input class="peer sr-only" name="theme-density" type="radio" value="compact"/>
<span class="theme-option-face flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-semibold text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span class="material-symbols-outlined text-sm">density_medium</span>
<span>مضغوط (مكثف)</span>
</span>
</label>
</div>
</fieldset>
<!-- Corner Radius Fieldset -->
<fieldset class="theme-fieldset border-none p-0 m-0">
<legend class="theme-legend text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">استدارة الحواف</legend>
<div class="theme-segmented grid grid-cols-3 gap-1.5 p-1 bg-slate-100 rounded-xl">
<label class="theme-option cursor-pointer">
<input checked="" class="peer sr-only" name="theme-corner" type="radio" value="soft"/>
<span class="theme-option-face flex items-center justify-center py-2 px-2 rounded-lg text-xs font-semibold text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span>ناعم (14px)</span>
</span>
</label>
<label class="theme-option cursor-pointer">
<input class="peer sr-only" name="theme-corner" type="radio" value="sharp"/>
<span class="theme-option-face flex items-center justify-center py-2 px-2 rounded-lg text-xs font-semibold text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span>حاد (4px)</span>
</span>
</label>
<label class="theme-option cursor-pointer">
<input class="peer sr-only" name="theme-corner" type="radio" value="round"/>
<span class="theme-option-face flex items-center justify-center py-2 px-2 rounded-lg text-xs font-semibold text-slate-600 transition-all peer-checked:bg-white peer-checked:text-purple-700 peer-checked:font-bold peer-checked:shadow-sm hover:text-slate-900">
<span>دائري (24px)</span>
</span>
</label>
</div>
</fieldset>
</div>
<!-- Footer Action -->
<div class="theme-panel-foot flex items-center justify-between px-5 py-3.5 bg-slate-50 border-t border-slate-100">
<button class="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 rounded-lg transition-colors" id="resetDefaultsBtn" type="button">
<span class="material-symbols-outlined text-base">restart_alt</span>
            استعادة الافتراضي
          </button>
<button class="preview-accent-bg text-white inline-flex items-center gap-1.5 px-4 py-2 text-xs font-bold rounded-lg shadow-sm hover:opacity-90 active:scale-95 transition-all" id="applyNotificationBtn" type="button">
<span class="material-symbols-outlined text-sm">done_all</span>
<span>تطبيق الإعدادات</span>
</button>
</div>
</div>
<!-- Quick Tips Card -->
<div class="mt-4 p-4 rounded-xl bg-slate-800/60 border border-slate-700/60 text-slate-400 text-xs flex items-start gap-3">
<span class="material-symbols-outlined text-purple-400 text-lg flex-shrink-0 mt-0.5">tips_and_updates</span>
<p class="leading-relaxed">
          تم تجميع خيارات الألوان في قوائم منسدلة أنيقة لتوفير المساحة وسهولة التصفح. انقر على أي قسم لفتحه أو إغلاقه مع انعكاس لحظي في شاشة المعاينة.
        </p>
</div>
</aside>
<!-- ==========================================
         LEFT PANEL: LIVE DASHBOARD PREVIEW CANVAS (8 Cols)
         ========================================== -->
<section class="lg:col-span-8 xl:col-span-8 w-full flex flex-col gap-3">
<!-- Preview Header Indicator Bar -->
<div class="flex items-center justify-between px-4 py-2.5 bg-slate-800/80 backdrop-blur-md rounded-xl border border-slate-700/70">
<div class="flex items-center gap-2.5">
<div class="flex items-center gap-1.5">
<span class="w-3 h-3 rounded-full bg-red-500/80 inline-block"></span>
<span class="w-3 h-3 rounded-full bg-amber-500/80 inline-block"></span>
<span class="w-3 h-3 rounded-full bg-emerald-500/80 inline-block"></span>
</div>
<span class="text-xs font-bold text-slate-200 flex items-center gap-1.5 border-r border-slate-700 pr-3 mr-1">
<span class="material-symbols-outlined text-purple-400 text-sm">visibility</span>
            معاينة حية ومباشرة (Live Preview Canvas)
          </span>
</div>
<div class="flex items-center gap-2">
<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            متصل باللوحة
          </span>
<span class="text-[11px] text-slate-400 hidden sm:inline-block" id="canvasModeLabel">الوضع: نهاري</span>
</div>
</div>
<!-- Live Mockup Window Container -->
<div class="w-full rounded-2xl shadow-2xl border overflow-hidden flex flex-col transition-colors duration-300" id="liveCanvas">
<!-- Live App Nav -->
<nav class="px-5 py-3.5 border-b flex items-center justify-between gap-4 transition-colors" id="liveNavbar">
<div class="flex items-center gap-3">
<div class="w-9 h-9 preview-rounded preview-btn-main flex items-center justify-center font-bold shadow-md">
<span class="material-symbols-outlined text-lg">space_dashboard</span>
</div>
<div>
<span class="font-bold text-sm block leading-tight preview-text-main" id="liveBrandTitle">منصة الإدارة الذكية</span>
<span class="text-[11px] preview-text-muted">نظام تخطيط الموارد 2025</span>
</div>
</div>
<!-- App Search Box -->
<div class="hidden sm:flex items-center flex-1 max-w-xs relative mx-4">
<span class="material-symbols-outlined absolute right-3 preview-text-muted text-base">search</span>
<input class="preview-input-field w-full pl-3 pr-9 py-1.5 text-xs rounded-lg preview-accent-ring transition-all outline-none border" placeholder="البحث في العمليات، الفواتير..." type="text"/>
</div>
<!-- User & Action items -->
<div class="flex items-center gap-2 sm:gap-3">
<button class="w-8 h-8 rounded-lg preview-text-muted hover:opacity-80 flex items-center justify-center relative transition-colors" title="الإشعارات" type="button">
<span class="material-symbols-outlined text-lg">notifications</span>
<span class="absolute top-1.5 right-1.5 w-2 h-2 preview-btn-main rounded-full"></span>
</button>
<button class="w-8 h-8 rounded-lg preview-text-muted hover:opacity-80 flex items-center justify-center transition-colors" title="الرسائل" type="button">
<span class="material-symbols-outlined text-lg">mail</span>
</button>
<div class="flex items-center gap-2 mr-1 pr-2 border-r preview-table-row">
<div class="w-8 h-8 rounded-full preview-btn-main flex items-center justify-center font-bold text-xs ring-2 ring-slate-200/50">
                س.م
              </div>
<div class="hidden md:block text-right">
<p class="text-xs font-bold leading-tight preview-text-main">سارة المنصور</p>
<p class="text-[10px] preview-text-muted">مديرة المشروعات</p>
</div>
</div>
</div>
</nav>
<!-- Live App Body Content -->
<div class="p-5 sm:p-6 space-y-6">
<!-- Welcome Banner -->
<div class="preview-card border shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
<div>
<div class="flex items-center gap-2 mb-1">
<span class="text-xs font-semibold px-2 py-0.5 rounded-md preview-accent-tint preview-accent-text" id="liveWelcomeBadge">لوحة التحكم التنفيذية</span>
<span class="text-xs preview-text-muted">تحديث فوري منذ دقيقتين</span>
</div>
<h3 class="text-lg font-bold preview-text-main leading-snug">أهلاً بك مجدداً، سارة! إليك نظرة سريعة على مؤشرات اليوم</h3>
<p class="text-xs preview-text-muted mt-0.5">النظام يعمل بكفاءة 99.98% مع تحقيق 84% من أهداف الربع الحالي.</p>
</div>
<div class="flex items-center gap-2.5 w-full md:w-auto">
<button class="preview-rounded px-3.5 py-2 text-xs font-bold preview-btn-main shadow-sm flex items-center justify-center gap-1.5 w-full md:w-auto" type="button">
<span class="material-symbols-outlined text-sm">add_circle</span>
<span>مشروع جديد</span>
</button>
<button class="preview-rounded px-3.5 py-2 text-xs font-semibold preview-input-field preview-text-main hover:opacity-80 transition-all flex items-center justify-center gap-1 border" type="button">
<span class="material-symbols-outlined text-sm">file_download</span>
<span>تصدير</span>
</button>
</div>
</div>
<!-- Quick Metrics Cards (3 Cards) -->
<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
<!-- Metric 1 -->
<div class="preview-card border shadow-sm hover:shadow-md transition-shadow">
<div class="flex items-center justify-between mb-3">
<span class="text-xs font-medium preview-text-muted">إجمالي المبيعات الشهرية</span>
<div class="w-8 h-8 rounded-lg preview-accent-tint preview-accent-text flex items-center justify-center">
<span class="material-symbols-outlined text-base">payments</span>
</div>
</div>
<div class="flex items-baseline justify-between">
<span class="text-2xl font-extrabold preview-text-main tracking-tight">142,850 <span class="text-xs font-semibold preview-text-muted">ر.س</span></span>
<span class="text-xs font-bold text-emerald-600 bg-emerald-500/10 px-1.5 py-0.5 rounded flex items-center">
<span class="material-symbols-outlined text-xs">trending_up</span> +14.2%
                </span>
</div>
<!-- Mini Progress Bar -->
<div class="w-full bg-slate-200/50 dark:bg-slate-700/50 h-1.5 rounded-full mt-3 overflow-hidden">
<div class="h-full preview-btn-main rounded-full" style="width: 78%"></div>
</div>
</div>
<!-- Metric 2 -->
<div class="preview-card border shadow-sm hover:shadow-md transition-shadow">
<div class="flex items-center justify-between mb-3">
<span class="text-xs font-medium preview-text-muted">العملاء النشطون</span>
<div class="w-8 h-8 rounded-lg bg-sky-500/15 text-sky-500 flex items-center justify-center">
<span class="material-symbols-outlined text-base">group</span>
</div>
</div>
<div class="flex items-baseline justify-between">
<span class="text-2xl font-extrabold preview-text-main tracking-tight">3,420 <span class="text-xs font-semibold preview-text-muted">مستخدم</span></span>
<span class="text-xs font-bold text-emerald-600 bg-emerald-500/10 px-1.5 py-0.5 rounded flex items-center">
<span class="material-symbols-outlined text-xs">trending_up</span> +8.5%
                </span>
</div>
<div class="w-full bg-slate-200/50 dark:bg-slate-700/50 h-1.5 rounded-full mt-3 overflow-hidden">
<div class="h-full bg-sky-500 rounded-full" style="width: 64%"></div>
</div>
</div>
<!-- Metric 3 -->
<div class="preview-card border shadow-sm hover:shadow-md transition-shadow">
<div class="flex items-center justify-between mb-3">
<span class="text-xs font-medium preview-text-muted">معدل الإنجاز والمهام</span>
<div class="w-8 h-8 rounded-lg bg-amber-500/15 text-amber-500 flex items-center justify-center">
<span class="material-symbols-outlined text-base">task_alt</span>
</div>
</div>
<div class="flex items-baseline justify-between">
<span class="text-2xl font-extrabold preview-text-main tracking-tight">94.8%</span>
<span class="text-xs font-bold text-amber-600 bg-amber-500/10 px-1.5 py-0.5 rounded flex items-center">
<span class="material-symbols-outlined text-xs">done</span> ممتاز
                </span>
</div>
<div class="w-full bg-slate-200/50 dark:bg-slate-700/50 h-1.5 rounded-full mt-3 overflow-hidden">
<div class="h-full bg-amber-500 rounded-full" style="width: 94%"></div>
</div>
</div>
</div>
<!-- Split Content: Table & Interactive Form Widget -->
<div class="grid grid-cols-1 lg:grid-cols-12 gap-5">
<!-- Activity Table (7 Cols) -->
<div class="preview-card lg:col-span-7 border shadow-sm flex flex-col justify-between">
<div>
<div class="flex items-center justify-between mb-4">
<div>
<h4 class="text-sm font-bold preview-text-main">سجل المعاملات والعمليات الأخيرة</h4>
<p class="text-[11px] preview-text-muted">أحدث الأنشطة المسجلة في النظام اليوم</p>
</div>
<span class="material-symbols-outlined preview-text-muted text-lg cursor-pointer hover:opacity-80">more_horiz</span>
</div>
<div class="overflow-x-auto">
<table class="w-full text-right text-xs">
<thead>
<tr class="preview-text-muted border-b preview-table-row">
<th class="pb-2 font-medium">العميل / المعاملة</th>
<th class="pb-2 font-medium">الحالة</th>
<th class="pb-2 font-medium">المبلغ</th>
<th class="pb-2 font-medium">الإجراء</th>
</tr>
</thead>
<tbody class="divide-y preview-table-row">
<tr>
<td class="py-2.5">
<div class="font-bold preview-text-main">شركة التقنية المتقدمة</div>
<span class="text-[10px] preview-text-muted">تجديد اشتراك سحابي</span>
</td>
<td class="py-2.5">
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-600">مكتمل</span>
</td>
<td class="py-2.5 font-bold preview-text-main">12,400 ر.س</td>
<td class="py-2.5">
<button class="preview-btn-action-text hover:underline font-semibold text-xs" type="button">عرض</button>
</td>
</tr>
<tr>
<td class="py-2.5">
<div class="font-bold preview-text-main">مؤسسة الأفق للاستشارات</div>
<span class="text-[10px] preview-text-muted">دفعة أولى لمشروع رقمي</span>
</td>
<td class="py-2.5">
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold preview-accent-tint preview-accent-text">قيد المعالجة</span>
</td>
<td class="py-2.5 font-bold preview-text-main">28,500 ر.س</td>
<td class="py-2.5">
<button class="preview-btn-action-text hover:underline font-semibold text-xs" type="button">عرض</button>
</td>
</tr>
<tr>
<td class="py-2.5">
<div class="font-bold preview-text-main">متجر الريادة الرقمي</div>
<span class="text-[10px] preview-text-muted">ترقية الباقة الاحترافية</span>
</td>
<td class="py-2.5">
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-600">مكتمل</span>
</td>
<td class="py-2.5 font-bold preview-text-main">4,900 ر.س</td>
<td class="py-2.5">
<button class="preview-btn-action-text hover:underline font-semibold text-xs" type="button">عرض</button>
</td>
</tr>
</tbody>
</table>
</div>
</div>
<!-- Pagination / Foot -->
<div class="pt-3 mt-2 border-t preview-table-row flex items-center justify-between text-[11px] preview-text-muted">
<span>عرض 3 من أصل 48 معاملة</span>
<a class="preview-btn-action-text font-bold hover:underline" href="#more">عرض الكل ←</a>
</div>
</div>
<!-- Quick Action Interactive Form (5 Cols) -->
<div class="preview-card lg:col-span-5 border shadow-sm flex flex-col justify-between">
<div>
<h4 class="text-sm font-bold preview-text-main mb-1">إرسال تنبيه أو رسالة سريعة</h4>
<p class="text-[11px] preview-text-muted mb-3">تطبيق فوري لخيارات استدارة الحواف وتدرج الألوان</p>
<div class="space-y-3">
<div>
<label class="block text-xs font-semibold preview-text-muted mb-1">المستلم أو المجموعة</label>
<input class="preview-rounded preview-input-field w-full border px-3 py-2 text-xs preview-accent-ring outline-none" type="text" value="فريق التطوير والواجهات"/>
</div>
<div>
<label class="block text-xs font-semibold preview-text-muted mb-1">ملاحظة سريعة</label>
<textarea class="preview-rounded preview-input-field w-full border p-2.5 text-xs preview-accent-ring outline-none resize-none" rows="2">تم اعتماد التصميم الجديد بنجاح!</textarea>
</div>
</div>
</div>
<div class="pt-3 mt-3 border-t preview-table-row flex items-center gap-2">
<button class="preview-rounded flex-1 py-2 text-xs font-bold preview-btn-main hover:opacity-95 transition-opacity text-center shadow-sm" type="button">
                  إرسال الرسالة
                </button>
<button class="preview-rounded px-3 py-2 text-xs font-semibold preview-input-field preview-text-muted hover:opacity-80 transition-colors border" type="button">
                  إلغاء
                </button>
</div>
</div>
</div>
<!-- Interactive Component Sample Strip -->
<div class="preview-card preview-subtle-strip border flex flex-wrap items-center justify-between gap-3 text-xs">
<div class="flex items-center gap-2">
<span class="material-symbols-outlined preview-btn-action-text text-lg">check_circle</span>
<span class="font-bold preview-text-main">عينة عناصر واجهة المستخدم:</span>
</div>
<div class="flex flex-wrap items-center gap-2">
<button class="preview-rounded px-3 py-1.5 preview-btn-main font-bold text-xs shadow-sm">زر مميز</button>
<button class="preview-rounded px-3 py-1.5 preview-accent-tint preview-accent-text font-bold text-xs">زر فاتح</button>
<button class="preview-rounded px-3 py-1.5 border preview-accent-border preview-btn-action-text font-bold text-xs bg-white/70">زر محدد</button>
<span class="preview-rounded px-2.5 py-1 text-[11px] font-semibold preview-input-field preview-text-muted border">شارة نظام</span>
<div class="flex items-center gap-1.5 mr-2">
<input checked="" class="preview-rounded text-purple-600 focus:ring-0 w-4 h-4 cursor-pointer" id="sampleCheck" type="checkbox"/>
<label class="text-xs preview-text-main select-none cursor-pointer" for="sampleCheck">خيار نشط</label>
</div>
</div>
</div>
</div>
</div>
</section>
</main>
<!-- Live Toast Notification Element -->
<div class="fixed bottom-6 left-6 bg-slate-900 text-white px-4 py-3 rounded-xl shadow-2xl border border-slate-700 flex items-center gap-3 translate-y-24 opacity-0 transition-all duration-300 z-50 pointer-events-none" id="toastNotification">
<span class="material-symbols-outlined text-emerald-400 text-xl">verified</span>
<div>
<p class="text-xs font-bold">تم تطبيق وحفظ إعدادات المظهر بنجاح!</p>
<p class="text-[11px] text-slate-400" id="toastDetails">اللون: 280° | الخط: Cairo</p>
</div>
</div>
<!-- JAVASCRIPT: Full Real-Time Interactivity Engine -->
<script>
    (function () {
      // DOM Elements
      const root = document.documentElement;
      const hueSlider = document.getElementById('themeHue');
      const hueVal = document.getElementById('themeHueValue');
      const swatches = document.querySelectorAll('.theme-swatch');
      const fontSelect = document.getElementById('themeFontSelect');
      const fontSizeSlider = document.getElementById('themeFontSize');
      const fontSizeVal = document.getElementById('themeFontSizeValue');
      const modeRadios = document.querySelectorAll('input[name="theme-mode"]');
      const densityRadios = document.querySelectorAll('input[name="theme-density"]');
      const cornerRadios = document.querySelectorAll('input[name="theme-corner"]');
      const liveCanvas = document.getElementById('liveCanvas');
      const liveNavbar = document.getElementById('liveNavbar');
      const canvasModeLabel = document.getElementById('canvasModeLabel');
      const activeModeBadge = document.getElementById('activeModeBadge');
      const resetBtn = document.getElementById('resetDefaultsBtn');
      const quickResetBtn = document.getElementById('quickResetBtn');
      const applyBtn = document.getElementById('applyNotificationBtn');
      const toast = document.getElementById('toastNotification');
      const toastDetails = document.getElementById('toastDetails');

      // Accordion indicators
      const accordionAccentDot = document.getElementById('accordionAccentDot');
      const accordionCardDot = document.getElementById('accordionCardDot');
      const accordionBtnDot = document.getElementById('accordionBtnDot');
      const accordionBgDot = document.getElementById('accordionBgDot');
      const accordionTextDot = document.getElementById('accordionTextDot');

      // Accordion Items
      const accordionItems = document.querySelectorAll('.accordion-item');
      accordionItems.forEach(item => {
        const toggle = item.querySelector('.accordion-toggle');
        toggle.addEventListener('click', (e) => {
          e.preventDefault();
          const isOpen = item.classList.contains('is-open');
          
          // Optionally close siblings to keep panel super clean & compact
          accordionItems.forEach(other => {
            if (other !== item) other.classList.remove('is-open');
          });

          if (isOpen) {
            item.classList.remove('is-open');
          } else {
            item.classList.add('is-open');
          }
        });
      });

      // Card / Board Customization Elements
      const cardSwatches = document.querySelectorAll('.card-swatch');
      const cardHexLabel = document.getElementById('cardHexLabel');
      const customCardPicker = document.getElementById('customCardPicker');

      // Button Customization Elements
      const btnStyleRadios = document.querySelectorAll('input[name="btn-style"]');
      const btnColorSwatches = document.querySelectorAll('.btn-color-swatch');
      const btnHexLabel = document.getElementById('btnHexLabel');
      const customBtnColorPicker = document.getElementById('customBtnColorPicker');

      // Color Customization Elements
      const bgSwatches = document.querySelectorAll('.bg-swatch');
      const bgHexLabel = document.getElementById('bgHexLabel');
      const customBgPicker = document.getElementById('customBgPicker');
      const textSwatches = document.querySelectorAll('.text-swatch');
      const textHexLabel = document.getElementById('textHexLabel');
      const customTextColorPicker = document.getElementById('customTextColorPicker');
      const contrastBadge = document.getElementById('contrastBadge');

      // State Object
      const themeState = {
        hue: 280,
        font: 'Cairo',
        fontSize: 16,
        density: 'comfortable',
        corner: 'soft',
        mode: 'light',
        bgColor: '#f8fafc',
        cardBg: '#ffffff',
        cardBorder: 'rgba(226, 232, 240, 0.9)',
        textColor: '#0f172a',
        textMuted: '#64748b',
        btnColor: '#7c3aed',
        btnHover: '#6d28d9',
        btnStyle: 'filled'
      };

      // Helper: Calculate brightness from hex
      function getBrightness(hex) {
        let c = hex.replace('#', '');
        if (c.length === 3) {
          c = c.split('').map(x => x + x).join('');
        }
        const num = parseInt(c, 16);
        const r = (num >> 16) & 255;
        const g = (num >> 8) & 255;
        const b = num & 255;
        return (r * 299 + g * 587 + b * 114) / 1000;
      }

      // Update Contrast Indicator
      function updateContrastIndicator(bgHex, textHex) {
        const bgB = getBrightness(bgHex);
        const textB = getBrightness(textHex);
        const diff = Math.abs(bgB - textB);

        if (diff > 125) {
          contrastBadge.textContent = 'تباين ممتاز AAA';
          contrastBadge.className = 'text-[10px] font-semibold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200';
        } else if (diff > 80) {
          contrastBadge.textContent = 'تباين جيد AA';
          contrastBadge.className = 'text-[10px] font-semibold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200';
        } else {
          contrastBadge.textContent = 'تباين منخفض ⚠️';
          contrastBadge.className = 'text-[10px] font-semibold text-rose-600 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200';
        }
      }

      // 1. Update Accent Color
      function setAccentHue(hueValNumber) {
        themeState.hue = hueValNumber;
        hueSlider.value = hueValNumber;
        hueVal.textContent = hueValNumber + '°';
        root.style.setProperty('--primary-hue', hueValNumber);
        root.style.setProperty('--accent-color', `hsl(${hueValNumber}, 76%, 54%)`);
        root.style.setProperty('--accent-light', `hsla(${hueValNumber}, 76%, 54%, 0.12)`);
        root.style.setProperty('--accent-border', `hsla(${hueValNumber}, 76%, 54%, 0.3)`);
        root.style.setProperty('--accent-hover', `hsl(${hueValNumber}, 76%, 46%)`);

        if (accordionAccentDot) {
          accordionAccentDot.style.backgroundColor = `hsl(${hueValNumber}, 76%, 54%)`;
        }

        // Update swatch visual active ring
        swatches.forEach(swatch => {
          const sHue = swatch.getAttribute('data-hue');
          const checkmark = swatch.querySelector('.checkmark');
          if (Math.abs(parseInt(sHue, 10) - parseInt(hueValNumber, 10)) <= 8) {
            swatch.classList.add('ring-2', 'ring-offset-2', 'ring-purple-600');
            if (checkmark) checkmark.classList.remove('hidden');
          } else {
            swatch.classList.remove('ring-2', 'ring-offset-2', 'ring-purple-600');
            if (checkmark) checkmark.classList.add('hidden');
          }
        });
      }

      hueSlider.addEventListener('input', (e) => {
        setAccentHue(e.target.value);
      });

      // Swatches click
      swatches.forEach(swatch => {
        swatch.addEventListener('click', () => {
          const hue = swatch.getAttribute('data-hue');
          setAccentHue(hue);
        });
      });

      // 2. Card / Board Customization Logic
      function setCardColor(cardBg, cardBorder = null) {
        themeState.cardBg = cardBg;
        cardHexLabel.textContent = cardBg;
        if (accordionCardDot) accordionCardDot.style.backgroundColor = cardBg;

        const isDarkCard = getBrightness(cardBg) < 130;
        const computedBorder = cardBorder || (isDarkCard ? 'rgba(51, 65, 85, 0.7)' : 'rgba(226, 232, 240, 0.9)');
        themeState.cardBorder = computedBorder;

        root.style.setProperty('--preview-card-bg', cardBg);
        root.style.setProperty('--preview-card-border', computedBorder);

        // Update swatches selection
        cardSwatches.forEach(swatch => {
          const checkmark = swatch.querySelector('.checkmark');
          if (swatch.getAttribute('data-card').toLowerCase() === cardBg.toLowerCase()) {
            swatch.classList.add('border-purple-600', 'ring-2', 'ring-purple-600/30');
            if (checkmark) checkmark.classList.remove('hidden');
          } else {
            swatch.classList.remove('border-purple-600', 'ring-2', 'ring-purple-600/30');
            if (checkmark) checkmark.classList.add('hidden');
          }
        });
      }

      cardSwatches.forEach(swatch => {
        swatch.addEventListener('click', () => {
          const bg = swatch.getAttribute('data-card');
          const border = swatch.getAttribute('data-border');
          setCardColor(bg, border);
        });
      });

      customCardPicker.addEventListener('input', (e) => {
        setCardColor(e.target.value);
      });

      // 3. Button Color & Style Customization Logic
      function updateButtonVariables() {
        const { btnColor, btnStyle } = themeState;
        btnHexLabel.textContent = btnColor;
        if (accordionBtnDot) accordionBtnDot.style.backgroundColor = btnColor;
        const isBright = getBrightness(btnColor) > 175;

        if (btnStyle === 'filled') {
          root.style.setProperty('--btn-primary-bg', btnColor);
          root.style.setProperty('--btn-primary-text', isBright ? '#0f172a' : '#ffffff');
          root.style.setProperty('--btn-primary-border', 'transparent');
          root.style.setProperty('--btn-primary-hover', btnColor);
          root.style.setProperty('--btn-primary-shadow', `0 4px 12px -2px ${btnColor}40`);
        } else if (btnStyle === 'subtle') {
          root.style.setProperty('--btn-primary-bg', `${btnColor}20`);
          root.style.setProperty('--btn-primary-text', btnColor);
          root.style.setProperty('--btn-primary-border', `${btnColor}40`);
          root.style.setProperty('--btn-primary-hover', `${btnColor}35`);
          root.style.setProperty('--btn-primary-shadow', 'none');
        } else if (btnStyle === 'outline') {
          root.style.setProperty('--btn-primary-bg', 'transparent');
          root.style.setProperty('--btn-primary-text', btnColor);
          root.style.setProperty('--btn-primary-border', btnColor);
          root.style.setProperty('--btn-primary-hover', `${btnColor}18`);
          root.style.setProperty('--btn-primary-shadow', 'none');
        }
      }

      function setButtonColor(colorHex, hoverHex = null) {
        themeState.btnColor = colorHex;
        themeState.btnHover = hoverHex || colorHex;
        updateButtonVariables();

        btnColorSwatches.forEach(swatch => {
          const checkmark = swatch.querySelector('.checkmark');
          if (swatch.getAttribute('data-btn-color').toLowerCase() === colorHex.toLowerCase()) {
            swatch.classList.add('border-purple-600', 'ring-2', 'ring-purple-600/30');
            if (checkmark) checkmark.classList.remove('hidden');
          } else {
            swatch.classList.remove('border-purple-600', 'ring-2', 'ring-purple-600/30');
            if (checkmark) checkmark.classList.add('hidden');
          }
        });
      }

      btnColorSwatches.forEach(swatch => {
        swatch.addEventListener('click', () => {
          const color = swatch.getAttribute('data-btn-color');
          const hover = swatch.getAttribute('data-btn-hover');
          setButtonColor(color, hover);
        });
      });

      customBtnColorPicker.addEventListener('input', (e) => {
        setButtonColor(e.target.value);
      });

      btnStyleRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
          if (e.target.checked) {
            themeState.btnStyle = e.target.value;
            updateButtonVariables();
          }
        });
      });

      // 4. Background Color Logic
      function setBackgroundColor(bgColor, cardBg, navBg, borderColor, isDark = null) {
        themeState.bgColor = bgColor;
        bgHexLabel.textContent = bgColor;
        if (accordionBgDot) accordionBgDot.style.backgroundColor = bgColor;

        const isDarkTheme = isDark !== null ? isDark : getBrightness(bgColor) < 130;

        const computedCardBg = cardBg || themeState.cardBg || (isDarkTheme ? '#1e293b' : '#ffffff');
        const computedNavBg = navBg || (isDarkTheme ? bgColor : '#ffffff');
        const computedBorder = borderColor || (isDarkTheme ? 'rgba(51, 65, 85, 0.7)' : 'rgba(226, 232, 240, 0.9)');
        const computedInputBg = isDarkTheme ? '#334155' : '#f1f5f9';
        const computedSubtleBg = isDarkTheme ? 'rgba(30, 41, 59, 0.7)' : 'rgba(241, 245, 249, 0.85)';

        setCardColor(computedCardBg, computedBorder);

        root.style.setProperty('--preview-bg', bgColor);
        root.style.setProperty('--preview-nav-bg', computedNavBg);
        root.style.setProperty('--preview-border-color', computedBorder);
        root.style.setProperty('--preview-input-bg', computedInputBg);
        root.style.setProperty('--preview-subtle-bg', computedSubtleBg);

        // Auto adjust text color if currently completely unreadable
        const curTextBright = getBrightness(themeState.textColor);
        if (isDarkTheme && curTextBright < 100) {
          setTextColor('#f8fafc', '#94a3b8');
        } else if (!isDarkTheme && curTextBright > 200) {
          setTextColor('#0f172a', '#64748b');
        } else {
          updateContrastIndicator(bgColor, themeState.textColor);
        }

        // Active swatch states
        bgSwatches.forEach(swatch => {
          const checkmark = swatch.querySelector('.checkmark');
          if (swatch.getAttribute('data-bg').toLowerCase() === bgColor.toLowerCase()) {
            swatch.classList.add('border-purple-600', 'ring-2', 'ring-purple-600/30');
            if (checkmark) checkmark.classList.remove('hidden');
          } else {
            swatch.classList.remove('border-purple-600', 'ring-2', 'ring-purple-600/30');
            if (checkmark) checkmark.classList.add('hidden');
          }
        });
      }

      bgSwatches.forEach(swatch => {
        swatch.addEventListener('click', () => {
          const bg = swatch.getAttribute('data-bg');
          const card = swatch.getAttribute('data-card');
          const nav = swatch.getAttribute('data-nav');
          const border = swatch.getAttribute('data-border');
          const isDark = swatch.getAttribute('data-theme') === 'dark';
          setBackgroundColor(bg, card, nav, border, isDark);
        });
      });

      customBgPicker.addEventListener('input', (e) => {
        setBackgroundColor(e.target.value);
      });

      // 5. Text Color Logic
      function setTextColor(colorHex, mutedHex = null) {
        themeState.textColor = colorHex;
        textHexLabel.textContent = colorHex;
        if (accordionTextDot) accordionTextDot.style.backgroundColor = colorHex;

        const isLight = getBrightness(colorHex) > 150;
        const computedMuted = mutedHex || (isLight ? '#94a3b8' : '#64748b');
        themeState.textMuted = computedMuted;

        root.style.setProperty('--preview-text-main', colorHex);
        root.style.setProperty('--preview-text-muted', computedMuted);

        updateContrastIndicator(themeState.bgColor, colorHex);

        textSwatches.forEach(swatch => {
          const checkmark = swatch.querySelector('.checkmark');
          if (swatch.getAttribute('data-color').toLowerCase() === colorHex.toLowerCase()) {
            swatch.classList.add('border-purple-600', 'ring-2', 'ring-purple-600/30');
            if (checkmark) checkmark.classList.remove('hidden');
          } else {
            swatch.classList.remove('border-purple-600', 'ring-2', 'ring-purple-600/30');
            if (checkmark) checkmark.classList.add('hidden');
          }
        });
      }

      textSwatches.forEach(swatch => {
        swatch.addEventListener('click', () => {
          const col = swatch.getAttribute('data-color');
          const mut = swatch.getAttribute('data-muted');
          setTextColor(col, mut);
        });
      });

      customTextColorPicker.addEventListener('input', (e) => {
        setTextColor(e.target.value);
      });

      // 6. Update Font Family
      function setFontFamily(fontName) {
        themeState.font = fontName;
        fontSelect.value = fontName;
        root.style.setProperty('--app-font', `'${fontName}', system-ui, sans-serif`);
      }

      fontSelect.addEventListener('change', (e) => {
        setFontFamily(e.target.value);
      });

      // 7. Update Font Size with Dynamic Real-time Reflectivity
      function setFontSize(sizePx) {
        themeState.fontSize = sizePx;
        fontSizeSlider.value = sizePx;
        fontSizeVal.textContent = sizePx + ' px';
        root.style.setProperty('--app-font-size', sizePx + 'px');
        if (liveCanvas) {
          liveCanvas.style.fontSize = sizePx + 'px';
        }
      }

      fontSizeSlider.addEventListener('input', (e) => {
        setFontSize(e.target.value);
      });

      // 8. Update Density
      function setDensity(densityVal) {
        themeState.density = densityVal;
        if (densityVal === 'compact') {
          root.style.setProperty('--density-py', '0.65rem');
          root.style.setProperty('--density-px', '0.85rem');
          root.style.setProperty('--density-gap', '0.75rem');
        } else {
          // comfortable
          root.style.setProperty('--density-py', '1rem');
          root.style.setProperty('--density-px', '1.25rem');
          root.style.setProperty('--density-gap', '1.25rem');
        }
      }

      densityRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
          if (e.target.checked) setDensity(e.target.value);
        });
      });

      // 9. Update Corner Radius
      function setCornerRadius(cornerType) {
        themeState.corner = cornerType;
        let radius = '14px';
        if (cornerType === 'sharp') radius = '4px';
        if (cornerType === 'round') radius = '24px';
        root.style.setProperty('--app-radius', radius);
      }

      cornerRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
          if (e.target.checked) setCornerRadius(e.target.value);
        });
      });

      // 10. Update Theme Mode (Light / Dark / System / Custom)
      function setThemeMode(mode) {
        themeState.mode = mode;
        let effectiveDark = false;

        if (mode === 'dark') {
          effectiveDark = true;
          activeModeBadge.textContent = 'ليلي';
        } else if (mode === 'light') {
          effectiveDark = false;
          activeModeBadge.textContent = 'نهاري';
        } else if (mode === 'system') {
          effectiveDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
          activeModeBadge.textContent = 'تلقائي (' + (effectiveDark ? 'ليلي' : 'نهاري') + ')';
        } else if (mode === 'custom') {
          effectiveDark = getBrightness(themeState.bgColor) < 130;
          activeModeBadge.textContent = 'مخصص';
        }

        if (effectiveDark) {
          setBackgroundColor('#0f172a', '#1e293b', '#0f172a', '#334155', true);
          setTextColor('#f8fafc', '#94a3b8');
          canvasModeLabel.textContent = 'الوضع: ليلي (Dark)';
        } else {
          setBackgroundColor('#f8fafc', '#ffffff', '#ffffff', '#e2e8f0', false);
          setTextColor('#0f172a', '#64748b');
          canvasModeLabel.textContent = 'الوضع: نهاري (Light)';
        }
      }

      modeRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
          if (e.target.checked) setThemeMode(e.target.value);
        });
      });

      // 11. Reset to Defaults Function
      function resetToDefaults() {
        setAccentHue(280);
        setFontFamily('Cairo');
        setFontSize(16);
        setDensity('comfortable');
        setCornerRadius('soft');
        setBackgroundColor('#f8fafc', '#ffffff', '#ffffff', '#e2e8f0', false);
        setCardColor('#ffffff', '#e2e8f0');
        setButtonColor('#7c3aed', '#6d28d9');
        themeState.btnStyle = 'filled';
        const filledBtnRadio = document.querySelector('input[name="btn-style"][value="filled"]');
        if (filledBtnRadio) filledBtnRadio.checked = true;
        updateButtonVariables();
        setTextColor('#0f172a', '#64748b');
        setThemeMode('light');

        // Check correct radio buttons
        const lightModeRadio = document.querySelector('input[name="theme-mode"][value="light"]');
        if (lightModeRadio) lightModeRadio.checked = true;

        const comfortableRadio = document.querySelector('input[name="theme-density"][value="comfortable"]');
        if (comfortableRadio) comfortableRadio.checked = true;

        const softCornerRadio = document.querySelector('input[name="theme-corner"][value="soft"]');
        if (softCornerRadio) softCornerRadio.checked = true;

        // Reset accordion open state (open accent, collapse others)
        accordionItems.forEach(item => {
          if (item.getAttribute('data-accordion') === 'accent') {
            item.classList.add('is-open');
          } else {
            item.classList.remove('is-open');
          }
        });

        showToast('تمت استعادة كافة الإعدادات والبطاقات والأزرار للافتراضي!');
      }

      resetBtn.addEventListener('click', resetToDefaults);
      quickResetBtn.addEventListener('click', resetToDefaults);

      // 12. Toast Feedback Trigger
      function showToast(message) {
        if (message) {
          toast.querySelector('p').textContent = message;
        }
        toastDetails.textContent = `البطاقات: ${themeState.cardBg} | الأزرار: ${themeState.btnColor} | الخط: ${themeState.fontSize}px`;
        toast.classList.remove('translate-y-24', 'opacity-0');
        toast.classList.add('translate-y-0', 'opacity-100');

        setTimeout(() => {
          toast.classList.remove('translate-y-0', 'opacity-100');
          toast.classList.add('translate-y-24', 'opacity-0');
        }, 2800);
      }

      applyBtn.addEventListener('click', () => {
        showToast('تم حفظ وتطبيق التفضيلات والبطاقات والأزرار بنجاح!');
      });

      // Initialize defaults
      setAccentHue(280);
      setFontFamily('Cairo');
      setFontSize(16);
      setCornerRadius('soft');
      setBackgroundColor('#f8fafc', '#ffffff', '#ffffff', '#e2e8f0', false);
      setCardColor('#ffffff', '#e2e8f0');
      setButtonColor('#7c3aed', '#6d28d9');
      setTextColor('#0f172a', '#64748b');
    })();
  </script>
</body></html>