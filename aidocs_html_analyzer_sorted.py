# aidocs_html_analyzer_sorted.py
from bs4 import BeautifulSoup
import json
import re
import sys
import urllib.parse


class AidocsHtmlAnalyzerSorted:
    """Parses a CivicClerk AIDocs HTML page, scopes to target agenda sections,
    associates GenFile links with their parent Item X.Y, and identifies which
    links are separately-uploaded supporting documents (vs. agenda-embedded)."""

    # Agenda sections to search for supporting documents (case-insensitive,
    # leading "N. " stripped before matching).
    _TARGET_SECTIONS = frozenset({
        'decision items',
        'motions on notice',
        'information items',
        'information only reports',
        'response to gallery questions from previous meetings',
        'response to questions on notice from previous meetings',
        'questions on notice',
        'items without notice',
        'motions without notice',
        'questions without notice',
    })

    # Agenda-embedded document labels — these are sections inside the agenda
    # PDF itself and must NOT be downloaded separately.
    _EMBEDDED_DOC_LABELS = frozenset({
        'report',
        'information only report',
        'corro / resolution report',
        'cover page',
    })

    def __init__(self):
        self.major_items = []
        self.individual_items = []
        self.supporting_docs = []
        self.structure = {}
        self.all_genfile_links = []   # populated by extract_structure

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def analyze_file(self, html_file_path):
        """Load HTML from a file and analyse it. Returns True on success."""
        try:
            with open(html_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            soup = BeautifulSoup(content, 'html.parser')
            self.extract_structure(soup)
            self.create_simplified_structure()
            return True
        except Exception as e:
            print(f"Error analyzing file: {str(e)}")
            return False

    def analyze_string(self, html_content):
        """Analyse HTML from a string (convenience method used in tests)."""
        soup = BeautifulSoup(html_content, 'html.parser')
        self.extract_structure(soup)
        self.create_simplified_structure()
        return True

    # ------------------------------------------------------------------
    # Core extraction
    # ------------------------------------------------------------------

    def extract_structure(self, soup):
        """Process all agenda cells in DOM order.

        Tracks the current target section and current individual item so
        that GenFile links in each preview cell can be tagged with their
        parent Item X.Y number. Links are only extracted when we are inside
        a target section.
        """
        all_cells = soup.find_all(
            'td',
            class_=['dx-wrap dxtl dxtl__B0',
                    'dxtlPreview_CustomThemeModerno dxtl__B0']
        )

        current_section = None       # non-None when inside a target section
        current_major_number = None  # e.g. 10
        individual_counter = 0
        current_item_number = None   # e.g. "10.1"
        current_item_text = None
        html_position = 0            # insertion-order counter for stable sort

        for doc_index, cell in enumerate(all_cells):
            cell_info = self.analyze_cell(cell, doc_index)

            if cell_info['type'] == 'major':
                self.major_items.append(cell_info)
                # Strip leading "N. " to get the bare section name
                bare = re.sub(r'^\d+\.\s*', '', cell_info['text'].lower()).strip()
                if bare in self._TARGET_SECTIONS:
                    current_section = cell_info['text']
                    current_major_number = cell_info.get('item_number')
                    individual_counter = 0
                    current_item_number = None
                    current_item_text = None
                else:
                    current_section = None
                    current_major_number = None
                    current_item_number = None
                    current_item_text = None

            elif cell_info['type'] == 'individual':
                self.individual_items.append(cell_info)
                if current_section is not None:
                    individual_counter += 1
                    if current_major_number is not None:
                        current_item_number = f"{current_major_number}.{individual_counter}"
                    else:
                        current_item_number = str(individual_counter)
                    current_item_text = cell_info['text']

            elif cell_info['type'] == 'supporting_docs':
                self.supporting_docs.append(cell_info)
                if current_section is not None and current_item_number is not None:
                    for link in cell.find_all(
                            'a', href=re.compile(r'GenFile\.aspx', re.I)):
                        link_text = link.get_text(strip=True)
                        link_href = link.get('href', '')
                        doc_match = re.search(
                            r'Supporting Document (\d+)', link_text, re.I)
                        self.all_genfile_links.append({
                            'text': link_text,
                            'href': link_href,
                            'ad_value': self.get_ad_value(link_href),
                            'is_supporting_doc': self.is_supporting_document(link_text),
                            'doc_number': int(doc_match.group(1)) if doc_match else None,
                            'parent_item_number': current_item_number,
                            'parent_item_text': current_item_text,
                            'html_position': html_position,
                        })
                        html_position += 1

    def analyze_cell(self, cell, index):
        """Classify a cell as major / individual / supporting_docs / unknown."""
        text = cell.get_text(separator=' ', strip=True)
        classes = ' '.join(cell.get('class', []))
        style = cell.get('style', '')
        colspan = cell.get('colspan')

        cell_type = 'unknown'
        if colspan == '2' and 'font-weight:bold' in style.lower():
            cell_type = 'major'
        elif ('dx-wrap dxtl dxtl__B0' in classes
              and not colspan
              and 'font-weight:bold' not in style.lower()):
            cell_type = 'individual'
        elif 'dxtlPreview_CustomThemeModerno' in classes:
            cell_type = 'supporting_docs'

        item_number = None
        if cell_type == 'major':
            match = re.search(r'^\s*(\d{1,2})', text)
            if match:
                item_number = int(match.group(1))
        else:
            item_match = re.search(r'(?:Item\s+)?(\d+\.\d+(?:\.\d+)?)', text)
            item_number = item_match.group(1) if item_match else None

        return {
            'index': index,
            'type': cell_type,
            'text': text,
            'item_number': item_number,
        }

    # ------------------------------------------------------------------
    # Filter
    # ------------------------------------------------------------------

    def is_supporting_document(self, link_text):
        """Return True for separately-uploaded supporting documents.

        Uses Approach A (exclusion-based): anything that is NOT a known
        agenda-embedded label is treated as a separately-uploaded file.
        This handles future council naming changes automatically — new
        embedded-doc labels are the only thing that ever needs updating here.

        Excluded (agenda-embedded):
          - Bare report labels: 'Report', 'Information Only Report', etc.
          - Any text starting with 'Attachment' (inline agenda sections)

        Included (download these):
          - 'Supporting Document N - Title'  (older agenda format)
          - 'Supplementary ...'
          - Descriptive names like 'Council Member Memo 175th Anniversary'
        """
        text_lower = link_text.lower().strip()
        if text_lower in self._EMBEDDED_DOC_LABELS:
            return False
        if text_lower.startswith('attachment'):
            return False
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_ad_value(self, link_href):
        """Extract 'ad' query parameter as int (0 if absent/invalid)."""
        try:
            params = urllib.parse.parse_qs(urllib.parse.urlparse(link_href).query)
            return int(params.get('ad', ['0'])[0])
        except (ValueError, IndexError):
            return 0

    def get_supporting_documents_only(self):
        """Return supporting-doc links sorted by item number then HTML position."""
        supporting = [l for l in self.all_genfile_links if l['is_supporting_doc']]
        return sorted(supporting, key=self._item_sort_key)

    def _item_sort_key(self, link):
        item_num = link.get('parent_item_number') or '999'
        try:
            parts = [int(x) for x in item_num.split('.')]
            major = parts[0] if parts else 999
            sub = parts[1] if len(parts) > 1 else 0
        except (ValueError, IndexError):
            major, sub = 999, 0
        return (major, sub, link.get('html_position', 0))

    # ------------------------------------------------------------------
    # Structure building (kept for JSON output + downstream compatibility)
    # ------------------------------------------------------------------

    def propagate_major_numbers_to_individuals(self, items):
        """Propagate major item numbers to following individual items."""
        current_major_number = None
        individual_counter = 1
        prefix_pattern = re.compile(r'^(\d+)\.(\d+)\s+')

        for item in items:
            if item['type'] == 'major' and item.get('item_number') is not None:
                current_major_number = item['item_number']
                individual_counter = 1
            elif item['type'] == 'individual' and current_major_number is not None:
                item['item_number'] = current_major_number
                text = item['text']
                match = prefix_pattern.match(text)
                if match:
                    major_num, sub_num = match.groups()
                    if int(major_num) == current_major_number:
                        rest_text = re.sub(r'^\d+\s+', '', text[match.end():]).strip()
                        item['text'] = f"{major_num}.{sub_num} {rest_text}"
                        individual_counter += 1
                    else:
                        individual_counter += 1
                else:
                    clean_text = re.sub(r'^\d+\s+', '', text).strip()
                    item['text'] = f"{current_major_number}.{individual_counter} {clean_text}"
                    individual_counter += 1
        return items

    def create_simplified_structure(self):
        all_items = sorted(
            self.major_items + self.individual_items,
            key=lambda x: x.get('index', 0)
        )
        all_items = self.propagate_major_numbers_to_individuals(all_items)
        self.structure = {
            'items': all_items,
            'all_supporting_docs': self.supporting_docs,
            'all_genfile_links': self.all_genfile_links,
            'supporting_documents_only': self.get_supporting_documents_only(),
            'summary': {
                'total_major_items': len(self.major_items),
                'total_individual_items': len(self.individual_items),
                'total_all_items': len(all_items),
                'total_supporting_doc_containers': len(self.supporting_docs),
                'total_genfile_links': len(self.all_genfile_links),
                'total_supporting_documents': len(self.get_supporting_documents_only()),
            },
        }

    def save_simplified_json(self, output_file):
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.structure, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving JSON: {str(e)}")
            return False

    def extract_supporting_documents_for_scraper(self):
        """Return supporting docs in scraper-ready format with parent_item_number."""
        return [{
            'title': doc['text'],
            'url': doc['href'],
            'doc_number': doc['doc_number'],
            'ad_value': doc['ad_value'],
            'parent_item_number': doc['parent_item_number'],
            'parent_item_text': doc['parent_item_text'],
        } for doc in self.get_supporting_documents_only()]


def main():
    if len(sys.argv) != 2:
        print("Usage: python aidocs_html_analyzer_sorted.py <path_to_aidocs_content.html>")
        sys.exit(1)
    analyzer = AidocsHtmlAnalyzerSorted()
    if not analyzer.analyze_file(sys.argv[1]):
        sys.exit(1)
    output_json = sys.argv[1].replace('.html', '_simplified_sorted.json')
    analyzer.save_simplified_json(output_json)
    docs = analyzer.extract_supporting_documents_for_scraper()
    print(f"Found {len(docs)} supporting documents")
    for d in docs:
        print(f"  Item {d['parent_item_number']}: {d['title']}")


if __name__ == "__main__":
    main()
