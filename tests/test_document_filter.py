import pytest
from aidocs_html_analyzer_sorted import AidocsHtmlAnalyzerSorted

@pytest.fixture
def analyzer():
    return AidocsHtmlAnalyzerSorted()

# --- Should be downloaded ---
def test_attachment_with_dash(analyzer):
    assert analyzer.is_supporting_document('Attachment A - Draft Terms of Reference') is True

def test_attachment_without_dash(analyzer):
    assert analyzer.is_supporting_document('Attachment B Libraries') is True

def test_attachment_multiword(analyzer):
    assert analyzer.is_supporting_document('Attachment D Winns Bakehouse and Museum') is True

def test_attachment_lowercase(analyzer):
    assert analyzer.is_supporting_document('attachment a - something') is True

def test_supporting_document_numbered(analyzer):
    assert analyzer.is_supporting_document('Supporting Document 1 - City of Mitcham Dog Plan') is True

def test_supporting_document_unnumbered(analyzer):
    assert analyzer.is_supporting_document('Supporting Document - Behavioural Standards') is True

def test_supplementary_keyword(analyzer):
    assert analyzer.is_supporting_document('Supplementary Information - Budget') is True

# --- Should NOT be downloaded ---
def test_bare_report(analyzer):
    assert analyzer.is_supporting_document('Report') is False

def test_information_only_report(analyzer):
    assert analyzer.is_supporting_document('Information Only Report') is False

def test_corro_report(analyzer):
    assert analyzer.is_supporting_document('Corro / Resolution Report') is False

def test_cover_page(analyzer):
    assert analyzer.is_supporting_document('Cover Page') is False
