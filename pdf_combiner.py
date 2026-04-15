"""pdf_combiner.py
Combines downloaded supporting-document PDFs into a single file
with a cover page listing all documents and their page numbers.
"""
import io
import os
import re
from datetime import datetime


def combine_pdfs(pdf_entries, output_path, meeting_title, run_date=None):
    """Merge PDFs with a cover-page table of contents.

    Args:
        pdf_entries: list of {'filepath': str, 'item_number': str, 'title': str}
        output_path: full path for the output combined PDF
        meeting_title: displayed as heading on the cover page
        run_date: date string for cover page (defaults to today's date)

    Returns:
        output_path on success, None if no valid input files exist.
    """
    from pypdf import PdfWriter, PdfReader
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4

    if run_date is None:
        run_date = datetime.now().strftime('%Y-%m-%d')

    valid_entries = [e for e in pdf_entries if os.path.isfile(e['filepath'])]
    if not valid_entries:
        return None

    width, height = A4

    # --- Pass 1: determine page numbers for the ToC ---
    # Page 1 is the cover; content starts at page 2.
    page_map = {}
    current_page = 2
    for entry in valid_entries:
        page_map[entry['filepath']] = current_page
        try:
            current_page += len(PdfReader(entry['filepath']).pages)
        except Exception:
            current_page += 1

    # --- Build cover page in memory ---
    cover_buf = io.BytesIO()
    c = rl_canvas.Canvas(cover_buf, pagesize=A4)

    # Heading
    c.setFont('Helvetica-Bold', 15)
    c.drawString(40, height - 55, meeting_title)
    c.setFont('Helvetica', 10)
    c.drawString(40, height - 75, f'Supporting Documents  —  Run date: {run_date}')

    # Table header
    y = height - 110
    c.setFont('Helvetica-Bold', 10)
    c.drawString(40, y, 'Item')
    c.drawString(95, y, 'Document title')
    c.drawString(width - 55, y, 'Page')
    y -= 4
    c.line(40, y, width - 40, y)
    y -= 14

    # Table rows
    c.setFont('Helvetica', 9)
    for entry in valid_entries:
        item_str = entry.get('item_number', '')
        raw_title = entry.get('title', os.path.basename(entry['filepath']))
        display_title = re.sub(
            r'^Supporting Document \d+\s*[-:]?\s*', '', raw_title,
            flags=re.IGNORECASE).strip()
        if len(display_title) > 68:
            display_title = display_title[:65] + '...'
        pg = str(page_map.get(entry['filepath'], '?'))
        c.drawString(40, y, item_str)
        c.drawString(95, y, display_title)
        c.drawString(width - 55, y, pg)
        y -= 13
        if y < 55:
            c.showPage()
            y = height - 55
            c.setFont('Helvetica', 9)

    c.save()
    cover_buf.seek(0)

    # --- Merge cover + content ---
    writer = PdfWriter()

    for page in PdfReader(cover_buf).pages:
        writer.add_page(page)

    for entry in valid_entries:
        try:
            for page in PdfReader(entry['filepath']).pages:
                writer.add_page(page)
        except Exception:
            pass  # skip unreadable files silently

    with open(output_path, 'wb') as f:
        writer.write(f)

    return output_path
