"""Supabase DB wrapper — request logging and rate limiting."""
import os
from datetime import date

from supabase import create_client, Client

COUNCIL_DOMAIN = "mitchamcouncil.sa.gov.au"
DAILY_LIMIT = 5


def _client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def is_rate_limited(email: str) -> bool:
    """Return True if this email has hit the daily request cap."""
    if email.lower().endswith(f"@{COUNCIL_DOMAIN}"):
        return False
    today = date.today().isoformat()
    result = (
        _client()
        .table("requests")
        .select("id")
        .eq("email", email.lower())
        .gte("requested_at", f"{today}T00:00:00+00:00")
        .execute()
    )
    return len(result.data) >= DAILY_LIMIT


def log_request(
    email: str,
    meeting_id: str,
    meeting_title: str,
    meeting_url: str,
    ip_address: str | None = None,
) -> int:
    """Insert a new request row and return its id."""
    result = (
        _client()
        .table("requests")
        .insert(
            {
                "email": email.lower(),
                "meeting_id": meeting_id,
                "meeting_title": meeting_title,
                "meeting_url": meeting_url,
                "ip_address": ip_address,
                "status": "pending",
            }
        )
        .execute()
    )
    return result.data[0]["id"]


def update_request_status(request_id: int, status: str) -> None:
    _client().table("requests").update({"status": status}).eq("id", request_id).execute()
