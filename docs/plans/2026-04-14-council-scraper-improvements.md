# Council Scraper Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the document-detection filter so all attachment/supplementary docs are downloaded (not just ones literally labelled "Supporting Document"), add meeting URL auto-discovery from the CivicClerk portal, add skip-if-already-done logic, and wire everything up as a Windows Task Scheduler job at 5 pm every Friday.

**Architecture:** The existing three-stage scraper (`council_document_scraper.py`) is kept intact. Changes are: (1) broaden the `is_supporting_document` filter in the analyser, (2) a new `meeting_discovery.py` module that discovers agenda URLs from the CivicClerk portal page, (3) a new `scheduled_run.py` orchestrator that ties discovery → skip-check → scrape together, and (4) a `setup_task.bat` that registers the Windows scheduled task.

**Tech Stack:** Python 3, requests, BeautifulSoup, selenium (existing), pytest (new), Windows Task Scheduler (`schtasks`)

---

## Background: Root Cause

In older agendas (e.g. September 2025), supplementary documents were labelled `"Supporting Document 1 - Title"`. In April 2026 the same documents are labelled `"Attachment A - Title"`, `"Attachment B Libraries"`, etc. The existing `is_supporting_document()` only matched the literal string `"supporting document"`, so April 2026 returned 0 downloads despite having 27 GenFile links.

The fix is to also match any link text that starts with `"attachment"` or contains `"supplementary"`. Bare report variants (`"Report"`, `"Information Only Report"`, `"Corro / Resolution Report"`, `"Cover Page"`) must remain excluded.

> **Note on "Council Member Memo" style links:** These currently exist in April 2026 data. They do NOT match the attachment/supporting pattern so they will NOT be downloaded. If that should change, add `'memo'` to the inclusion set in Task 1.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `aidocs_html_analyzer_sorted.py` | Modify `:116-119` | Broadened `is_supporting_document()` |
| `tests/__init__.py` | Create | Makes tests a package |
| `tests/test_document_filter.py` | Create | Unit tests for the filter fix |
| `meeting_discovery.py` | Create | Discovers agenda URLs from CivicClerk portal |
| `tests/test_meeting_discovery.py` | Create | Unit tests for URL discovery parsing |
| `scheduled_run.py` | Create | Orchestrator: discover → skip-check → scrape → log |
| `setup_task.bat` | Create | Registers Windows Task Scheduler job (run once) |

---

## Task 1: Fix `is_supporting_document()` filter

**Files:**
- Modify: `aidocs_html_analyzer_sorted.py:116-119`
- Create: `tests/__init__.py`
- Create: `tests/test_document_filter.py`

- [ ] **Step 1.1 — Create the empty test package**

```
tests/__init__.py  (empty file)
```

- [ ] **Step 1.2 — Write the failing tests**

Create `tests/test_document_filter.py`:

```python
import pytest
from aidocs_html_analyzer_sorted import AidocsHtmlAnalyzerSorted

@pytest.fixture
def analyzer():
    return AidocsHtmlAnalyzerSorted()

# --- Should be downloaded ---
def test_attachment_with_dash(analyzer):
    assert analyzer.is_supporting_document('Attachment A - Draft Terms of Reference') is True

def test_attachment_without_dash(analyzer):
    assert analyzer.is_supporting_document('Attachment B Libraries') is True

def test_attachment_multiword(analyzer):
    assert analyzer.is_supporting_document('Attachment D Winns Bakehouse and Museum') is True

def test_attachment_lowercase(analyzer):
    assert analyzer.is_supporting_document('attachment a - something') is True

def test_supporting_document_numbered(analyzer):
    assert analyzer.is_supporting_document('Supporting Document 1 - City of Mitcham Dog Plan') is True

def test_supporting_document_unnumbered(analyzer):
    assert analyzer.is_supporting_document('Supporting Document - Behavioural Standards') is True

def test_supplementary_keyword(analyzer):
    assert analyzer.is_supporting_document('Supplementary Information - Budget') is True

# --- Should NOT be downloaded ---
def test_bare_report(analyzer):
    assert analyzer.is_supporting_document('Report') is False

def test_information_only_report(analyzer):
    assert analyzer.is_supporting_document('Information Only Report') is False

def test_corro_report(analyzer):
    assert analyzer.is_supporting_document('Corro / Resolution Report') is False

def test_cover_page(analyzer):
    assert analyzer.is_supporting_document('Cover Page') is False
```

- [ ] **Step 1.3 — Run tests to confirm they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_document_filter.py -v
```

Expected: most `is True` assertions FAIL because current code only checks `'supporting document' in text_lower`.

- [ ] **Step 1.4 — Implement the fix**

In `aidocs_html_analyzer_sorted.py`, replace lines 116–119:

```python
# OLD
def is_supporting_document(self, link_text):
    """Identify supporting documents based on text characteristics"""
    text_lower = link_text.lower()
    return 'supporting document' in text_lower
```

With:

```python
# NEW
# Bare report labels that are never supplementary attachments
_EXCLUDED_LABELS = {
    'report',
    'information only report',
    'corro / resolution report',
    'cover page',
}

def is_supporting_document(self, link_text):
    """Return True for supplementary/attachment docs; False for bare report labels.

    Matches:
      - Any text starting with 'attachment' (e.g. 'Attachment A - Title')
      - Any text containing 'supporting document'
      - Any text containing 'supplementary'
    Excludes:
      - 'Report', 'Information Only Report', 'Corro / Resolution Report', 'Cover Page'
    """
    text_lower = link_text.lower().strip()
    if text_lower in self._EXCLUDED_LABELS:
        return False
    return (
        text_lower.startswith('attachment') or
        'supporting document' in text_lower or
        'supplementary' in text_lower
    )
```

Note: `_EXCLUDED_LABELS` must be defined at class level (inside the class body, before `__init__`), not inside the method. Add it right after the class docstring / `def __init__` block, e.g.:

```python
class AidocsHtmlAnalyzerSorted:
    _EXCLUDED_LABELS = {
        'report',
        'information only report',
        'corro / resolution report',
        'cover page',
    }

    def __init__(self):
        ...
```

- [ ] **Step 1.5 — Run tests to confirm they all pass**

```
.venv\Scripts\python.exe -m pytest tests/test_document_filter.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 1.6 — Integration smoke-check: rerun analyser against saved April 2026 HTML**

```
.venv\Scripts\python.exe -c "
from aidocs_html_analyzer_sorted import AidocsHtmlAnalyzerSorted
a = AidocsHtmlAnalyzerSorted()
a.analyze_file('council_docs/14 April 2026 Full Council/aidocs_content.html')
docs = a.extract_supporting_documents_for_scraper()
print('Found', len(docs), 'docs')
for d in docs:
    print(' -', d['title'])
"
```

Expected: should find all Attachment links (approximately 25 documents based on the existing data). The bare "Report" entries should NOT appear.

- [ ] **Step 1.7 — Commit**

```
git add aidocs_html_analyzer_sorted.py tests/__init__.py tests/test_document_filter.py
```

```
printf 'fix: broaden supporting doc filter to match Attachment/Supplementary labels\n\nPreviously only matched "Supporting Document X - ..." text.\nApril 2026 agendas use "Attachment A - ...", "Attachment B ...", etc.\nNow matches any link starting with "attachment" or containing\n"supplementary", while still excluding bare Report labels.\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n' | git commit -F -
```

---

## Task 2: Meeting URL discovery module

**Files:**
- Create: `meeting_discovery.py`
- Create: `tests/test_meeting_discovery.py`

The CivicClerk portal page at `https://mitcham.civicclerk.com.au/web/` renders two grids in server-side ASP.NET WebForms: "Current and Upcoming Events" and "Most Recent Events". Both contain `<a href>` links to `Player.aspx?id=XXXX`. We parse those links from the static HTML response.

> **If the grids are loaded via async callbacks and links are absent in the static HTML:** fall back to reading `config.json` (see Step 2.8).

- [ ] **Step 2.1 — Write failing tests (with mock HTML)**

Create `tests/test_meeting_discovery.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from meeting_discovery import parse_meeting_links, discover_latest_council_meetings

SAMPLE_HTML = """
<html><body>
<div id="upcoming">
  <a href="Player.aspx?id=1402&amp;key=-1&amp;mod=-1&amp;mk=-1&amp;nov=0">
    Full Council Meeting - 13 May 2026
  </a>
  <a href="Player.aspx?id=1401&amp;key=-1&amp;mod=-1&amp;mk=-1&amp;nov=0">
    Full Council Meeting - 14 April 2026
  </a>
</div>
<div id="other">
  <a href="Player.aspx?id=1399&amp;key=-1&amp;mod=-1&amp;mk=-1&amp;nov=0">
    Special Full Council - 7 April 2026
  </a>
  <a href="SomethingElse.aspx?id=999">Not a meeting link</a>
</div>
</body></html>
"""

def test_parse_meeting_links_finds_player_urls():
    links = parse_meeting_links(SAMPLE_HTML, base_url='https://mitcham.civicclerk.com.au/web/')
    assert len(links) == 3

def test_parse_meeting_links_builds_full_urls():
    links = parse_meeting_links(SAMPLE_HTML, base_url='https://mitcham.civicclerk.com.au/web/')
    urls = [l['url'] for l in links]
    assert 'https://mitcham.civicclerk.com.au/web/Player.aspx?id=1402&key=-1&mod=-1&mk=-1&nov=0' in urls

def test_parse_meeting_links_extracts_title():
    links = parse_meeting_links(SAMPLE_HTML, base_url='https://mitcham.civicclerk.com.au/web/')
    titles = [l['title'] for l in links]
    assert any('Full Council Meeting - 13 May 2026' in t for t in titles)

def test_parse_meeting_links_ignores_non_player_links():
    links = parse_meeting_links(SAMPLE_HTML, base_url='https://mitcham.civicclerk.com.au/web/')
    urls = [l['url'] for l in links]
    assert not any('SomethingElse' in u for u in urls)

def test_discover_latest_council_meetings_calls_requests():
    with patch('meeting_discovery.requests.Session') as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        results = discover_latest_council_meetings()
        assert len(results) == 3
        mock_session.get.assert_called_once()
```

- [ ] **Step 2.2 — Run to confirm failure**

```
.venv\Scripts\python.exe -m pytest tests/test_meeting_discovery.py -v
```

Expected: `ModuleNotFoundError: No module named 'meeting_discovery'`

- [ ] **Step 2.3 — Implement `meeting_discovery.py`**

Create `meeting_discovery.py`:

```python
"""meeting_discovery.py
Discovers upcoming council meeting agenda URLs from the CivicClerk portal.
"""
import re
import json
import logging
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs

CIVICCLERK_PORTAL = 'https://mitcham.civicclerk.com.au/web/'
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')

logger = logging.getLogger(__name__)


def parse_meeting_links(html: str, base_url: str = CIVICCLERK_PORTAL) -> list[dict]:
    """Parse Player.aspx meeting links from a CivicClerk portal HTML page.

    Returns a list of dicts: [{'title': str, 'url': str, 'meeting_id': int}, ...]
    """
    soup = BeautifulSoup(html, 'html.parser')
    seen_ids = set()
    results = []

    for anchor in soup.find_all('a', href=re.compile(r'Player\.aspx', re.I)):
        href = anchor.get('href', '')
        full_url = urljoin(base_url, href)
        title = anchor.get_text(separator=' ', strip=True)

        # Extract numeric meeting ID
        qs = parse_qs(urlparse(full_url).query)
        id_list = qs.get('id', [])
        if not id_list:
            continue
        try:
            meeting_id = int(id_list[0])
        except ValueError:
            continue

        if meeting_id in seen_ids:
            continue
        seen_ids.add(meeting_id)

        results.append({'title': title, 'url': full_url, 'meeting_id': meeting_id})

    # Sort highest ID (most recent) first — CivicClerk IDs are sequential
    results.sort(key=lambda x: x['meeting_id'], reverse=True)
    return results


def discover_latest_council_meetings(portal_url: str = CIVICCLERK_PORTAL) -> list[dict]:
    """Fetch the CivicClerk portal page and return parsed meeting links.

    Falls back to config.json if the portal page returns no links (JS-rendered content).
    Returns list of dicts sorted newest-first.
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    try:
        logger.info(f'[DISCOVERY] Fetching portal: {portal_url}')
        response = session.get(portal_url, timeout=15)
        response.raise_for_status()
        links = parse_meeting_links(response.text, base_url=portal_url)
        if links:
            logger.info(f'[DISCOVERY] Found {len(links)} meetings on portal page')
            return links
        logger.warning('[DISCOVERY] No Player.aspx links found in portal HTML (may be JS-rendered)')
    except Exception as e:
        logger.error(f'[DISCOVERY] Portal fetch failed: {e}')

    # Fallback: read config.json
    return _load_from_config()


def _load_from_config() -> list[dict]:
    """Load meeting URL(s) from config.json fallback."""
    if not os.path.exists(CONFIG_FILE):
        logger.error(f'[DISCOVERY] No config.json found at {CONFIG_FILE}')
        return []

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        entries = cfg.get('meetings', [])
        logger.info(f'[DISCOVERY] Loaded {len(entries)} meetings from config.json')
        return entries
    except Exception as e:
        logger.error(f'[DISCOVERY] Failed to read config.json: {e}')
        return []
```

- [ ] **Step 2.4 — Run tests to confirm they pass**

```
.venv\Scripts\python.exe -m pytest tests/test_meeting_discovery.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 2.5 — Live smoke-check (requires internet)**

```
.venv\Scripts\python.exe -c "
import logging
logging.basicConfig(level=logging.INFO)
from meeting_discovery import discover_latest_council_meetings
meetings = discover_latest_council_meetings()
for m in meetings[:5]:
    print(m['meeting_id'], '|', m['title'][:60], '|', m['url'][:80])
"
```

Expected: prints 3–10 recent meetings with IDs and titles.

> **If zero links are returned:** the portal page is fully JS-rendered. In that case, create `config.json` (see Step 2.8) and re-run; discovery will use the fallback.

- [ ] **Step 2.6 — Create `config.json` fallback template**

Create `config.json`:

```json
{
  "_comment": "Manual fallback used when CivicClerk portal page is JS-rendered. Add meetings here.",
  "meetings": [
    {
      "title": "Full Council Meeting - 14 April 2026",
      "url": "https://mitcham.civicclerk.com.au/web/Player.aspx?id=1401&key=-1&mod=-1&mk=-1&nov=0",
      "meeting_id": 1401
    }
  ]
}
```

- [ ] **Step 2.7 — Add `config.json` to `.gitignore` (contains local overrides)**

```
echo 'config.json' >> .gitignore
```

- [ ] **Step 2.8 — Commit**

```
git add meeting_discovery.py tests/test_meeting_discovery.py config.json .gitignore
```

```
printf 'feat: add meeting URL discovery module\n\nFetches Player.aspx links from CivicClerk portal page.\nFalls back to config.json if portal returns no links.\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n' | git commit -F -
```

---

## Task 3: Add skip-if-already-done logic

The scraper should skip a meeting if `council_docs/<folder>/target_downloads.json` exists **and** at least one PDF is present in that folder.

**Files:**
- Modify: `council_document_scraper.py` — add `is_already_scraped()` method and call it in `scrape_agenda()`
- Create: `tests/test_skip_logic.py`

- [ ] **Step 3.1 — Write failing test**

Create `tests/test_skip_logic.py`:

```python
import os
import json
import tempfile
import pytest
from council_document_scraper import CouncilDocumentScraper


@pytest.fixture
def scraper(tmp_path):
    return CouncilDocumentScraper(output_folder=str(tmp_path), log_level='WARNING')


def test_not_scraped_when_folder_missing(scraper, tmp_path):
    assert scraper.is_already_scraped(str(tmp_path / 'NonExistentMeeting')) is False


def test_not_scraped_when_no_pdfs(scraper, tmp_path):
    folder = tmp_path / 'SomeMeeting'
    folder.mkdir()
    targets = [{'title': 'Doc 1', 'url': 'x', 'recommended_filename': 'f.pdf',
                'doc_number': 1, 'ad_value': 100}]
    (folder / 'target_downloads.json').write_text(json.dumps(targets))
    # No PDF files present
    assert scraper.is_already_scraped(str(folder)) is False


def test_already_scraped_when_pdf_exists(scraper, tmp_path):
    folder = tmp_path / 'SomeMeeting'
    folder.mkdir()
    targets = [{'title': 'Doc 1', 'url': 'x', 'recommended_filename': 'f.pdf',
                'doc_number': 1, 'ad_value': 100}]
    (folder / 'target_downloads.json').write_text(json.dumps(targets))
    (folder / 'SD_100_Something.pdf').write_bytes(b'%PDF fake')
    assert scraper.is_already_scraped(str(folder)) is True
```

- [ ] **Step 3.2 — Run to confirm failure**

```
.venv\Scripts\python.exe -m pytest tests/test_skip_logic.py -v
```

Expected: `AttributeError: 'CouncilDocumentScraper' object has no attribute 'is_already_scraped'`

- [ ] **Step 3.3 — Add `is_already_scraped()` to `council_document_scraper.py`**

Add this method to the `CouncilDocumentScraper` class, after `sanitize_folder_name()`:

```python
def is_already_scraped(self, meeting_folder_path):
    """Return True if meeting_folder_path contains at least one PDF."""
    if not os.path.isdir(meeting_folder_path):
        return False
    pdfs = [f for f in os.listdir(meeting_folder_path) if f.lower().endswith('.pdf')]
    return len(pdfs) > 0
```

- [ ] **Step 3.4 — Run tests to confirm they pass**

```
.venv\Scripts\python.exe -m pytest tests/test_skip_logic.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 3.5 — Commit**

```
git add council_document_scraper.py tests/test_skip_logic.py
```

```
printf 'feat: add is_already_scraped() skip-check method\n\nReturns True if the output folder already contains PDFs,\navoiding redundant re-downloads on repeat Friday runs.\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n' | git commit -F -
```

---

## Task 4: Create `scheduled_run.py` orchestrator

**Files:**
- Create: `scheduled_run.py`

This script:
1. Discovers meeting URLs (from portal or config override)
2. For each meeting, checks if already scraped (skip unless `--force`)
3. Scrapes any new meetings
4. Writes a plain-text run log entry to `run_log.txt`

CLI usage:
```
# Auto-discover and scrape any new meetings
python scheduled_run.py

# Force re-scrape a specific meeting
python scheduled_run.py --url "https://mitcham.civicclerk.com.au/web/Player.aspx?id=1401&key=-1&mod=-1&mk=-1&nov=0" --force

# Dry run - show what would be scraped without doing it
python scheduled_run.py --dry-run
```

- [ ] **Step 4.1 — Create `scheduled_run.py`**

```python
"""scheduled_run.py
Orchestrator for the weekly Friday council agenda scrape.

Usage:
    python scheduled_run.py                            # auto-discover, skip done
    python scheduled_run.py --url URL [--force]        # specific meeting, optionally force
    python scheduled_run.py --dry-run                  # show what would run, no downloads
"""
import argparse
import logging
import os
import sys
from datetime import datetime

from council_document_scraper import CouncilDocumentScraper
from meeting_discovery import discover_latest_council_meetings

OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), 'council_docs')
RUN_LOG = os.path.join(os.path.dirname(__file__), 'run_log.txt')


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('council_scraper.log', encoding='utf-8'),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)


def append_run_log(entries: list[str]):
    """Append a timestamped block to run_log.txt."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(RUN_LOG, 'a', encoding='utf-8') as f:
        f.write(f'\n=== Run at {timestamp} ===\n')
        for line in entries:
            f.write(line + '\n')


def main():
    parser = argparse.ArgumentParser(description='Mitcham Council Agenda Scraper - Scheduled Run')
    parser.add_argument('--url', help='Override: scrape this specific agenda URL')
    parser.add_argument('--force', action='store_true',
                        help='Re-scrape even if already downloaded')
    parser.add_argument('--dry-run', action='store_true',
                        help='Discover and show meetings without downloading')
    args = parser.parse_args()

    logger = setup_logging()
    scraper = CouncilDocumentScraper(output_folder=OUTPUT_FOLDER)
    log_entries = []

    # --- Determine meetings to process ---
    if args.url:
        meetings = [{'title': 'Manual override', 'url': args.url, 'meeting_id': 0}]
        logger.info(f'[SCHEDULED] Using provided URL: {args.url}')
    else:
        meetings = discover_latest_council_meetings()
        if not meetings:
            msg = 'No meetings discovered. Check portal or config.json.'
            logger.error(f'[SCHEDULED] {msg}')
            append_run_log([msg])
            sys.exit(1)

    logger.info(f'[SCHEDULED] {len(meetings)} meeting(s) discovered')

    # --- Process each meeting ---
    scraped_count = 0
    skipped_count = 0

    for meeting in meetings:
        url = meeting['url']
        title = meeting.get('title', 'Unknown')
        logger.info(f'[SCHEDULED] Considering: {title}')

        # Determine expected output folder (scraper will create it; check by sanitised title)
        sanitised = scraper.sanitize_folder_name(title)
        folder_path = os.path.join(OUTPUT_FOLDER, sanitised)

        if not args.force and scraper.is_already_scraped(folder_path):
            msg = f'SKIP (already done): {title}'
            logger.info(f'[SCHEDULED] {msg}')
            log_entries.append(msg)
            skipped_count += 1
            continue

        if args.dry_run:
            msg = f'DRY-RUN (would scrape): {title} | {url}'
            logger.info(f'[SCHEDULED] {msg}')
            log_entries.append(msg)
            continue

        logger.info(f'[SCHEDULED] Scraping: {title}')
        result = scraper.scrape_agenda(url)

        if result['status'] == 'success':
            msg = (f'OK: {result["meeting_title"]} | '
                   f'{result["total_supporting_docs"]} docs found | '
                   f'{result["successful_downloads"]} downloaded | '
                   f'{result["failed_downloads"]} failed')
        else:
            msg = f'ERROR: {title} | {result.get("error_message", "unknown error")}'

        logger.info(f'[SCHEDULED] {msg}')
        log_entries.append(msg)
        scraped_count += 1

    summary = (f'Summary: {scraped_count} scraped, {skipped_count} skipped'
               + (' [DRY RUN]' if args.dry_run else ''))
    logger.info(f'[SCHEDULED] {summary}')
    log_entries.append(summary)
    append_run_log(log_entries)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4.2 — Smoke-test dry run (no downloads)**

```
.venv\Scripts\python.exe scheduled_run.py --dry-run
```

Expected: prints discovered meetings labelled `DRY-RUN (would scrape): ...`, no files downloaded.

- [ ] **Step 4.3 — Smoke-test with the April 2026 URL and --force**

```
.venv\Scripts\python.exe scheduled_run.py --url "https://mitcham.civicclerk.com.au/web/Player.aspx?id=1401&key=-1&mod=-1&mk=-1&nov=0" --force
```

Expected: scrapes April 2026, downloads all Attachment docs into `council_docs/14 April 2026 Full Council/`, prints success summary.

Verify:
```
ls "council_docs/14 April 2026 Full Council/"
```

Expected: multiple `SD_*.pdf` files present.

- [ ] **Step 4.4 — Verify run_log.txt was written**

```
cat run_log.txt
```

Expected: timestamped block with `OK: 14 April 2026 Full Council | ...` entry.

- [ ] **Step 4.5 — Commit**

```
git add scheduled_run.py
```

```
printf 'feat: add scheduled_run.py orchestrator\n\nDiscovers meetings, skips already-done ones, scrapes new ones,\nappends results to run_log.txt. Supports --url, --force, --dry-run.\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n' | git commit -F -
```

---

## Task 5: Windows Task Scheduler setup

**Files:**
- Create: `setup_task.bat`

Registers a Task Scheduler job to run `scheduled_run.py` every Friday at 17:00 using the project's venv Python.

- [ ] **Step 5.1 — Create `setup_task.bat`**

```bat
@echo off
:: Run this once as Administrator to register the weekly scrape task.
:: To remove: schtasks /delete /tn "MitchamCouncilScraper" /f

set TASK_NAME=MitchamCouncilScraper
set PYTHON=%~dp0.venv\Scripts\python.exe
set SCRIPT=%~dp0scheduled_run.py
set LOG=%~dp0council_scraper.log

echo Registering task: %TASK_NAME%
echo Python: %PYTHON%
echo Script: %SCRIPT%

schtasks /create /tn "%TASK_NAME%" /tr "\"%PYTHON%\" \"%SCRIPT%\"" /sc weekly /d FRI /st 17:00 /f /rl HIGHEST

if %errorlevel% == 0 (
    echo.
    echo Task registered successfully.
    echo It will run every Friday at 5:00 PM.
    echo To run immediately: schtasks /run /tn "%TASK_NAME%"
    echo To view log:        type "%LOG%"
    echo To delete task:     schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo.
    echo ERROR: Failed to register task. Try running as Administrator.
)
pause
```

- [ ] **Step 5.2 — Verify the bat file content reads back correctly**

```
cat setup_task.bat
```

Expected: bat file printed with the correct paths and task name.

- [ ] **Step 5.3 — Register the task (run as Administrator)**

Right-click `setup_task.bat` → "Run as administrator", OR in an elevated terminal:

```
setup_task.bat
```

Expected: `Task registered successfully.`

- [ ] **Step 5.4 — Verify task exists in Task Scheduler**

```
schtasks /query /tn MitchamCouncilScraper /fo LIST
```

Expected: output showing `Task Name: MitchamCouncilScraper`, `Schedule Type: Weekly`, `Days: Fri`, `Start Time: 5:00:00 PM`.

- [ ] **Step 5.5 — Test on-demand run via Task Scheduler**

```
schtasks /run /tn MitchamCouncilScraper
```

Then check `run_log.txt` and `council_scraper.log` for the run output.

- [ ] **Step 5.6 — Commit**

```
git add setup_task.bat
```

```
printf 'feat: add Windows Task Scheduler setup bat\n\nRegisters MitchamCouncilScraper task to run every Friday at 17:00.\nRun setup_task.bat as Administrator once to activate.\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n' | git commit -F -
```

---

## Self-Review: Spec Coverage Check

| Requirement | Covered by |
|-------------|------------|
| Fix missing supporting docs in April 2026 | Task 1 — filter updated |
| Catch all attachments regardless of naming | Task 1 — `startswith('attachment')` + `supplementary` |
| Don't download bare Reports | Task 1 — `_EXCLUDED_LABELS` set |
| URL auto-discovery from Mitcham council page | Task 2 — `meeting_discovery.py` |
| Direct URL override where only id varies | Task 4 — `--url` flag |
| Run every Friday at 5pm | Task 5 — Task Scheduler |
| On-demand run | Task 4 — `python scheduled_run.py` or `schtasks /run` |
| Log file notification | Task 4 — `run_log.txt` + `council_scraper.log` |
| Skip if already done | Task 3 — `is_already_scraped()` |
| Same output folder | All tasks — `council_docs/` hardcoded as default |
| Special meetings (ad hoc) | Task 2 — discovery returns all Player.aspx links, not just regular meetings |

**Open question:** The discovery module checks `https://mitcham.civicclerk.com.au/web/` for Player.aspx links. If that page renders its grids via JavaScript (the CivicClerk portal uses ASP.NET WebForms callbacks), the static HTML fetch will return zero links. In that case, the user must populate `config.json` manually with the meeting URL before each Friday run. A future improvement could add Selenium-based portal scraping, but that is out of scope here.
