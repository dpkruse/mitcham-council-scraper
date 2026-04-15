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
    entries = [{'filepath': p, 'item_number': f'10.{i+1}', 'title': f'Doc {i}'}
               for i, p in enumerate(paths)]
    output_path = str(tmp_path / 'combined.pdf')
    combine_pdfs(entries, output_path, 'Meeting', '2026-04-15')
    # cover page (1) + 3 input pages = 4 minimum
    assert len(PdfReader(output_path).pages) >= 4


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
