import pytest
from unittest.mock import patch, MagicMock
from meeting_discovery import parse_meeting_links, discover_latest_council_meetings

# Real portal structure: meeting rows have onclick="LaunchPlayer(ID,...)"
# NOT <a href="Player.aspx?id=..."> links
SAMPLE_HTML = """
<html><body>
<table>
  <tr onclick="LaunchPlayer(1402,-1,-1,-1,0)"><td>Full Council - 13 May 2026</td></tr>
  <tr onclick="LaunchPlayer(1401,-1,-1,-1,0)"><td>Full Council - 14 April 2026</td></tr>
  <tr onclick="LaunchPlayer(1410,-1,-1,-1,0)"><td>Special Full Council - 1 April 2026</td></tr>
  <tr onclick="LaunchPlayer(1418,-1,-1,-1,0)"><td>Audit and Risk Committee - 28 March 2026</td></tr>
  <tr onclick="LaunchPlayer(1375,-1,-1,-1,0)"><td>Council Assessment Panel - 25 March 2026</td></tr>
  <tr onclick="LaunchPlayer(1451,-1,-1,-1,0)"><td>CEO Performance Review - 20 March 2026</td></tr>
</table>
</body></html>
"""

BASE = 'https://mitcham.civicclerk.com.au/web/'


def test_finds_full_council_meetings():
    links = parse_meeting_links(SAMPLE_HTML, base_url=BASE)
    titles = [l['title'] for l in links]
    assert any('Full Council - 13 May' in t for t in titles)
    assert any('Full Council - 14 April' in t for t in titles)


def test_includes_special_full_council():
    links = parse_meeting_links(SAMPLE_HTML, base_url=BASE)
    titles = [l['title'] for l in links]
    assert any('Special Full Council' in t for t in titles)


def test_excludes_non_full_council():
    links = parse_meeting_links(SAMPLE_HTML, base_url=BASE)
    titles = [l['title'] for l in links]
    assert not any('Audit' in t for t in titles)
    assert not any('Assessment Panel' in t for t in titles)
    assert not any('CEO' in t for t in titles)


def test_builds_correct_url():
    links = parse_meeting_links(SAMPLE_HTML, base_url=BASE)
    urls = [l['url'] for l in links]
    assert 'https://mitcham.civicclerk.com.au/web/Player.aspx?id=1402&key=-1&mod=-1&mk=-1&nov=0' in urls


def test_returns_correct_meeting_id():
    links = parse_meeting_links(SAMPLE_HTML, base_url=BASE)
    ids = [l['meeting_id'] for l in links]
    assert 1401 in ids
    assert 1402 in ids


def test_sorted_newest_first():
    links = parse_meeting_links(SAMPLE_HTML, base_url=BASE)
    ids = [l['meeting_id'] for l in links]
    assert ids == sorted(ids, reverse=True)


def test_deduplicates_ids():
    html = """
    <html><body>
      <tr onclick="LaunchPlayer(100,-1,-1,-1,0)"><td>Full Council - May</td></tr>
      <tr onclick="LaunchPlayer(100,-1,-1,-1,0)"><td>Full Council - May duplicate</td></tr>
    </body></html>
    """
    links = parse_meeting_links(html, base_url=BASE)
    assert len(links) == 1


def test_empty_html_returns_empty_list():
    links = parse_meeting_links('<html><body></body></html>', base_url=BASE)
    assert links == []


def test_no_full_council_returns_empty_list():
    html = """
    <html><body>
      <tr onclick="LaunchPlayer(200,-1,-1,-1,0)"><td>Audit Committee - March</td></tr>
    </body></html>
    """
    links = parse_meeting_links(html, base_url=BASE)
    assert links == []


def test_discover_returns_live_results():
    with patch('meeting_discovery.requests.Session') as mock_cls:
        mock_session = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        results = discover_latest_council_meetings()
        assert len(results) == 3  # 2 Full Council + 1 Special Full Council
        mock_session.get.assert_called_once()


def test_discover_falls_back_to_config_when_no_full_council(tmp_path, monkeypatch):
    import json, meeting_discovery
    cfg = tmp_path / 'config.json'
    cfg.write_text(json.dumps({'meetings': [
        {'title': 'Manual Entry', 'url': 'https://example.com', 'meeting_id': 999}
    ]}))
    monkeypatch.setattr(meeting_discovery, 'CONFIG_FILE', str(cfg))

    html_no_full_council = """
    <html><body>
      <tr onclick="LaunchPlayer(300,-1,-1,-1,0)"><td>Audit Committee</td></tr>
    </body></html>
    """
    with patch('meeting_discovery.requests.Session') as mock_cls:
        mock_session = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.text = html_no_full_council
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        results = discover_latest_council_meetings()
        assert len(results) == 1
        assert results[0]['meeting_id'] == 999


def test_discover_falls_back_to_config_on_network_error(tmp_path, monkeypatch):
    import json, meeting_discovery
    cfg = tmp_path / 'config.json'
    cfg.write_text(json.dumps({'meetings': [
        {'title': 'Manual Entry', 'url': 'https://example.com', 'meeting_id': 888}
    ]}))
    monkeypatch.setattr(meeting_discovery, 'CONFIG_FILE', str(cfg))

    with patch('meeting_discovery.requests.Session') as mock_cls:
        mock_session = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.side_effect = ConnectionError('portal down')

        results = discover_latest_council_meetings()
        assert len(results) == 1
        assert results[0]['meeting_id'] == 888
