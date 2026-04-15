import pytest
from aidocs_html_analyzer_sorted import AidocsHtmlAnalyzerSorted

# Minimal HTML that mimics real CivicClerk structure.
# Major cells: colspan="2" + style="font-weight:bold"
# Individual cells: dx-wrap dxtl dxtl__B0 (no colspan, no bold)
# Preview cells: dxtlPreview_CustomThemeModerno dxtl__B0 (contains GenFile links)
SAMPLE_HTML = """
<html><body><table>
  <tr><td class="dx-wrap dxtl dxtl__B0" colspan="2" style="font-weight:bold">Administrative Matters</td></tr>
  <tr><td class="dxtlPreview_CustomThemeModerno dxtl__B0"></td></tr>

  <tr><td class="dx-wrap dxtl dxtl__B0" colspan="2" style="font-weight:bold">10. Decision Items</td></tr>
  <tr><td class="dxtlPreview_CustomThemeModerno dxtl__B0"></td></tr>

  <tr><td class="dx-wrap dxtl dxtl__B0">1 City of Mitcham Anniversary</td></tr>
  <tr><td class="dxtlPreview_CustomThemeModerno dxtl__B0">
    <a href="../GenFile.aspx?ar=100&amp;token=abc">Report</a>
    <a href="../GenFile.aspx?ar=101&amp;token=def">Attachment A - Draft Terms</a>
    <a href="../GenFile.aspx?ar=102&amp;token=ghi">Council Member Memo</a>
  </td></tr>

  <tr><td class="dx-wrap dxtl dxtl__B0">2 Another Decision Item</td></tr>
  <tr><td class="dxtlPreview_CustomThemeModerno dxtl__B0">
    <a href="../GenFile.aspx?ar=200&amp;token=jkl">Report</a>
    <a href="../GenFile.aspx?ar=201&amp;token=mno">Supporting Document 1 - Some Study</a>
  </td></tr>

  <tr><td class="dx-wrap dxtl dxtl__B0" colspan="2" style="font-weight:bold">Administrative Matters</td></tr>
  <tr><td class="dxtlPreview_CustomThemeModerno dxtl__B0"></td></tr>
  <tr><td class="dx-wrap dxtl dxtl__B0">1 Some Admin Item</td></tr>
  <tr><td class="dxtlPreview_CustomThemeModerno dxtl__B0">
    <a href="../GenFile.aspx?ar=300&amp;token=pqr">Supporting Document 1 - Admin Doc</a>
  </td></tr>
</table></body></html>
"""

@pytest.fixture
def docs():
    a = AidocsHtmlAnalyzerSorted()
    a.analyze_string(SAMPLE_HTML)
    return a.extract_supporting_documents_for_scraper()

def test_finds_descriptive_supporting_doc(docs):
    titles = [d['title'] for d in docs]
    assert 'Council Member Memo' in titles

def test_finds_explicit_supporting_document(docs):
    titles = [d['title'] for d in docs]
    assert any('Some Study' in t for t in titles)

def test_excludes_reports(docs):
    titles = [d['title'] for d in docs]
    assert 'Report' not in titles

def test_excludes_attachments(docs):
    titles = [d['title'] for d in docs]
    assert not any(t.lower().startswith('attachment') for t in titles)

def test_item_101_assigned_to_first_item(docs):
    memo = next(d for d in docs if d['title'] == 'Council Member Memo')
    assert memo['parent_item_number'] == '10.1'

def test_item_102_assigned_to_second_item(docs):
    study = next(d for d in docs if 'Some Study' in d['title'])
    assert study['parent_item_number'] == '10.2'

def test_non_target_section_excluded(docs):
    titles = [d['title'] for d in docs]
    assert not any('Admin Doc' in t for t in titles)

def test_results_ordered_by_item_number(docs):
    numbers = [d['parent_item_number'] for d in docs]
    def key(n):
        return [int(p) for p in n.split('.')]
    assert numbers == sorted(numbers, key=key)
