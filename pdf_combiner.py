"""pdf_combiner.py
Combines downloaded supporting-document PDFs into a single file with:
- A grouped cover/index page (by agenda item)
- A per-document cover page before each PDF
- PDF bookmarks for quick navigation
- Clickable internal links from index rows to cover pages
- A footer crediting the tool
- A clickable heading linking to the full meeting agenda
"""
import io
import logging
import os
import re
from collections import OrderedDict
from datetime import datetime

from pypdf import PdfWriter, PdfReader
from pypdf.annotations import Link
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4


logger = logging.getLogger(__name__)

GITHUB_URL = 'https://github.com/dpkruse/mitcham-council-scraper'
GITHUB_DISPLAY = 'github.com/dpkruse/mitcham-council-scraper'

# Colour palette aligned with Mitcham council website CSS
_C_HEADING = (0.208, 0.208, 0.212)  # #353536 — headings
_C_BODY = (0.290, 0.290, 0.290)     # #4A4A4A — body text
_C_LINK = (0, 0.427, 0.314)         # #006d50 — website active/hover link (teal)
_C_LINK_BLUE = (0, 0.341, 0.659)    # #0057A8 — blue for footer GitHub link
_C_GREY = (0.55, 0.55, 0.55)        # secondary / metadata grey


def _display_title(entry):
    """Reformat 'Supporting Document N: title' → 'Supporting document N — title'."""
    raw = entry.get('title', os.path.basename(entry['filepath']))
    match = re.match(r'^Supporting Document (\d+)\s*[-:]?\s*', raw, flags=re.IGNORECASE)
    if match:
        num = match.group(1)
        rest = raw[match.end():].strip()
        return f'Supporting document {num} \u2014 {rest}'
    return f'Supporting document \u2014 {raw.strip()}'


def _wrap_lines(text, c, font_name, font_size, max_width):
    """Split text into lines that each fit within max_width points."""
    words = text.split()
    lines, current = [], ''
    for word in words:
        test = (current + ' ' + word).strip()
        if c.stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _truncate_to_width(text, c, font_name, font_size, max_width):
    """Truncate text with ellipsis to fit within max_width points."""
    if c.stringWidth(text, font_name, font_size) <= max_width:
        return text
    while len(text) > 4 and c.stringWidth(text + '\u2026', font_name, font_size) > max_width:
        text = text[:-1]
    return text + '\u2026'


def _build_index_page(groups, page_map, meeting_title, run_date, meeting_url):
    """Return (BytesIO, link_records) for the index/cover page PDF.

    link_records: list of (filepath, x1, y1, x2, y2, page_in_index)
    where coordinates are PDF points (bottom-left origin) and
    page_in_index is 0-based within the index PDF.
    """
    width, height = A4
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)

    current_index_page = 0
    link_records = []

    # --- Main heading: word-wrapped; clickable link to meeting if URL provided ---
    heading_text = f'City of Mitcham \u2014 {meeting_title}'
    heading_lines = _wrap_lines(heading_text, c, 'Helvetica-Bold', 15, width - 80)
    c.setFont('Helvetica-Bold', 15)
    c.setFillColorRGB(*(_C_LINK if meeting_url else _C_HEADING))
    for i, line in enumerate(heading_lines):
        line_y = height - 50 - i * 19
        c.drawString(40, line_y, line)
        if meeting_url:
            lw = c.stringWidth(line, 'Helvetica-Bold', 15)
            c.linkURL(meeting_url, (40, line_y - 4, 40 + lw, line_y + 13), relative=0)

    y_subhead = height - 50 - (len(heading_lines) - 1) * 19 - 19
    c.setFont('Helvetica', 10)
    c.setFillColorRGB(*_C_BODY)
    c.drawString(40, y_subhead, f'{run_date}  \u00b7  Supporting Documents')

    y = y_subhead - 22

    # --- Rule ---
    y -= 4
    c.setFillColorRGB(*_C_BODY)
    c.line(40, y, width - 40, y)
    y -= 14

    # --- Grouped table ---
    for (item_number, item_descriptor), entries in groups.items():
        # Group heading — may wrap for long descriptors
        heading = (f'{item_number}  {item_descriptor}'.strip()
                   if item_descriptor else item_number)
        c.setFont('Helvetica-Bold', 10)
        heading_lines_g = _wrap_lines(heading, c, 'Helvetica-Bold', 10, width - 80)

        # Ensure heading + at least one doc row fits on this page
        needed = len(heading_lines_g) * 13 + 3 + 13
        if y - needed < 80:
            c.showPage()
            current_index_page += 1
            y = height - 55

        c.setFont('Helvetica-Bold', 10)
        c.setFillColorRGB(*_C_HEADING)
        for i, hline in enumerate(heading_lines_g):
            c.drawString(40, y - i * 13, hline)
        y -= (len(heading_lines_g) - 1) * 13 + 3
        c.setFillColorRGB(*_C_BODY)
        c.line(40, y, width - 40, y)
        y -= 13

        # Document rows
        c.setFont('Helvetica', 9)
        c.setFillColorRGB(*_C_BODY)
        for entry in entries:
            if y < 80:
                c.showPage()
                current_index_page += 1
                y = height - 55
                c.setFont('Helvetica', 9)
                c.setFillColorRGB(*_C_BODY)

            full_title = _display_title(entry)
            pg_text = str(page_map.get(entry['filepath'], '?'))
            pg_width = c.stringWidth(pg_text, 'Helvetica', 9)
            available = width - 40 - 52 - pg_width - 10
            title = _truncate_to_width(full_title, c, 'Helvetica', 9, available)

            c.drawString(52, y, title)
            c.drawRightString(width - 40, y, pg_text)

            link_records.append((
                entry['filepath'],
                52, y - 3, width - 40, y + 10,
                current_index_page,
            ))
            y -= 13

        y -= 4  # gap between groups

    # --- Three-line footer ---
    COUNCILLOR_URL = ('https://www.mitchamcouncil.sa.gov.au/Our-city-and-council'
                      '/your-council/meet-your-council-members/kruse,-darren')
    c.setFont('Helvetica', 8)
    c.setFillColorRGB(*_C_GREY)
    c.drawCentredString(width / 2, 52, 'Generated by Mitcham Council supporting document scraper')

    # Second line: "Scraper written by " + blue clickable "Councillor Darren Kruse"
    prefix2 = 'Scraper written by '
    name_text = 'Councillor Darren Kruse'
    full2 = prefix2 + name_text
    full2_w = c.stringWidth(full2, 'Helvetica', 8)
    prefix2_w = c.stringWidth(prefix2, 'Helvetica', 8)
    name_w = c.stringWidth(name_text, 'Helvetica', 8)
    line2_start_x = width / 2 - full2_w / 2
    c.setFillColorRGB(*_C_GREY)
    c.drawString(line2_start_x, 40, prefix2)
    c.setFillColorRGB(*_C_LINK_BLUE)
    c.drawString(line2_start_x + prefix2_w, 40, name_text)
    c.linkURL(COUNCILLOR_URL, (line2_start_x + prefix2_w, 38, line2_start_x + prefix2_w + name_w, 48), relative=0)

    # Third line: grey prefix + blue clickable GitHub link, centred together
    prefix = 'Code online at '
    full_w = c.stringWidth(prefix + GITHUB_DISPLAY, 'Helvetica', 8)
    prefix_w = c.stringWidth(prefix, 'Helvetica', 8)
    link_w = c.stringWidth(GITHUB_DISPLAY, 'Helvetica', 8)
    line_start_x = width / 2 - full_w / 2
    c.setFillColorRGB(*_C_GREY)
    c.drawString(line_start_x, 28, prefix)
    c.setFillColorRGB(*_C_LINK_BLUE)
    c.drawString(line_start_x + prefix_w, 28, GITHUB_DISPLAY)
    c.linkURL(GITHUB_URL, (line_start_x + prefix_w, 26, line_start_x + prefix_w + link_w, 36), relative=0)

    c.setFillColorRGB(0, 0, 0)
    c.save()
    buf.seek(0)
    return buf, link_records


def _build_cover_page(entry, meeting_title, run_date, n, m):
    """Return a BytesIO containing one per-document cover page."""
    width, height = A4
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)

    item_number = entry.get('item_number', '')
    item_descriptor = entry.get('item_descriptor', '')
    doc_title = _display_title(entry)

    # Top grey metadata line
    c.setFont('Helvetica', 8)
    c.setFillColorRGB(*_C_GREY)
    c.drawCentredString(
        width / 2, height - 60,
        f'City of Mitcham  \u00b7  {meeting_title}  \u00b7  {run_date}',
    )

    # Item line (medium bold, word-wrapped)
    item_line = (f'Item {item_number}  \u00b7  {item_descriptor}'
                 if item_descriptor else f'Item {item_number}')
    c.setFont('Helvetica-Bold', 12)
    item_lines = _wrap_lines(item_line, c, 'Helvetica-Bold', 12, width - 80)
    item_line_h = len(item_lines) * 16

    # Document title (large bold, word-wrapped)
    c.setFont('Helvetica-Bold', 16)
    doc_lines = _wrap_lines(doc_title, c, 'Helvetica-Bold', 16, width - 80)
    doc_line_h = len(doc_lines) * 22

    # Centre both blocks together vertically
    gap = 22
    total_h = item_line_h + gap + doc_line_h
    block_top = height / 2 + total_h / 2

    c.setFont('Helvetica-Bold', 12)
    c.setFillColorRGB(*_C_HEADING)
    for i, il in enumerate(item_lines):
        c.drawCentredString(width / 2, block_top - i * 16, il)

    c.setFont('Helvetica-Bold', 16)
    doc_top = block_top - item_line_h - gap
    for i, dl in enumerate(doc_lines):
        c.drawCentredString(width / 2, doc_top - i * 22, dl)

    # Bottom note
    c.line(40, 60, width - 40, 60)
    c.setFont('Helvetica', 9)
    c.setFillColorRGB(*_C_GREY)
    c.drawCentredString(width / 2, 45, f'Supporting document {n} of {m} for this item')

    c.setFillColorRGB(0, 0, 0)
    c.save()
    buf.seek(0)
    return buf


def combine_pdfs(pdf_entries, output_path, meeting_title, run_date=None, meeting_url=None):
    """Merge PDFs with a grouped cover page, per-document covers, and bookmarks.

    Args:
        pdf_entries: list of dicts with keys:
            'filepath'        — path to the PDF file
            'item_number'     — agenda item number, e.g. '10.4'
            'item_descriptor' — agenda item title, e.g. '4 Library Opening Hours' (optional)
            'title'           — raw document title (optional)
        output_path:  full path for the output combined PDF
        meeting_title: displayed in headings
        run_date:     date string (defaults to today)
        meeting_url:  Player.aspx URL; used as clickable link on index heading (optional)

    Returns:
        output_path on success, None if no valid input files exist.
    """
    if run_date is None:
        run_date = datetime.now().strftime('%Y-%m-%d')

    valid_entries = [e for e in pdf_entries if os.path.isfile(e['filepath'])]
    if not valid_entries:
        return None

    # --- Group entries by (item_number, item_descriptor) preserving order ---
    groups = OrderedDict()
    for entry in valid_entries:
        key = (entry.get('item_number', ''), entry.get('item_descriptor', ''))
        groups.setdefault(key, []).append(entry)

    # --- Precompute N-of-M counts for cover pages ---
    cover_position = {}  # filepath -> (n, m)
    for entries in groups.values():
        m = len(entries)
        for i, entry in enumerate(entries):
            cover_position[entry['filepath']] = (i + 1, m)

    # --- Pass 1: calculate 1-indexed page numbers for the index ToC ---
    # Page 1 = index. Then each entry: 1 cover page + its own pages.
    page_map = {}
    current_page = 2
    for entry in valid_entries:
        page_map[entry['filepath']] = current_page
        current_page += 1  # cover page
        try:
            current_page += len(PdfReader(entry['filepath']).pages)
        except Exception as e:
            logger.warning(f'[COMBINER] Could not read page count for {entry["filepath"]}: {e}')
            current_page += 1

    # --- Build index page ---
    index_buf, link_records = _build_index_page(
        groups, page_map, meeting_title, run_date, meeting_url
    )

    # --- Assemble writer ---
    writer = PdfWriter()

    index_reader = PdfReader(index_buf)
    for page in index_reader.pages:
        writer.add_page(page)

    bookmark_page = {}      # filepath -> 0-indexed page of its cover
    group_first_page = {}   # group key -> 0-indexed page of first cover in group

    page_idx = len(index_reader.pages)

    for entry in valid_entries:
        key = (entry.get('item_number', ''), entry.get('item_descriptor', ''))
        n, m = cover_position[entry['filepath']]

        cover_buf = _build_cover_page(entry, meeting_title, run_date, n, m)
        cover_pages = PdfReader(cover_buf).pages
        for page in cover_pages:
            writer.add_page(page)

        bookmark_page[entry['filepath']] = page_idx
        group_first_page.setdefault(key, page_idx)
        page_idx += len(cover_pages)

        try:
            doc_pages = PdfReader(entry['filepath']).pages
            for page in doc_pages:
                writer.add_page(page)
            page_idx += len(doc_pages)
        except Exception as e:
            logger.warning(f'[COMBINER] Could not read pages from {entry["filepath"]}: {e}')
            page_idx += 1

    # --- Internal link annotations: index rows → cover pages ---
    for filepath, x1, y1, x2, y2, index_page_num in link_records:
        if filepath not in bookmark_page:
            continue
        try:
            annotation = Link(
                rect=(x1, y1, x2, y2),
                target_page_index=bookmark_page[filepath],
            )
            writer.add_annotation(page_number=index_page_num, annotation=annotation)
        except Exception as e:
            logger.warning(f'[COMBINER] Could not add link annotation for {filepath}: {e}')

    # --- PDF bookmarks (outline) ---
    for (item_number, item_descriptor), entries in groups.items():
        heading = (f'{item_number}  {item_descriptor}'.strip()
                   if item_descriptor else item_number)
        try:
            parent = writer.add_outline_item(
                heading, group_first_page[(item_number, item_descriptor)]
            )
            for entry in entries:
                writer.add_outline_item(
                    _display_title(entry),
                    bookmark_page[entry['filepath']],
                    parent=parent,
                )
        except AttributeError:
            parent = writer.add_bookmark(
                heading, group_first_page[(item_number, item_descriptor)]
            )
            for entry in entries:
                writer.add_bookmark(
                    _display_title(entry),
                    bookmark_page[entry['filepath']],
                    parent=parent,
                )

    with open(output_path, 'wb') as f:
        writer.write(f)

    return output_path
