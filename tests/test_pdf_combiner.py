import os
import pytest
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader
from pdf_combiner import combine_pdfs


def make_pdf(path, text='Test page'):
    """Helper: create a minimal one-page PDF at path."""
    c = canvas.Canvas(path, pagesize=A4)
    c.drawString(100, 750, text)
    c.save()


def test_returns_none_when_no_valid_files(tmp_path):
    entries = [{'filepath': str(tmp_path / 'missing.pdf'),
                'item_number': '10.1', 'title': 'Test'}]
    result = combine_pdfs(entries, str(tmp_path / 'out.pdf'), 'Meeting', '2026-04-15')
    assert result is None


def test_creates_output_file(tmp_path):
    pdf_path = str(tmp_path / 'input.pdf')
    make_pdf(pdf_path)
    entries = [{'filepath': pdf_path, 'item_number': '10.1', 'title': 'Test Doc'}]
    output_path = str(tmp_path / 'combined.pdf')
    result = combine_pdfs(entries, output_path, 'Test Meeting', '2026-04-15')
    assert result == output_path
    assert os.path.isfile(output_path)


def test_combined_has_more_pages_than_input(tmp_path):
    pdf_path = str(tmp_path / 'input.pdf')
    make_pdf(pdf_path)
    output_path = str(tmp_path / 'combined.pdf')
    combine_pdfs([{'filepath': pdf_path, 'item_number': '10.1', 'title': 'Doc'}],
                 output_path, 'Meeting', '2026-04-15')
    assert len(PdfReader(output_path).pages) > len(PdfReader(pdf_path).pages)


def test_multiple_inputs_all_included(tmp_path):
    paths = []
    for i in range(3):
        p = str(tmp_path / f'input{i}.pdf')
        make_pdf(p, f'Page {i}')
        paths.append(p)
    entries = [{'filepath': p, 'item_number': f'10.{i+1}',
                'item_descriptor': f'Item {i+1} Desc', 'title': f'Doc {i}'}
               for i, p in enumerate(paths)]
    output_path = str(tmp_path / 'combined.pdf')
    combine_pdfs(entries, output_path, 'Meeting', '2026-04-15')
    # 1 index + 3×(1 cover + 1 doc page) = 7
    assert len(PdfReader(output_path).pages) >= 7


def test_skips_missing_files_gracefully(tmp_path):
    good_pdf = str(tmp_path / 'good.pdf')
    make_pdf(good_pdf)
    entries = [
        {'filepath': str(tmp_path / 'missing.pdf'), 'item_number': '10.1', 'title': 'Missing'},
        {'filepath': good_pdf, 'item_number': '10.2', 'title': 'Good Doc'},
    ]
    output_path = str(tmp_path / 'combined.pdf')
    result = combine_pdfs(entries, output_path, 'Meeting', '2026-04-15')
    assert result == output_path
    assert os.path.isfile(output_path)


def test_per_doc_cover_pages_inserted(tmp_path):
    """1 entry, 1-page PDF → index(1) + cover(1) + doc(1) = 3 pages total."""
    pdf_path = str(tmp_path / 'input.pdf')
    make_pdf(pdf_path)
    output_path = str(tmp_path / 'combined.pdf')
    combine_pdfs(
        [{'filepath': pdf_path, 'item_number': '10.1',
          'item_descriptor': 'Test Item', 'title': 'Test Doc'}],
        output_path, 'Meeting', '2026-04-15',
    )
    assert len(PdfReader(output_path).pages) == 3


def test_index_page_contains_city_of_mitcham(tmp_path):
    pdf_path = str(tmp_path / 'input.pdf')
    make_pdf(pdf_path)
    output_path = str(tmp_path / 'combined.pdf')
    combine_pdfs(
        [{'filepath': pdf_path, 'item_number': '10.1',
          'item_descriptor': 'Test Item', 'title': 'Test Doc'}],
        output_path, 'Full Council', '2026-01-27',
    )
    index_text = PdfReader(output_path).pages[0].extract_text()
    assert 'City of Mitcham' in index_text


def test_index_page_contains_meeting_url(tmp_path):
    """When meeting_url is provided, the meeting title appears as the clickable heading."""
    pdf_path = str(tmp_path / 'input.pdf')
    make_pdf(pdf_path)
    output_path = str(tmp_path / 'combined.pdf')
    url = 'https://mitcham.civicclerk.com.au/web/Player.aspx?id=1353'
    combine_pdfs(
        [{'filepath': pdf_path, 'item_number': '10.1',
          'item_descriptor': '', 'title': 'Test Doc'}],
        output_path, 'Full Council', '2026-01-27',
        meeting_url=url,
    )
    index_text = PdfReader(output_path).pages[0].extract_text()
    assert 'Full Council' in index_text


def test_index_page_omits_url_when_none(tmp_path):
    """When meeting_url is None, 'Full agenda:' row is absent from index."""
    pdf_path = str(tmp_path / 'input.pdf')
    make_pdf(pdf_path)
    output_path = str(tmp_path / 'combined.pdf')
    combine_pdfs(
        [{'filepath': pdf_path, 'item_number': '10.1',
          'item_descriptor': '', 'title': 'Test Doc'}],
        output_path, 'Full Council', '2026-01-27',
        meeting_url=None,
    )
    index_text = PdfReader(output_path).pages[0].extract_text()
    assert 'Full agenda:' not in index_text


def test_bookmarks_created(tmp_path):
    pdf_path = str(tmp_path / 'input.pdf')
    make_pdf(pdf_path)
    output_path = str(tmp_path / 'combined.pdf')
    combine_pdfs(
        [{'filepath': pdf_path, 'item_number': '10.1',
          'item_descriptor': 'Test Item', 'title': 'Test Doc'}],
        output_path, 'Meeting', '2026-04-15',
    )
    assert len(PdfReader(output_path).outline) > 0


def test_grouped_items_have_single_heading(tmp_path):
    """Two entries with the same item_number produce one top-level bookmark."""
    paths = [str(tmp_path / f'doc{i}.pdf') for i in range(2)]
    for p in paths:
        make_pdf(p)
    entries = [
        {'filepath': paths[0], 'item_number': '10.4',
         'item_descriptor': 'Library Opening Hours', 'title': 'Schedule'},
        {'filepath': paths[1], 'item_number': '10.4',
         'item_descriptor': 'Library Opening Hours', 'title': 'Slides'},
    ]
    output_path = str(tmp_path / 'combined.pdf')
    combine_pdfs(entries, output_path, 'Meeting', '2026-04-15')
    outline = PdfReader(output_path).outline
    top_level = [item for item in outline if not isinstance(item, list)]
    assert len(top_level) == 1
    assert '10.4' in top_level[0].title


def test_item_descriptor_shown_in_index(tmp_path):
    pdf_path = str(tmp_path / 'input.pdf')
    make_pdf(pdf_path)
    output_path = str(tmp_path / 'combined.pdf')
    combine_pdfs(
        [{'filepath': pdf_path, 'item_number': '10.4',
          'item_descriptor': 'Library Opening Hours', 'title': 'Test Doc'}],
        output_path, 'Full Council', '2026-01-27',
    )
    index_text = PdfReader(output_path).pages[0].extract_text()
    assert 'Library Opening Hours' in index_text
