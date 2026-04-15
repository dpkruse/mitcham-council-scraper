"""meeting_discovery.py
Discovers upcoming Full Council meeting agenda URLs from the CivicClerk portal.

Parses onclick="LaunchPlayer(ID,...)" attributes from the server-rendered portal
homepage. Falls back to config.json if the portal is unreachable or returns no
Full Council meetings.
"""
import re
import json
import logging
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

CIVICCLERK_PORTAL = 'https://mitcham.civicclerk.com.au/web/'
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')

logger = logging.getLogger(__name__)


def parse_meeting_links(html: str, base_url: str = CIVICCLERK_PORTAL) -> list[dict]:
    """Parse Full Council meeting links from a CivicClerk portal HTML page.

    Handles two portal HTML patterns:
      - onclick="LaunchPlayer(ID,...)" on any element (e.g. <tr>)
      - href="javascript:LaunchPlayer(ID,...)" on <a> elements

    Filters to those whose visible text contains 'full council' (case-insensitive).

    Returns a list of dicts: [{'title': str, 'url': str, 'meeting_id': int}, ...]
    sorted highest meeting_id (most recent) first.
    """
    soup = BeautifulSoup(html, 'html.parser')
    seen_ids = set()
    results = []

    launch_pattern = re.compile(r'LaunchPlayer\((\d+)', re.I)

    def _extract(element, attr_value):
        id_match = launch_pattern.search(attr_value)
        if not id_match:
            return
        try:
            meeting_id = int(id_match.group(1))
        except ValueError:
            return
        if meeting_id in seen_ids:
            return
        title = element.get_text(separator=' ', strip=True)
        if 'full council' not in title.lower():
            return
        seen_ids.add(meeting_id)
        url = urljoin(base_url, f'Player.aspx?id={meeting_id}&key=-1&mod=-1&mk=-1&nov=0')
        results.append({'title': title, 'url': url, 'meeting_id': meeting_id})

    # Pattern 1: onclick="LaunchPlayer(...)" or onclick="javascript:LaunchPlayer(...)"
    for element in soup.find_all(onclick=launch_pattern):
        _extract(element, element.get('onclick', ''))

    # Pattern 2: href="javascript:LaunchPlayer(...)"
    for element in soup.find_all(href=launch_pattern):
        _extract(element, element.get('href', ''))

    results.sort(key=lambda x: x['meeting_id'], reverse=True)
    return results


def discover_latest_council_meetings(portal_url: str = CIVICCLERK_PORTAL) -> list[dict]:
    """Fetch the CivicClerk portal page and return Full Council meeting links.

    Falls back to config.json if the portal is unreachable or returns no
    Full Council meetings.
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
                logger.info(f'[DISCOVERY] Found {len(links)} Full Council meetings on portal')
                return links
            logger.warning('[DISCOVERY] No Full Council meetings found on portal — falling back to config.json')
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
                logger.warning(f'[DISCOVERY] Skipping invalid config entry: {entry}')
        logger.info(f'[DISCOVERY] Loaded {len(valid)} meetings from config.json')
        return valid
    except Exception as e:
        logger.error(f'[DISCOVERY] Failed to read config.json: {e}')
        return []
