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
    sorted highest meeting_id (most recent) first.
    """
    soup = BeautifulSoup(html, 'html.parser')
    seen_ids = set()
    results = []

    for anchor in soup.find_all('a', href=re.compile(r'Player\.aspx', re.I)):
        href = anchor.get('href', '')
        full_url = urljoin(base_url, href)
        title = anchor.get_text(separator=' ', strip=True)

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

    results.sort(key=lambda x: x['meeting_id'], reverse=True)
    return results


def discover_latest_council_meetings(portal_url: str = CIVICCLERK_PORTAL) -> list[dict]:
    """Fetch the CivicClerk portal page and return parsed meeting links.

    Falls back to config.json if the portal page returns no links.
    Returns list of dicts sorted newest-first.
    """
    with requests.Session() as session:
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
            logger.warning('[DISCOVERY] Portal returned HTML but no Player.aspx links found (JS-rendered?)')
        except Exception as e:
            logger.error(f'[DISCOVERY] Portal fetch failed: {e}')

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
        valid = []
        for entry in entries:
            if all(k in entry for k in ('title', 'url', 'meeting_id')):
                valid.append(entry)
            else:
                logger.warning(f'[DISCOVERY] Skipping invalid config entry (missing required fields): {entry}')
        logger.info(f'[DISCOVERY] Loaded {len(valid)} meetings from config.json')
        return valid
    except Exception as e:
        logger.error(f'[DISCOVERY] Failed to read config.json: {e}')
        return []
