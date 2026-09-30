"""The faculty-performance print route now downloads a one-page PDF.

The old test asserted against ``templates/faculty_performance/print.html`` plus a
standalone browser-scaling script. Both were deleted: the read-only page was
folded into the PDF download, so these tests pin the PDF shell and the service
contract instead. The "one page, no chrome" guarantees live in
``test_pdf_downloads.py``; this module stays focused on the performance form.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'templates/print/pdf/_base.html'
PERFORMANCE = ROOT / 'templates/print/pdf/performance.html'


def _text(path):
    return path.read_text(encoding='utf-8')


def test_performance_pdf_is_a_single_landscape_sheet():
    template = _text(PERFORMANCE)
    assert "pdf_size = 'A4 landscape'" in template
    assert "pdf_page_w = '297mm'" in template
    assert "pdf_page_h = '210mm'" in template
    # The scalable content lives inside .pdf-sheet so the base fit script can
    # shrink it; without the wrapper nothing scales and the tail is clipped.
    assert '<div class="pdf-sheet">' in template


def test_performance_pdf_carries_no_chrome():
    """The complaint that started this work: a second read-only page with
    buttons and a header naming the signed-in user."""
    template = _text(PERFORMANCE)
    for banned in ('window.print', '<button', 'user.username', 'session.user'):
        assert banned not in template, '%s leaked into the PDF' % banned


def test_the_read_only_html_page_is_gone():
    assert not (ROOT / 'templates/faculty_performance/print.html').exists()
    assert not (ROOT / 'static/js/faculty_performance_print_fit.js').exists()
    manifest = _text(ROOT / 'static/dist/manifest.json')
    assert 'faculty_performance_print_fit' not in manifest


def test_the_pdf_shell_keeps_output_to_one_page():
    base = _text(BASE)
    assert 'overflow: hidden' in base, (
        'the page box no longer clips, so long content spills onto page 2'
    )
    assert 'function fit()' in base
    assert 'sheet.scrollHeight' in base
    assert 'Math.min(1, m.pw / m.sw, m.ph / m.sh)' in base
    assert 'document.fonts.ready' in base, (
        'fitting before webfonts settle measures the wrong height and clips rows'
    )


def test_the_fit_uses_layout_scaling_not_paint_only_transform():
    """transform only rescales at paint time, so the print snapshot was right
    roughly half the time and clipped the rest of the form the other half.
    zoom feeds the scale back into layout, which is what makes one page stable.
    """
    base = _text(BASE)
    assert 'sheet.style.zoom = scale' in base, (
        'the fit fell back to paint-only scaling, which renders a clipped page '
        'about half the time'
    )
    assert 'sheet.scrollWidth' in base


def test_other_print_documents_keep_their_portrait_default():
    template = _text(ROOT / 'templates/faculty_performance/_print_document.html')

    assert 'size: A4 portrait' in template