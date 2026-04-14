import os
import json
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
