from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_performance_form_print_fits_a4_landscape_page():
    template = (ROOT / 'templates/faculty_performance/print.html').read_text(
        encoding='utf-8'
    )
    script = (ROOT / 'static/js/faculty_performance_print_fit.js').read_text(
        encoding='utf-8'
    )

    assert 'size: A4 landscape' in template
    assert 'height: 190mm' in template
    assert 'faculty_performance_print_fit.js' in template
    assert 'beforeprint' in script
    assert 'page.clientHeight / form.scrollHeight' in script
    assert 'performance-print-fit' in template


def test_other_print_documents_keep_their_portrait_default():
    template = (
        ROOT / 'templates/faculty_performance/_print_document.html'
    ).read_text(encoding='utf-8')

    assert 'size: A4 portrait' in template
