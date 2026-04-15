import os
import pytest
from unittest.mock import MagicMock, patch
from supporting_docs_downloader import SupportingDocsDownloader


BASE = 'https://mitcham.civicclerk.com.au/web/'


@pytest.fixture
def downloader():
    return SupportingDocsDownloader(base_url=BASE)


def test_downloads_pdf_successfully(downloader, tmp_path):
    target = {
        'url': '../GenFile.aspx?ad=4906&token=abc',
        'recommended_filename': 'Item 10.1 Test Doc.pdf',
    }
    mock_response = MagicMock()
    mock_response.headers = {'content-type': 'application/pdf'}
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_content = MagicMock(return_value=[b'%PDF-1.7 fake content'])

    with patch.object(downloader.session, 'get', return_value=mock_response):
        result = downloader.download_single_document(target, str(tmp_path))

    assert result['status'] == 'success'
    assert result['method'] == 'requests_direct'
    assert os.path.isfile(os.path.join(str(tmp_path), 'Item 10.1 Test Doc.pdf'))


def test_handles_non_pdf_response(downloader, tmp_path):
    target = {
        'url': '../GenFile.aspx?ad=999&token=abc',
        'recommended_filename': 'Item 10.1 Test Doc.pdf',
    }
    mock_response = MagicMock()
    mock_response.headers = {'content-type': 'text/html; charset=utf-8'}
    mock_response.raise_for_status = MagicMock()

    with patch.object(downloader.session, 'get', return_value=mock_response):
        result = downloader.download_single_document(target, str(tmp_path))

    assert result['status'] == 'unexpected_content_type'
    assert 'text/html' in result['error']


def test_resolves_relative_url(downloader, tmp_path):
    target = {
        'url': '../GenFile.aspx?ad=123&token=xyz',
        'recommended_filename': 'doc.pdf',
    }
    mock_response = MagicMock()
    mock_response.headers = {'content-type': 'application/pdf'}
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_content = MagicMock(return_value=[b'%PDF'])

    with patch.object(downloader.session, 'get', return_value=mock_response) as mock_get:
        downloader.download_single_document(target, str(tmp_path))
        called_url = mock_get.call_args[0][0]

    assert called_url == 'https://mitcham.civicclerk.com.au/web/GenFile.aspx?ad=123&token=xyz'


def test_handles_network_error(downloader, tmp_path):
    target = {
        'url': '../GenFile.aspx?ad=404&token=abc',
        'recommended_filename': 'doc.pdf',
    }
    with patch.object(downloader.session, 'get', side_effect=ConnectionError('network down')):
        result = downloader.download_single_document(target, str(tmp_path))

    assert result['status'] == 'error'
    assert 'network down' in result['error']
