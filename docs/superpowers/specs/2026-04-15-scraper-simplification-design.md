# Scraper Simplification — Design Spec

**Date:** 2026-04-15
**Status:** Approved

---

## Goal

Eliminate the Selenium/ChromeDriver dependency entirely, fix meeting URL discovery so it no longer requires manual `config.json` updates, and add background context to the README explaining why this tool exists.

---

## Background

GenFile.aspx (the CivicClerk document endpoint) responds directly with `Content-Type: application/pdf` to a plain HTTP GET request. Selenium was initialising Chrome but the actual PDF bytes were always being fetched by the Stage 1 requests path — Chrome was never used. This was confirmed by testing the live URL directly with `requests`.

Meeting IDs are embedded in server-rendered HTML as `onclick="LaunchPlayer(1401,-1,-1,-1,0)"` attributes — no JavaScript execution is required to discover them.

---

## Changes

### 1. `meeting_discovery.py` — rewrite

**New behaviour:**
1. GET `https://mitcham.civicclerk.com.au/web/`
2. Find all elements whose `onclick` attribute contains `LaunchPlayer(`
3. Parse the first argument (meeting ID) from the `LaunchPlayer(ID,...)` call
4. Extract the visible meeting title from the surrounding element text
5. Keep only meetings where the title contains `"full council"` (case-insensitive) — captures both "Full Council" and "Special Full Council"
6. Build URL: `https://mitcham.civicclerk.com.au/web/Player.aspx?id={id}&key=-1&mod=-1&mk=-1&nov=0`
7. Return `[{'title': str, 'url': str, 'meeting_id': int}, ...]` — same shape as today

**`config.json` fallback:** kept. If the live fetch succeeds, config.json is ignored. If the portal is unreachable or returns no Full Council meetings, fall back to config.json exactly as before. This prevents the scraper from breaking if CivicClerk changes its HTML structure.

**Deduplication:** if the same meeting ID appears more than once in the HTML, keep only the first occurrence.

---

### 2. `supporting_docs_downloader.py` — strip Selenium

All Selenium code is removed. The download path becomes:

1. Resolve relative URL → absolute URL (existing logic, unchanged)
2. `session.get(url, stream=True)`
3. `Content-Type: application/pdf` → stream to file, return success
4. Anything else → log warning, return failure

**Methods removed:**
- `_setup_selenium_driver`
- `_stage2_follow_redirect`
- `_stage2_selenium_download`
- `_stage2_requests_download`
- `_extract_redirect_url`
- `_wait_for_any_new_pdf`

**Constructor changes:**
- `use_selenium` parameter removed
- `download_folder` parameter removed (was only needed for Selenium file detection)

**CLI changes:**
- `--no-selenium` flag removed from `main()`

**Imports removed:** `selenium`, `webdriver`, `By`, `WebDriverWait`, `EC`, `Options`, `TimeoutException`, `NoSuchElementException`, `glob`

---

### 3. `requirements.txt` — remove selenium

Remove the `selenium>=4.0.0` line.

---

### 4. `README.md` — add background section

Add a **Background** section after "What it does":

> Mitcham Council resolved to stop printing supporting documents in the agenda packet to reduce escalating printing costs. Elected members receive only the printed agenda; supporting documents are published online separately. CivicClerk (the portal software) refers to the printed agenda as the "packet" — this tool downloads the separately-published supporting documents that accompany it.
>
> A typical example is the 27 January 2026 Full Council meeting, which had 8 supporting documents listed in the agenda under the note: *"These documents are not included in the agenda packet but can be found on the website."* This tool automates downloading all of them into a single named PDF.

Update the **Meeting URL discovery** section to explain that the tool now auto-discovers Full Council meetings from the portal — `config.json` is only needed as a manual fallback if the portal is unreachable or its HTML structure changes.

---

## Files Modified

| File | Change |
|------|--------|
| `meeting_discovery.py` | Rewrite — live portal scrape with config.json fallback |
| `supporting_docs_downloader.py` | Strip ~300 lines of Selenium/Stage 2 code |
| `requirements.txt` | Remove `selenium` |
| `README.md` | Add Background section; update discovery section |

## Files NOT changed

- `aidocs_html_analyzer_sorted.py` — unchanged
- `council_document_scraper.py` — unchanged (calls downloader with same interface)
- `scheduled_run.py` — unchanged
- `pdf_combiner.py` — unchanged
- All tests — `meeting_discovery` tests updated to match new behaviour; downloader tests updated to remove Selenium paths

---

## Tests

### `tests/test_meeting_discovery.py` — update existing tests

Existing tests mock `requests.get` to return HTML fixtures. Update fixtures to include `LaunchPlayer(...)` onclick handlers. Tests must cover:
- Extracts Full Council meeting IDs correctly
- Filters out non-Full Council meetings (Audit Committee, CEO Review, etc.)
- Includes "Special Full Council" meetings
- Deduplicates repeated meeting IDs
- Falls back to config.json when live fetch returns no Full Council meetings
- Falls back to config.json when live fetch raises a network error

### `tests/test_document_downloader.py` — update existing tests (if they exist)

Remove any tests that exercise Selenium paths. Add/keep tests for:
- Direct PDF download (200 + `application/pdf`) → success
- Non-PDF response → failure with logged warning
- Relative URL resolution → correct absolute URL

---

## Out of Scope

- Scraping meeting types other than Full Council
- Date-based filtering of discovered meetings (existing `is_already_scraped()` handles this)
- Any changes to the web service layer (Sub-project 2)
