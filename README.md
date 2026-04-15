# Mitcham Council Agenda Scraper

Automatically downloads separately-uploaded supporting documents from
[Mitcham Council](https://www.mitchamcouncil.sa.gov.au) meeting agendas
published on the CivicClerk portal.

## What it does

1. Fetches the AIDocs HTML for a council meeting agenda
2. Identifies separately-uploaded supporting documents (see [Document Detection](#document-detection))
3. Downloads each document, naming it `Item X.Y Title.pdf`
4. Optionally combines all downloaded PDFs into a single file with a cover-page index
5. Writes a markdown run summary (`_run_summary.txt`) into the meeting folder

Output is saved to `council_docs/{Meeting Title}/`.

## Setup

**Requirements:** Python 3.11+, Google Chrome, ChromeDriver matching your Chrome version

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

ChromeDriver must be on your PATH or in the project folder.

## Usage

```bash
# Auto-discover latest meeting (uses config.json) and scrape if not already done
python scheduled_run.py

# Scrape a specific meeting URL
python scheduled_run.py --url "https://mitcham.civicclerk.com.au/web/Player.aspx?id=1401&key=-1&mod=-1&mk=-1&nov=0"

# Force re-scrape even if already downloaded
python scheduled_run.py --url URL --force

# Create a combined PDF with cover-page index after downloading
python scheduled_run.py --url URL --combine

# See what would be scraped without downloading anything
python scheduled_run.py --dry-run
```

## Scheduled automation (Windows)

Run `setup_task.bat` **once as Administrator** to register a Windows Task Scheduler
job that runs the scraper every Friday at 5:00 PM:

```
setup_task.bat
```

To run on demand:  `schtasks /run /tn MitchamCouncilScraper`
To remove the task: `schtasks /delete /tn MitchamCouncilScraper /f`

## Meeting URL discovery

The CivicClerk portal uses JavaScript rendering, so meeting URLs cannot be
scraped automatically from the portal homepage. Before each run, add the
upcoming meeting URL to `config.json`:

```json
{
  "meetings": [
    {
      "title": "Full Council Meeting - 13 May 2026",
      "url": "https://mitcham.civicclerk.com.au/web/Player.aspx?id=XXXX&key=-1&mod=-1&mk=-1&nov=0",
      "meeting_id": XXXX
    }
  ]
}
```

The meeting ID appears in the URL on the council website's
[Minutes and Agendas](https://www.mitchamcouncil.sa.gov.au/Our-city-and-council/your-council/minutes-and-agendas) page.

## Document detection

### Why Approach A (exclusion-based)?

Council meeting agenda viewers show two types of linked documents:

- **Agenda-embedded documents** (`Report`, `Attachment A`, `Attachment B`, …) — these are
  sections _inside_ the agenda PDF. They do not need to be downloaded separately.
- **Separately-uploaded supporting documents** (`Supporting Document N - Title`,
  `Council Member Memo …`, etc.) — independent files uploaded alongside the agenda.
  **These are what this tool downloads.**

The filter uses **exclusion-based detection**: any link whose text is _not_ a known
embedded-doc label (Report, Attachment X, Information Only Report, Cover Page) is
treated as a supporting document to download.

**Why not inclusion-based?** An inclusion-based approach (matching `Supporting Document`,
`Supplementary`, etc. explicitly) breaks silently when the council changes naming
conventions — as happened between the September 2025 agendas (`Supporting Document N`)
and April 2026 agendas (`Council Member Memo`, etc.). The exclusion approach only needs
updating when the council introduces a *new embedded-doc label*, which is far less common.

### Target sections

Documents are only extracted from these agenda sections:

- Decision Items
- Motions on Notice
- Information Items / Information Only Reports
- Response to Gallery Questions, Questions on Notice, Motions Without Notice (rare)

Procedural sections (Welcome, Attendees, Declaration of Interests, Presentations,
Deputations) are ignored.

## Output structure

```
council_docs/
  14 April 2026 Full Council/
    Item 10.1 Council Member Memo 175th Anniversary.pdf
    14 April 2026 Full Council - Supporting Documents.pdf   ← --combine only
    _run_summary.txt
    aidocs_content.html
    analysis_structure.json
    target_downloads.json
```

## Running over past agendas

```bash
python scheduled_run.py --url "https://mitcham.civicclerk.com.au/web/Player.aspx?id=XXXX&key=-1&mod=-1&mk=-1&nov=0" --force --combine
```

Use `--force` to re-download even if the folder already exists.
