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
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        results = discover_latest_council_meetings()
        assert len(results) == 3
        mock_session.get.assert_called_once()
        mock_session.__enter__.assert_called_once()
        mock_session.__exit__.assert_called_once()


def test_parse_meeting_links_empty_html():
    links = parse_meeting_links('<html><body></body></html>', base_url='https://mitcham.civicclerk.com.au/web/')
    assert links == []


def test_parse_meeting_links_deduplicates_ids():
    html = """
    <html><body>
      <a href="Player.aspx?id=100&key=-1">Meeting A</a>
      <a href="Player.aspx?id=100&key=-1">Meeting A duplicate</a>
    </body></html>
    """
    links = parse_meeting_links(html, base_url='https://mitcham.civicclerk.com.au/web/')
    assert len(links) == 1


def test_parse_meeting_links_skips_missing_id():
    html = """
    <html><body>
      <a href="Player.aspx?key=-1">No ID here</a>
      <a href="Player.aspx?id=200&key=-1">Valid meeting</a>
    </body></html>
    """
    links = parse_meeting_links(html, base_url='https://mitcham.civicclerk.com.au/web/')
    assert len(links) == 1
    assert links[0]['meeting_id'] == 200
