"""FastAPI web application for the Mitcham Council document scraper."""
import os
import re
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import db
import email_sender
import meeting_discovery
import storage
from council_document_scraper import CouncilDocumentScraper
from pdf_combiner import combine_pdfs

BASE_DIR = Path(__file__).parent
JOBS_TMP = Path(tempfile.gettempdir()) / "council_jobs"

app = FastAPI(title="Mitcham Council Documents")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ── In-memory job state ────────────────────────────────────────────────────────
_jobs: dict = {}
_jobs_lock = threading.Lock()


def _set_job(job_id: str, **kwargs) -> None:
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).update(kwargs)


def _get_job(job_id: str) -> dict:
    with _jobs_lock:
        return dict(_jobs.get(job_id, {}))


# ── Helpers ────────────────────────────────────────────────────────────────────
def _meeting_id_from_url(url: str) -> str:
    """Extract the numeric meeting ID from a CivicClerk Player.aspx URL."""
    match = re.search(r"[?&]id=(\d+)", url)
    return match.group(1) if match else url


# ── Background job ─────────────────────────────────────────────────────────────
def _run_job(job_id: str, url: str, email: str, meeting_title: str, request_id: int) -> None:
    tmp_folder = JOBS_TMP / job_id
    tmp_folder.mkdir(parents=True, exist_ok=True)
    meeting_id = _meeting_id_from_url(url)

    try:
        # Stage 1 — cache check
        _set_job(job_id, stage="Checking cache...")
        cached = storage.list_files(meeting_id)

        if cached:
            _set_job(job_id, stage="Cache hit — retrieving documents...")
            meeting_folder = tmp_folder / "docs"
            storage.download_all(meeting_id, meeting_folder)
            # Use title passed from the UI (cached runs skip scraping)
            resolved_title = meeting_title
        else:
            # Stage 2 — scrape
            _set_job(job_id, stage="Fetching agenda structure...")
            scraper = CouncilDocumentScraper(output_folder=str(tmp_folder))
            result = scraper.scrape_agenda(url)

            if result["status"] != "success":
                raise RuntimeError(result.get("error_message", "Scraping failed"))

            meeting_folder = Path(result["meeting_folder"])
            resolved_title = result["meeting_title"]

            # Stage 3 — combine
            _set_job(job_id, stage="Building combined PDF...")
            pdf_entries = [
                {
                    "filepath": str(meeting_folder / t["recommended_filename"]),
                    "item_number": t.get("parent_item_number", ""),
                    "item_descriptor": t.get("parent_item_text", ""),
                    "title": t.get("title", ""),
                }
                for t in result.get("target_downloads", [])
            ]
            combined_name = f"{resolved_title} - Supporting Documents.pdf"
            combine_pdfs(
                pdf_entries,
                str(meeting_folder / combined_name),
                resolved_title,
                meeting_url=url,
            )

            # Stage 4 — upload to cache
            _set_job(job_id, stage="Caching documents...")
            storage.upload_all(meeting_id, meeting_folder)

        # Locate generated PDFs
        all_pdfs = sorted(meeting_folder.glob("*.pdf"))
        combined_pdf = next((p for p in all_pdfs if "Supporting Documents" in p.name), None)
        individual_pdfs = [p for p in all_pdfs if p != combined_pdf]

        # Stage 5 — send email
        _set_job(job_id, stage="Sending email...")
        files_for_email = [
            {
                "name": p.stem,
                "signed_url": storage.get_signed_url(meeting_id, p.name),
                "path": p,
            }
            for p in individual_pdfs
        ]
        combined_signed_url = (
            storage.get_signed_url(meeting_id, combined_pdf.name) if combined_pdf else None
        )
        email_sender.send_documents_email(
            to_email=email,
            meeting_title=resolved_title,
            files=files_for_email,
            combined_pdf_path=combined_pdf,
            combined_signed_url=combined_signed_url,
        )

        db.update_request_status(request_id, "done")
        _set_job(
            job_id,
            status="done",
            stage="Complete",
            meeting_title=resolved_title,
            files=[
                {"name": p.name, "url": f"/api/download/{job_id}/{p.name}"}
                for p in individual_pdfs
            ],
            combined_pdf_url=(
                f"/api/download/{job_id}/{combined_pdf.name}" if combined_pdf else None
            ),
        )

    except Exception as exc:
        db.update_request_status(request_id, "error")
        _set_job(job_id, status="error", stage="Failed", error=str(exc))


# ── Request model ──────────────────────────────────────────────────────────────
class JobRequest(BaseModel):
    url: str
    email: str
    meeting_title: str = ""


# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/meetings")
async def get_meetings():
    """Discover and return upcoming Full Council meetings from the CivicClerk portal."""
    return meeting_discovery.discover_latest_council_meetings()


@app.post("/api/jobs")
async def create_job(body: JobRequest, request: Request):
    """Validate the request, apply rate limiting, and kick off a background job."""
    email = body.email.strip().lower()
    url = body.url.strip()
    meeting_title = body.meeting_title.strip()

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="A valid email address is required.")

    if db.is_rate_limited(email):
        raise HTTPException(
            status_code=429,
            detail=(
                "You've reached the daily limit of 5 requests. "
                "Council staff with a @mitchamcouncil.sa.gov.au address have unlimited access."
            ),
        )

    meeting_id = _meeting_id_from_url(url)
    request_id = db.log_request(
        email=email,
        meeting_id=meeting_id,
        meeting_title=meeting_title or f"Meeting {meeting_id}",
        meeting_url=url,
        ip_address=request.client.host if request.client else None,
    )

    job_id = str(uuid.uuid4())[:8]
    _set_job(job_id, status="running", stage="Starting...", files=[], error=None)

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, url, email, meeting_title, request_id),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Return current job state for frontend polling."""
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/download/{job_id}/{filename}")
async def download_file(job_id: str, filename: str):
    """Serve a generated PDF file, searching recursively in the job's temp folder."""
    job = _get_job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(status_code=404, detail="File not available.")

    matches = list((JOBS_TMP / job_id).rglob(filename))
    if not matches:
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(path=str(matches[0]), filename=filename, media_type="application/pdf")
