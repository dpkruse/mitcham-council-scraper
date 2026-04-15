"""Supabase Storage wrapper — PDF cache for processed meetings."""
import os
from pathlib import Path

from supabase import create_client, Client

BUCKET = "meeting-docs"


def _client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def list_files(meeting_id: str) -> list[str]:
    """Return cached filenames for this meeting. Empty list = cache miss."""
    try:
        items = _client().storage.from_(BUCKET).list(meeting_id)
        return [f["name"] for f in items if f.get("name")]
    except Exception:
        return []


def download_all(meeting_id: str, dest: Path) -> None:
    """Download every cached PDF for meeting_id into dest folder."""
    dest.mkdir(parents=True, exist_ok=True)
    client = _client()
    for name in list_files(meeting_id):
        data = client.storage.from_(BUCKET).download(f"{meeting_id}/{name}")
        (dest / name).write_bytes(data)


def upload_file(meeting_id: str, filepath: Path) -> None:
    """Upload one PDF into the cache bucket."""
    with open(filepath, "rb") as f:
        _client().storage.from_(BUCKET).upload(
            f"{meeting_id}/{filepath.name}",
            f,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )


def upload_all(meeting_id: str, folder: Path) -> None:
    """Upload every PDF in folder to the cache bucket."""
    for pdf in folder.glob("*.pdf"):
        upload_file(meeting_id, pdf)


def get_signed_url(meeting_id: str, filename: str, expires_in: int = 86400) -> str:
    """Return a signed URL for a cached file (default 24 h TTL)."""
    result = _client().storage.from_(BUCKET).create_signed_url(
        f"{meeting_id}/{filename}", expires_in
    )
    # supabase-py v2 returns a dict; v1 returned an object
    if isinstance(result, dict):
        return result.get("signedURL") or result.get("signed_url", "")
    return getattr(result, "signed_url", str(result))
