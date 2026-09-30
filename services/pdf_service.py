"""خدمة توليد ملفات PDF على الخادم عبر متصفح Chromium بدون واجهة.

سبب وجودها: الطباعة من المتصفح تعتمد على إعدادات جهاز المستخدم (المقاس،
الهوامش، مقياس التصغير) فيختلف ترقيم نفس القالب من جهاز لآخر، وهو أصل
مشكلة «الاستمارة تنتقل لصفحة ثانية» و«الترويسة تظهر في النسخة». هنا نرسم
القالب مرة واحدة على الخادم بعلبة صفحة ثابتة ونسلّم المستخدم ملفاً جاهزاً،
فيكون الناتج واحداً للجميع.

يتطلب متصفحاً من عائلة Chromium. يُكتشف المسار تلقائياً (Edge ثم Chrome ثم
الأسماء المعروفة في PATH) ويمكن تجاوزه بالمتغير ROPEY_PDF_BROWSER.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import threading
from urllib.parse import quote

from flask import Response, current_app, render_template

# /     /     >---- متغير البيئة لتجاوز المتصفح المكتشف تلقائياً
BROWSER_ENV_VAR = 'ROPEY_PDF_BROWSER'
#     /     >---- مهلة أمان لا هدف أداء: وسيط التحويل بضع ثوانٍ، لكنه يبلغ
#     /     >---- ثلاثين ثانية أو أكثر على جهاز مشغول. الفشل هنا استثناء.
DEFAULT_TIMEOUT_SECONDS = 90.0
VIRTUAL_TIME_BUDGET_MS = 4000
MIN_PAGE_SCALE = 0.4

#     /     >---- الوضع القديم أسرع في الإقلاع، والجديد احتياط لو أُزيل دعمه
HEADLESS_MODES = ('--headless', '--headless=new')

_BROWSER_CANDIDATES = (
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/snap/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
)

_BROWSER_NAMES = (
    'msedge', 'chrome', 'chromium', 'chromium-browser',
    'google-chrome', 'google-chrome-stable',
)

#     /     >---- نحدّث المسار مرة واحدة فقط لكل العملية
_cache_lock = threading.Lock()
_cached_browser = None
_browser_resolved = False
_cached_profile = None

#     /     >---- كل طلب يفتح عملية متصفح؛ التزاحم على جهاز صغير يبطئ الجميع
render_lock = threading.Lock()

_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0

_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.IGNORECASE | re.DOTALL)
_UNSAFE_FILENAME_RE = re.compile(r'[\r\n"\\/]')


class PdfUnavailableError(RuntimeError):
    """لا يوجد متصفح من عائلة Chromium على الجهاز."""


class PdfRenderError(RuntimeError):
    """المتصفح عمل لكنه لم ينتج ملف PDF صالحاً."""


#     /     >---- مسار المتصفح (مع تخزين مؤقت) أو None
def browser_path():
    global _cached_browser, _browser_resolved
    if _browser_resolved:
        return _cached_browser
    with _cache_lock:
        if _browser_resolved:
            return _cached_browser
        found = None
        override = (os.environ.get(BROWSER_ENV_VAR) or '').strip()
        if override and os.path.isfile(override):
            found = override
        if found is None:
            for candidate in _BROWSER_CANDIDATES:
                if os.path.isfile(candidate):
                    found = candidate
                    break
        if found is None:
            for name in _BROWSER_NAMES:
                found = shutil.which(name)
                if found:
                    break
        _cached_browser = found
        _browser_resolved = True
        return _cached_browser


def is_available():
    """هل يمكن توليد PDF على هذا الجهاز؟"""
    return browser_path() is not None


def reset_browser_cache():
    """يُستدعى بعد تغيير المتغير البيئي أثناء الاختبار."""
    global _cached_browser, _browser_resolved
    with _cache_lock:
        _cached_browser = None
        _browser_resolved = False


#     /     >---- استبدال مسارات /static بصور داخل النص
def inline_static_images(html, static_root):
    """يبدّل ``src="/static/..."`` بـ ``data:`` URI.

    المتصفح يفتح ملف الـ HTML من مجلد مؤقت بلا أصل شبكي، فالمسار النسبي
    ``/static`` يُحلّ على القرص ويختفي شعار الكلية من كل ملف PDF بصمت.
    """
    if not html or '/static/' not in html:
        return html
    root = os.path.abspath(static_root)

    def _replace(match):
        prefix, src, suffix = match.groups()
        if src.startswith('data:') or '://' in src or src.startswith('//'):
            return match.group(0)
        path = src.split('?', 1)[0].split('#', 1)[0]
        if not path.startswith('/static/'):
            return match.group(0)
        target = os.path.abspath(
            os.path.join(root, path[len('/static/'):].lstrip('/')))
        try:
            inside = os.path.commonpath([root, target]) == root
        except ValueError:
            inside = False
        if not inside:
            return match.group(0)
        try:
            with open(target, 'rb') as handle:
                payload = handle.read()
        except OSError:
            return match.group(0)
        mime = mimetypes.guess_type(target)[0] or 'application/octet-stream'
        encoded = base64.b64encode(payload).decode('ascii')
        return '%sdata:%s;base64,%s%s' % (prefix, mime, encoded, suffix)

    return _IMG_SRC_RE.sub(_replace, html)


def _static_root():
    return os.path.join(current_app.root_path, 'static')


#     /     >---- مجلد تعريف واحد يشارك كل عمليات التحويل
def _shared_profile():
    """مجلد تعريف واحد لكل العملية.

    إنشاء ``--user-data-dir`` جديد في كل طلب يجعل المتصفح يشغّل تهيئة
    أولية في كل مرة (شuardiam|first-run|Nextensions)، وهي أبطأ جزء في
    التحويل. المشاركة آمنة لأن التحويليات تُنفَّذ متسلسلة تحت
    :data:`render_lock`.
    """
    global _cached_profile
    if _cached_profile and os.path.isdir(_cached_profile):
        return _cached_profile
    path = tempfile.mkdtemp(prefix='ropey-pdf-profile-')
    _cached_profile = path
    return path


#     /     >---- تشغيل المتصفح على ملف HTML وإرجاع بايتات PDF
def _run_browser(command, pdf_path, timeout):
    try:
        subprocess.run(
            command, capture_output=True, timeout=timeout,
            creationflags=_NO_WINDOW, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PdfRenderError(
            'انتهت مهلة توليد ملف PDF بعد %s ثانية.' % int(timeout)
        ) from exc
    except OSError as exc:
        raise PdfRenderError(
            'تعذّر تشغيل المتصفح لتوليد ملف PDF: %s' % exc
        ) from exc
    if os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0:
        with open(pdf_path, 'rb') as handle:
            data = handle.read()
        if data.startswith(b'%PDF'):
            return data
    return None


def render_pdf(html, *, timeout=DEFAULT_TIMEOUT_SECONDS,
               virtual_time_ms=VIRTUAL_TIME_BUDGET_MS):
    """يحوّل HTML إلى بايتات PDF، ويرفع استثناءً عند الفشل."""
    browser = browser_path()
    if not browser:
        raise PdfUnavailableError(
            'لم يُعثر على متصفح Chrome أو Edge لتوليد ملفات PDF على هذا الجهاز. '
            'ثبّت أحدهما أو عيّن %s.' % BROWSER_ENV_VAR
        )

    workdir = tempfile.mkdtemp(prefix='ropey-pdf-')
    try:
        doc_path = os.path.join(workdir, 'document.html')
        pdf_path = os.path.join(workdir, 'document.pdf')
        with open(doc_path, 'w', encoding='utf-8') as handle:
            handle.write(html)

        base = [
            '--disable-gpu',
            '--no-sandbox',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions',
            '--disable-background-networking',
            '--disable-component-update',
            '--disable-sync',
            '--hide-scrollbars',
            '--run-all-compositor-stages-before-draw',
            '--no-pdf-header-footer',
            '--print-to-pdf-no-header',
            '--virtual-time-budget=%d' % virtual_time_ms,
            '--user-data-dir=%s' % _shared_profile(),
            '--print-to-pdf=%s' % pdf_path,
            'file:///%s' % doc_path.replace(os.sep, '/'),
        ]

        #     /     >---- الوضع القديم أسرع، والجديد احتياط إن لم يعد مدعوماً
        data = None
        with render_lock:
            for mode in HEADLESS_MODES:
                data = _run_browser([browser, mode] + base, pdf_path, timeout)
                if data:
                    break

        if not data:
            raise PdfRenderError('لم يُنتج المتصفح ملف PDF صالحاً.')
        return data
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _content_disposition(name):
    """ترويسة تنزيل آمنة للأسماء العربية (RFC 5987)."""
    cleaned = _UNSAFE_FILENAME_RE.sub('', str(name or '')).strip()
    if not cleaned:
        cleaned = 'document'
    if not cleaned.lower().endswith('.pdf'):
        cleaned += '.pdf'
    fallback = re.sub(r'[^A-Za-z0-9._-]', '_', cleaned) or 'document.pdf'
    return 'attachment; filename="%s"; filename*=UTF-8\'\'%s' % (
        fallback, quote(cleaned, safe='')
    )


def pdf_response(html, *, download_name, timeout=DEFAULT_TIMEOUT_SECONDS):
    """HTML جاهز ← رد Flask يحمل ملف PDF للتنزيل."""
    data = render_pdf(
        inline_static_images(html, _static_root()), timeout=timeout
    )
    response = Response(data, mimetype='application/pdf')
    response.headers['Content-Disposition'] = _content_disposition(download_name)
    response.headers['Content-Length'] = str(len(data))
    response.headers['Cache-Control'] = 'no-store'
    return response


def template_pdf_response(template_name, *, download_name,
                          timeout=DEFAULT_TIMEOUT_SECONDS, **context):
    """يرسم قالباً ثم يحوّله رد PDF جاهزاً للتنزيل."""
    html = render_template(template_name, **context)
    return pdf_response(html, download_name=download_name, timeout=timeout)