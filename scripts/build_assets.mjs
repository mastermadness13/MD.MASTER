/**
 * Asset build for newRopey.
 *
 * Replaces, at build time, the three things the browser used to do at
 * runtime and that made every page pay for them:
 *
 *   1. Tailwind Play CDN  -> real compiled CSS (no JIT engine on the wire,
 *      no DOM walk, no recompile when a modal is injected).
 *   2. static/css/app.css -> 36 serial @import round-trips collapsed into a
 *      single stylesheet.
 *   3. unhashed filenames  -> content-hashed filenames + static/dist/manifest.json
 *      so /static/dist/ can be served immutable (see security_headers.py).
 *
 * Outputs land in static/dist/. Source files are never modified or deleted,
 * so the app still boots correctly if this build has not been run.
 *
 *   node scripts/build_assets.mjs            one-shot build
 *   node scripts/build_assets.mjs --watch    rebuild on change
 *   node scripts/build_assets.mjs --clean-only
 */
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import * as esbuild from 'esbuild';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CSS_ROOT = path.join(ROOT, 'static', 'css');
const JS_ROOT = path.join(ROOT, 'static', 'js');
const DIST = path.join(ROOT, 'static', 'dist');
const MANIFEST = path.join(DIST, 'manifest.json');
const TAILWIND_INPUT = path.join(ROOT, 'assets', 'tailwind.input.css');
// Invoke the CLI's JS entry through the current node binary rather than the
// node_modules/.bin shim: the .cmd shim cannot be exec'd on Windows without
// `shell: true`, which would reintroduce quoting problems on every path.
const TAILWIND_CLI = path.join(ROOT, 'node_modules', 'tailwindcss', 'lib', 'cli.js');

// ES2018 keeps the output loadable by the older Android WebViews this app is
// used on, without downlevelling far enough to bloat the bundle.
const JS_TARGET = 'es2018';

const argv = new Set(process.argv.slice(2));
const WATCH = argv.has('--watch');
const CLEAN_ONLY = argv.has('--clean-only');

const log = (...args) => console.log('[assets]', ...args);
const kb = (bytes) => `${(bytes / 1024).toFixed(1)} KB`;

function hash(contents) {
  return createHash('sha256').update(contents).digest('hex').slice(0, 8);
}

async function walk(dir) {
  const out = [];
  let entries;
  try {
    entries = await fsp.readdir(dir, { withFileTypes: true });
  } catch (err) {
    if (err.code === 'ENOENT') return out;
    throw err;
  }
  for (const entry of entries) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...(await walk(abs)));
    else if (entry.isFile() && entry.name.endsWith('.js')) out.push(abs);
  }
  return out;
}

/**
 * Two CSS bundles, because the two shells need very different amounts of
 * Tailwind:
 *
 *  - app.css  : the authenticated/admin UI. ~230 KB of templates plus all of
 *               static/js, so it needs the full generated utility set.
 *  - spa.css  : the standalone SPA shell (templates/spa.html + static/js/spa).
 *               A dozen utilities. Serving it the full app bundle would waste
 *               ~40 KB gzip on a page that renders almost nothing, so it gets
 *               its own Tailwind run over a narrow content set.
 *
 * spa.html previously loaded the Play CDN with no config at all, which meant
 * its `bg-surface` utility silently resolved to nothing. The scoped build
 * fixes that as a side effect.
 */
const BUNDLES = [
  { name: 'app', out: 'app.css', key: 'app.css', globs: null },
  {
    name: 'spa',
    out: 'spa.css',
    key: 'spa.css',
    globs: ['./templates/spa.html', './static/js/spa/**/*.js', './static/js/pages/spa.js'],
  },
  {
    // Public site. Separate config on purpose: primary/public/shared use a
    // different palette from the authenticated UI.
    name: 'public',
    out: 'public.css',
    key: 'public.css',
    config: 'tailwind.public.config.js',
    globs: null, // config declares its own content globs
    postCss: 'static/public/shared/responsive.css',
    stableCopy: 'static/public/shared/tailwind.css',
  },
];

// ── CSS ────────────────────────────────────────────────────────────────────

/**
 * Flatten static/css/app.css by inlining its @import graph in source order.
 *
 * Order is load-bearing and is preserved exactly: layout/*, components/*,
 * features/*, themes/*, then the override layers (theme-overrides,
 * theme-custom) and finally mobile.css last.
 *
 * Two CSS-spec constraints are handled here:
 *  - Every @import must appear above all other rules or the browser discards
 *    the entire file. static/css/base/typography.css carries a Google Fonts
 *    @import, so remote imports are hoisted into a block emitted first.
 *  - Relative url() references would resolve against static/dist/ instead of
 *    the source file's own directory. Every url() in the graph is a data: URI
 *    today; assert that rather than trust it, so the day someone adds a real
 *    one the build fails loudly instead of shipping a broken image.
 */
async function collectCssImports() {
  const entrySource = await fsp.readFile(path.join(CSS_ROOT, 'app.css'), 'utf8');

  const importRe = /@import\s+url\(\s*['"]?\.?\/?([^'")]+?)['"]?\s*\)\s*;/g;
  const localFiles = [];
  let match;
  while ((match = importRe.exec(entrySource)) !== null) {
    localFiles.push(match[1].replace(/^\.\//, ''));
  }
  if (!localFiles.length) throw new Error('static/css/app.css has no @import statements');

  const remote = [];
  const body = [];

  for (const rel of localFiles) {
    const abs = path.join(CSS_ROOT, rel);
    let source = await fsp.readFile(abs, 'utf8');

    source = source.replace(
      /@import\s+url\(\s*['"]?(https?:\/\/[^'")]+?)['"]?\s*\)\s*;?/g,
      (_full, href) => {
        remote.push(href);
        return '';
      },
    );

    const relativeUrls = [...source.matchAll(/url\(\s*['"]?([^'")]+)/gi)]
      .map((m) => m[1].trim())
      .filter((u) => !/^(data:|#|https?:\/\/|\/)/i.test(u));
    if (relativeUrls.length) {
      throw new Error(
        `${rel} references relative asset(s) ${[...new Set(relativeUrls)].join(', ')}. ` +
        'Inlining it into static/dist/ would break the path — move the asset to an ' +
        'absolute /static/ URL first.',
      );
    }

    body.push(`/* ---- ${rel} ---- */`, source.trim());
  }

  return {
    remoteBlock: [...new Set(remote)].map((href) => `@import url('${href}');`).join('\n'),
    body: body.join('\n\n'),
    fileCount: localFiles.length,
  };
}

function compileTailwind(contentGlobs, configFile = 'tailwind.config.js') {
  log(`compiling tailwind (${configFile})`);
  const args = [
    TAILWIND_CLI,
    '--input', TAILWIND_INPUT,
    '--config', path.join(ROOT, configFile),
  ];
  if (contentGlobs) args.push('--content', contentGlobs.join(' '));
  return execFileSync(
    process.execPath,
    args,
    { cwd: ROOT, stdio: ['ignore', 'pipe', 'inherit'], encoding: 'utf8', maxBuffer: 128 * 1024 * 1024 },
  );
}

async function buildCss(bundle) {
  // Only the app bundle flattens the static/css @import graph. The public
  // bundle carries its own stylesheet, and the SPA bundle carries none.
  let remoteBlock = '';
  let body = '';
  let fileCount = 0;

  if (!bundle.globs && !bundle.postCss) {
    const collected = await collectCssImports();
    remoteBlock = collected.remoteBlock;
    body = collected.body;
    fileCount = collected.fileCount;
  }

  if (bundle.postCss) {
    // Cascade order as authored: responsive.css is linked before the CDN was
    // loaded, so Tailwind wins ties. Tailwind first, then responsive.css.
    body = `/* ---- ${bundle.postCss} ---- */\n${(await fsp.readFile(path.join(ROOT, bundle.postCss), 'utf8')).trim()}`;
  }

  const tailwind = compileTailwind(bundle.globs, bundle.config || 'tailwind.config.js');

  // Cascade order, verified against the pre-build DOM: the Play CDN injected
  // its <style> while still parsing <head>, i.e. BEFORE the stylesheet <link>
  // it sat next to was reached — so the linked sheet won every tie. Preserve
  // it by putting Tailwind first. Remote @imports must sit above all rules, so
  // they go at the very top, ahead of Tailwind's own reset.
  const combined = [remoteBlock, tailwind, body].filter(Boolean).join('\n');

  const { code } = await esbuild.transform(combined, {
    loader: 'css',
    minify: true,
    target: JS_TARGET,
    legalComments: 'none',
  });

  return { code, rawBytes: Buffer.byteLength(combined), fileCount };
}

// ── JS ─────────────────────────────────────────────────────────────────────

async function buildJs() {
  const files = (await walk(JS_ROOT)).sort();
  return Promise.all(
    files.map(async (abs) => {
      const source = await fsp.readFile(abs, 'utf8');
      const { code } = await esbuild.transform(source, {
        loader: 'js',
        minify: true,
        target: JS_TARGET,
        legalComments: 'none',
      });
      return { abs, rel: path.relative(JS_ROOT, abs).split(path.sep).join('/'), code };
    }),
  );
}

// ── orchestration ──────────────────────────────────────────────────────────

async function emit() {
  if (!fs.existsSync(TAILWIND_CLI)) {
    throw new Error(`Tailwind CLI missing at ${path.relative(ROOT, TAILWIND_CLI)} — run: npm install`);
  }

  await fsp.rm(DIST, { recursive: true, force: true });
  await fsp.mkdir(DIST, { recursive: true });

  const cssResults = [];
  for (const bundle of BUNDLES) {
    const built = await buildCss(bundle);
    cssResults.push({ bundle, built });
  }
  const js = await buildJs();

  const manifest = { builtAt: new Date().toISOString(), css: {}, js: {} };

  const write = async (name, code, ext, bucket, key) => {
    const file = `${name}.${hash(code)}.${ext}`;
    await fsp.writeFile(path.join(DIST, file), code);
    manifest[bucket][key] = `/static/dist/${file}`;
    return Buffer.byteLength(code);
  };

  for (const { bundle, built } of cssResults) {
    const bytes = await write(bundle.name, built.code, 'css', 'css', bundle.key);

    // Static HTML under static/public/ cannot call the static_asset() Jinja
    // helper, so it needs a stable filename. It still gets must-revalidate
    // caching from security_headers.py, which is correct for a file whose
    // name cannot carry a content hash.
    if (bundle.stableCopy) {
      const dest = path.join(ROOT, bundle.stableCopy);
      await fsp.mkdir(path.dirname(dest), { recursive: true });
      await fsp.writeFile(dest, built.code);
    }

    const sources = built.fileCount ? `${built.fileCount} sources -> ` : 'scoped tailwind -> ';
    log(`css  ${bundle.out.padEnd(9)} ${sources}${kb(bytes)}`);
  }

  let jsBytes = 0;
  let jsBefore = 0;
  const notable = [];
  for (const { abs, rel, code } of js) {
    // Flatten: static/js/exams/schedule.js -> exams-schedule.<hash>.js, so
    // static/dist/ stays a flat directory.
    const flat = rel.replace(/\//g, '-').replace(/\.js$/, '');
    jsBytes += await write(flat, code, 'js', 'js', rel);
    const srcBytes = (await fsp.stat(abs)).size;
    jsBefore += srcBytes;
    if (srcBytes > 20000) {
      notable.push(`${rel} ${kb(srcBytes)} -> ${kb(Buffer.byteLength(code))}`);
    }
  }
  log(`js   ${js.length} files ${kb(jsBefore)} -> ${kb(jsBytes)}`);
  for (const line of notable) log(`       ${line}`);

  await fsp.writeFile(MANIFEST, JSON.stringify(manifest, null, 2));
  log(`wrote ${path.relative(ROOT, MANIFEST)} (${Object.keys(manifest.js).length} js entries)`);
}

try {
  if (CLEAN_ONLY) {
    await fsp.rm(DIST, { recursive: true, force: true });
    log('removed static/dist');
  } else if (WATCH) {
    await emit();
    log('watching templates/ static/css/ static/js/ static/public/ assets/ … (ctrl-c to stop)');
    const timers = new Map();
    for (const dir of ['templates', 'static/css', 'static/js', 'static/public', 'assets']) {
      const abs = path.join(ROOT, dir);
      if (!fs.existsSync(abs)) continue;
      fs.watch(abs, { recursive: true }, (_event, filename) => {
        if (!filename || filename.includes(`${path.sep}dist${path.sep}`)) return;
        clearTimeout(timers.get(filename));
        timers.set(filename, setTimeout(() => {
          log(`changed: ${filename}`);
          emit().catch((err) => console.error('[assets] build failed:', err.message));
        }, 150));
      });
    }
  } else {
    await emit();
  }
} catch (err) {
  console.error(`[assets] ${err.message}`);
  process.exit(1);
}
