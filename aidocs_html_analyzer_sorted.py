# aidocs_html_analyzer_sorted.py - WITH CLEANED INDIVIDUAL ITEM TEXT NUMBERING
from bs4 import BeautifulSoup
import json
import re
import sys
import urllib.parse

class AidocsHtmlAnalyzerSorted:
    _EXCLUDED_LABELS = {
        'report',
        'information only report',
        'corro / resolution report',
        'cover page',
    }

    def __init__(self):
        self.major_items = []
        self.individual_items = []
        self.supporting_docs = []
        self.structure = {}
        self.all_genfile_links = []
    
    def analyze_file(self, html_file_path):
        """Load and analyze the AIDocs HTML file"""
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
    
    def get_ad_value(self, link_href):
        """Extract 'ad' parameter value from GenFile.aspx URL for sorting"""
        try:
            query = urllib.parse.urlparse(link_href).query
            params = urllib.parse.parse_qs(query)
            ad_values = params.get('ad', ['0'])
            return int(ad_values[0])
        except (ValueError, IndexError):
            return 0
    
    def extract_structure(self, soup):
        """Extract all relevant elements from the HTML"""
        all_cells = soup.find_all('td', class_=['dx-wrap dxtl dxtl__B0', 'dxtlPreview_CustomThemeModerno dxtl__B0'])
        
        for doc_index, cell in enumerate(all_cells):
            cell_info = self.analyze_cell(cell, doc_index)
            
            if cell_info['type'] == 'major':
                self.major_items.append(cell_info)
            elif cell_info['type'] == 'individual':
                self.individual_items.append(cell_info)
            elif cell_info['type'] == 'supporting_docs':
                self.supporting_docs.append(cell_info)
        
        # Extract all GenFile links
        self.extract_all_genfile_links(soup)
    
    def analyze_cell(self, cell, index):
        """Analyze individual cell to determine its type and content"""
        text = cell.get_text(separator=' ', strip=True)
        classes = ' '.join(cell.get('class', []))
        style = cell.get('style', '')
        colspan = cell.get('colspan')
        
        # Determine cell type
        cell_type = 'unknown'
        if colspan == '2' and 'font-weight:bold' in style.lower():
            cell_type = 'major'
        elif 'dx-wrap dxtl dxtl__B0' in classes and not colspan and 'font-weight:bold' not in style.lower():
            cell_type = 'individual'
        elif 'dxtlPreview_CustomThemeModerno' in classes:
            cell_type = 'supporting_docs'
        
        # Extract item number from text (for both major and individual items)
        item_number = None
        if cell_type == 'major':
            # For major items, look for leading digits (1-2 digits)
            match = re.search(r'^\s*(\d{1,2})', text)
            if match:
                item_number = int(match.group(1))
        else:
            # For individual items, use existing logic
            item_match = re.search(r'(?:Item\s+)?(\d+\.\d+(?:\.\d+)?)', text)
            item_number = item_match.group(1) if item_match else None
        
        return {
            'index': index,
            'type': cell_type,
            'text': text,
            'item_number': item_number
        }
    
    def extract_all_genfile_links(self, soup):
        """Extract and sort all GenFile.aspx links"""
        all_links = soup.find_all('a', href=re.compile(r'GenFile\.aspx'))
        
        for link in all_links:
            link_text = link.get_text(strip=True)
            link_href = link.get('href', '')
            is_supporting_doc = self.is_supporting_document(link_text)
            doc_number_match = re.search(r'Supporting Document (\d+)', link_text, re.IGNORECASE)
            doc_number = int(doc_number_match.group(1)) if doc_number_match else None
            
            link_info = {
                'text': link_text,
                'href': link_href,
                'ad_value': self.get_ad_value(link_href),
                'is_supporting_doc': is_supporting_doc,
                'doc_number': doc_number
            }
            self.all_genfile_links.append(link_info)
        
        # Sort by ad_value
        self.all_genfile_links.sort(key=lambda x: x['ad_value'])
    
    def is_supporting_document(self, link_text):
        """Return True for supplementary/attachment docs; False for bare report labels.

        Matches:
          - Any text starting with 'attachment'
          - Any text containing 'supporting document'
          - Any text containing 'supplementary'
        Excludes:
          - 'Report', 'Information Only Report', 'Corro / Resolution Report', 'Cover Page'
        """
        text_lower = link_text.lower().strip()
        if text_lower in self._EXCLUDED_LABELS:
            return False
        return (
            text_lower.startswith('attachment') or
            'supporting document' in text_lower or
            'supplementary' in text_lower
        )
    
    def propagate_major_numbers_to_individuals(self, items):
        """Propagate major item numbers to following individual items and clean up text"""
        current_major_number = None
        individual_counter = 1
        prefix_pattern = re.compile(r'^(\d+)\.(\d+)\s+')
    
        for item in items:
            if item['type'] == 'major' and item.get('item_number') is not None:
                # Found a new major item with a number
                current_major_number = item['item_number']
                individual_counter = 1
            elif item['type'] == 'individual' and current_major_number is not None:
                # Update individual item with major's number
                item['item_number'] = current_major_number
            
                text = item['text']
            
                # Check if text already starts with major.sub pattern
                match = prefix_pattern.match(text)
                if match:
                    major_num, sub_num = match.groups()
                    if int(major_num) == current_major_number:
                        # Remove redundant numbering after the "X.Y " prefix
                        rest_text = text[match.end():]
                        # Remove any leading digits and spaces from the rest
                        rest_text = re.sub(r'^\d+\s+', '', rest_text)
                        # Clean up any extra whitespace
                        rest_text = rest_text.strip()
                        item['text'] = f"{major_num}.{sub_num} {rest_text}"
                        individual_counter += 1
                    else:
                        # Different major number, leave as is
                        individual_counter += 1
                else:
                    # No existing pattern, add it
                    # Remove any leading digit and space from original text first
                    clean_text = re.sub(r'^\d+\s+', '', text).strip()
                    item['text'] = f"{current_major_number}.{individual_counter} {clean_text}"
                    individual_counter += 1
        return items
    
    def create_simplified_structure(self):
        """Create a simplified hierarchical structure"""
        # MERGE major_items and individual_items into one list, sorted by index
        all_items = []
        all_items.extend(self.major_items)
        all_items.extend(self.individual_items)
        
        # Sort merged list by index
        all_items_sorted = sorted(all_items, key=lambda x: x.get('index', 0))
        
        # Propagate major numbers to individual items and clean up text
        all_items_sorted = self.propagate_major_numbers_to_individuals(all_items_sorted)
        
        # Create structure with merged items (renamed from major_items to items)
        self.structure = {
            'items': all_items_sorted,  # RENAMED: Contains both major and individual items
            'all_supporting_docs': self.supporting_docs,
            'all_genfile_links': self.all_genfile_links,
            'supporting_documents_only': self.get_supporting_documents_only(),
            'summary': {
                'total_major_items': len(self.major_items),
                'total_individual_items': len(self.individual_items),
                'total_all_items': len(all_items_sorted),
                'total_supporting_doc_containers': len(self.supporting_docs),
                'total_genfile_links': len(self.all_genfile_links),
                'total_supporting_documents': len(self.get_supporting_documents_only())
            }
        }
    
    def get_supporting_documents_only(self):
        """Return only the GenFile links that are supporting documents"""
        supporting_only = [link for link in self.all_genfile_links if link['is_supporting_doc']]
        
        def sort_key(link):
            if link['doc_number'] is not None:
                return (0, link['doc_number'])
            else:
                return (1, link['ad_value'])
        
        return sorted(supporting_only, key=sort_key)
    
    def save_simplified_json(self, output_file):
        """Save the simplified structure as JSON"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.structure, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving JSON: {str(e)}")
            return False
    
    def extract_supporting_documents_for_scraper(self):
        """Extract supporting documents in the format expected by the scraper"""
        supporting_docs = self.get_supporting_documents_only()
        
        scraper_format = []
        for doc in supporting_docs:
            scraper_format.append({
                'title': doc['text'],
                'url': doc['href'],
                'doc_number': doc['doc_number'],
                'ad_value': doc['ad_value']
            })
        
        return scraper_format

def main():
    if len(sys.argv) != 2:
        print("Usage: python aidocs_html_analyzer_sorted.py <path_to_aidocs_content.html>")
        sys.exit(1)
    
    html_file = sys.argv[1]
    analyzer = AidocsHtmlAnalyzerSorted()
    
    if not analyzer.analyze_file(html_file):
        sys.exit(1)
    
    # Save simplified JSON structure
    output_json = html_file.replace('.html', '_simplified_sorted.json')
    analyzer.save_simplified_json(output_json)
    
    # Extract supporting documents
    supporting_docs = analyzer.extract_supporting_documents_for_scraper()
    print(f"Found {len(supporting_docs)} supporting documents")
    
    print("Analysis complete!")

if __name__ == "__main__":
    main()
