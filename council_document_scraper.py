# council_document_scraper.py
import requests
from bs4 import BeautifulSoup
import re
import os
import json
import sys
from urllib.parse import urljoin
import time
from datetime import datetime
import argparse
import logging

# Import the analyzer and downloader (assuming they exist as separate files)
from aidocs_html_analyzer_sorted import AidocsHtmlAnalyzerSorted
from supporting_docs_downloader import SupportingDocsDownloader

class CouncilDocumentScraper:
    def __init__(self, output_folder="council_docs", log_level="INFO"):
        self.output_folder = output_folder
        self.setup_logging(log_level)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.logger.info(f"[INIT] Initialized scraper with output folder '{self.output_folder}'")
        
    def setup_logging(self, level):
        logging.basicConfig(
            level=getattr(logging, level),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('council_scraper.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def extract_meeting_title_from_url(self, agenda_url):
        """Extract meeting title from <title> tag in head section"""
    
        try:
            self.logger.info(f"[TITLE-EXTRACT] Fetching meeting title from: {agenda_url}")
        
            response = self.session.get(agenda_url)
            response.raise_for_status()
        
            self.logger.debug(f"[TITLE-EXTRACT] Response status: {response.status_code}")
        
            soup = BeautifulSoup(response.content, 'html.parser')
        
            # Extract title from <title> tag in head
            if soup.title and soup.title.string:
                title_text = soup.title.string.strip()
                self.logger.info(f"[TITLE-EXTRACT] ✓ Found page title: '{title_text}'")
            
                # Basic validation - ensure it's not too long and looks like a meeting title
                if len(title_text) > 5 and len(title_text) < 200:
                    return title_text
                else:
                    self.logger.warning(f"[TITLE-EXTRACT] ✗ Title seems invalid (length: {len(title_text)})")
                    return None
            else:
                self.logger.warning("[TITLE-EXTRACT] ✗ No <title> tag found or empty")
                return None
            
        except Exception as e:
            self.logger.error(f"[TITLE-EXTRACT] ✗ Error extracting title: {str(e)}")
            return None

    def sanitize_folder_name(self, folder_name):
        """Sanitize folder name for filesystem compatibility"""

        self.logger.debug(f"[SANITIZE] Input folder name: '{folder_name}'")

        # Remove or replace invalid filesystem characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '-', folder_name)

        # Remove leading/trailing spaces and dots
        sanitized = sanitized.strip(' .')

        # Limit length to avoid filesystem limits
        if len(sanitized) > 200:
            sanitized = sanitized[:197] + "..."

        # Ensure it's not empty
        if not sanitized:
            sanitized = "Council_Meeting"

        self.logger.debug(f"[SANITIZE] Output folder name: '{sanitized}'")
        return sanitized

    def is_already_scraped(self, meeting_folder_path):
        """Return True if meeting_folder_path already contains at least one PDF."""
        if not os.path.isdir(meeting_folder_path):
            return False
        pdfs = [f for f in os.listdir(meeting_folder_path) if f.lower().endswith('.pdf')]
        return len(pdfs) > 0

    def scrape_agenda(self, agenda_url, meeting_date=None, use_selenium=True):
        """Main scraping function using three-stage approach"""
        try:
            self.logger.info("=" * 80)
            self.logger.info("[START] STARTING AGENDA SCRAPING PROCESS")
            self.logger.info("=" * 80)
            
            # Extract meeting title from the main page for folder naming
            self.logger.info("[FOLDER-NAME] Determining folder name...")
            folder_name = self.extract_meeting_title_from_url(agenda_url)
            
            if folder_name:
                self.logger.info(f"[FOLDER-NAME] ✓ Using meeting title: '{folder_name}'")
            else:
                self.logger.warning(f"[FOLDER-NAME] ✗ Meeting title extraction failed")
                
                # If no meeting title found, fall back to provided date or current date
                if meeting_date:
                    folder_name = meeting_date.replace('/', '-')
                    self.logger.info(f"[FOLDER-NAME] ✓ Fallback to provided date: '{folder_name}'")
                else:
                    folder_name = datetime.now().strftime('%Y-%m-%d')
                    self.logger.info(f"[FOLDER-NAME] ✓ Fallback to current date: '{folder_name}'")
                
                folder_name += "_Council"
                self.logger.info(f"[FOLDER-NAME] ✓ Final fallback name: '{folder_name}'")
            
            # Sanitize folder name for filesystem
            sanitized_folder_name = self.sanitize_folder_name(folder_name)
            
            full_output_path = os.path.join(self.output_folder, sanitized_folder_name)
            
            self.logger.info(f"[FOLDER-PATH] Final folder path determined: {full_output_path}")
            
            os.makedirs(full_output_path, exist_ok=True)
            self.logger.info(f"[FOLDER] ✓ Created output folder: {full_output_path}")
            
            # Stage 1: Extract AIDocs HTML
            self.logger.info("=" * 80)
            self.logger.info("[STAGE 1] EXTRACTING AIDOCS HTML")
            self.logger.info("=" * 80)
            aidocs_html_path = self.extract_aidocs_html(agenda_url, full_output_path)
            if not aidocs_html_path:
                return {"status": "error", "error_message": "Failed to extract AIDocs HTML"}
            
            # Stage 2: Analyze and create target files
            self.logger.info("=" * 80)
            self.logger.info("[STAGE 2] ANALYZING STRUCTURE AND CREATING TARGETS")
            self.logger.info("=" * 80)
            analysis_result = self.analyze_and_create_targets(aidocs_html_path, full_output_path)
            if not analysis_result:
                return {"status": "error", "error_message": "Failed to analyze structure"}
            
            # Stage 3: Download using separate downloader
            self.logger.info("=" * 80)
            self.logger.info("[STAGE 3] DOWNLOADING SUPPORTING DOCUMENTS")
            self.logger.info("=" * 80)
            
            # Extract base URL from agenda_url for the downloader
            from urllib.parse import urlparse
            parsed_url = urlparse(agenda_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}/web/"
            
            downloader = SupportingDocsDownloader(
                session=self.session,
                logger=self.logger,
                base_url=base_url
            )
            
            download_result = downloader.download_documents_from_json(
                analysis_result['targets_file'], 
                full_output_path
            )
            
            # Final summary
            self.logger.info("=" * 80)
            self.logger.info("[COMPLETE] SCRAPING COMPLETED SUCCESSFULLY!")
            self.logger.info(f"[SUMMARY] Meeting folder: {sanitized_folder_name}")
            self.logger.info(f"[SUMMARY] Analysis: {analysis_result['supporting_docs_count']} supporting docs found")
            self.logger.info(f"[SUMMARY] Downloads: {download_result.get('successful_downloads', 0)} successful, {download_result.get('failed_downloads', 0)} failed")
            self.logger.info(f"[OUTPUT] Files saved to: {full_output_path}")
            self.logger.info("=" * 80)
            
            return {
                "status": "success",
                "meeting_folder": full_output_path,
                "meeting_title": sanitized_folder_name,
                "analysis_file": analysis_result['analysis_file'],
                "targets_file": analysis_result['targets_file'],
                "download_result": download_result,
                "agenda_url": agenda_url,
                "total_supporting_docs": analysis_result['supporting_docs_count'],
                "successful_downloads": download_result.get('successful_downloads', 0),
                "failed_downloads": download_result.get('failed_downloads', 0),
                "target_downloads": analysis_result['target_downloads'],
            }
            
        except Exception as e:
            self.logger.error(f"[CRITICAL] Scraping failed: {str(e)}")
            return {"status": "error", "error_message": str(e), "agenda_url": agenda_url}
    
    def extract_aidocs_html(self, agenda_url, output_path):
        """Stage 1: Navigate to and extract the clean AIDocs HTML"""
        
        try:
            # Step 1: Get main agenda page
            self.logger.info(f"[STEP 1] Fetching main agenda page")
            self.logger.info(f"    URL: {agenda_url}")
            response = self.session.get(agenda_url)
            response.raise_for_status()
            self.logger.info(f"    [SUCCESS] Main page fetched ({len(response.content):,} bytes)")
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Step 2: Find CivicClerkPublicPortalContent (with fallbacks)
            self.logger.info(f"[STEP 2] Looking for portal container div")
            portal_div = (soup.find('div', id='CivicClerkPublicPortalContent') or
                         soup.find('div', id='CivicPortalContent') or 
                         soup.find('div', id='CivicPortal') or
                         soup.find('div', class_=re.compile(r'portal', re.I)))
            
            if not portal_div:
                self.logger.error("    [ERROR] No portal container div found")
                # Debug: show available divs
                all_divs = soup.find_all('div', id=True)[:10]  # First 10 divs with IDs
                self.logger.debug(f"    [DEBUG] Available divs with IDs: {[div.get('id') for div in all_divs]}")
                return None
            self.logger.info("    [SUCCESS] Found portal container div")
            
            # Step 3: Find DocumentFrame iframe
            self.logger.info(f"[STEP 3] Looking for DocumentFrame iframe")
            document_iframe = portal_div.find('iframe', attrs={'name': 'DocumentFrame'})
            if not document_iframe or not document_iframe.get('src'):
                self.logger.error("    [ERROR] DocumentFrame iframe not found")
                # Debug: show available iframes
                all_iframes = portal_div.find_all('iframe')
                self.logger.debug(f"    [DEBUG] Available iframes: {[{'name': iframe.get('name'), 'id': iframe.get('id'), 'src': iframe.get('src')[:50] if iframe.get('src') else None} for iframe in all_iframes]}")
                return None
            
            document_iframe_url = urljoin(agenda_url, document_iframe['src'])
            self.logger.info(f"    [SUCCESS] DocumentFrame URL: {document_iframe_url}")
            
            # Step 4: Get DocumentFrame content
            self.logger.info(f"[STEP 4] Fetching DocumentFrame content")
            document_response = self.session.get(document_iframe_url)
            document_response.raise_for_status()
            self.logger.info(f"    [SUCCESS] DocumentFrame content fetched ({len(document_response.content):,} bytes)")
            
            document_soup = BeautifulSoup(document_response.content, 'html.parser')
            
            # Step 5: Find docViewer iframe within DocumentFrame
            self.logger.info(f"[STEP 5] Looking for docViewer iframe")
            docviewer_iframe = document_soup.find('iframe', id='docViewer')
            if not docviewer_iframe or not docviewer_iframe.get('src'):
                # Fallback to AIDocs.aspx iframe
                self.logger.info("    [FALLBACK] Looking for AIDocs.aspx iframe")
                aidocs_iframe = document_soup.find('iframe', src=re.compile(r'AIDocs\.aspx'))
                if aidocs_iframe:
                    docviewer_iframe = aidocs_iframe
                    self.logger.info("    [SUCCESS] Found AIDocs.aspx iframe as fallback")
                else:
                    self.logger.error("    [ERROR] No docViewer or AIDocs iframe found")
                    # Debug: show available iframes
                    all_iframes = document_soup.find_all('iframe')
                    self.logger.debug(f"    [DEBUG] Available iframes in DocumentFrame: {[{'id': iframe.get('id'), 'src': iframe.get('src')[:50] if iframe.get('src') else None} for iframe in all_iframes]}")
                    return None
            
            aidocs_url = urljoin(agenda_url, docviewer_iframe['src'])
            id_match = re.search(r'id=(\d+)', docviewer_iframe['src'])
            docviewer_id = id_match.group(1) if id_match else "unknown"
            
            self.logger.info(f"    [SUCCESS] DocViewer ID: {docviewer_id}")
            self.logger.info(f"    [SUCCESS] AIDocs URL: {aidocs_url}")
            
            # Step 6: Get AIDocs.aspx page content (the clean agenda content)
            self.logger.info(f"[STEP 6] Fetching clean AIDocs content")
            aidocs_response = self.session.get(aidocs_url)
            aidocs_response.raise_for_status()
            self.logger.info(f"    [SUCCESS] AIDocs content fetched ({len(aidocs_response.content):,} bytes)")
            
            # Save the clean AIDocs HTML
            aidocs_html_path = os.path.join(output_path, "aidocs_content.html")
            with open(aidocs_html_path, "w", encoding="utf-8") as f:
                f.write(aidocs_response.text)
            
            self.logger.info(f"    [SAVED] Clean AIDocs HTML saved to: {aidocs_html_path}")
            
            return aidocs_html_path
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"[ERROR] HTTP request failed: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to extract AIDocs HTML: {str(e)}")
            return None
    
    def analyze_and_create_targets(self, aidocs_html_path, output_path):
        """Stage 2: Analyze HTML and create target downloads file"""
        
        try:
            self.logger.info(f"[ANALYZE] Starting HTML structure analysis")
            self.logger.info(f"    Input file: {aidocs_html_path}")
            
            # Initialize the analyzer
            analyzer = AidocsHtmlAnalyzerSorted()
            
            # Analyze the HTML file
            if not analyzer.analyze_file(aidocs_html_path):
                self.logger.error("[ERROR] HTML analysis failed")
                return None
            
            # Create analysis file path
            analysis_file = os.path.join(output_path, "analysis_structure.json")
            
            # Save the complete analysis
            if not analyzer.save_simplified_json(analysis_file):
                self.logger.error("[ERROR] Failed to save analysis file")
                return None
            
            self.logger.info(f"[SAVED] Analysis structure saved to: {analysis_file}")
            
            # Extract supporting documents only
            supporting_docs = analyzer.extract_supporting_documents_for_scraper()
            
            self.logger.info(f"[EXTRACTED] Found {len(supporting_docs)} supporting documents:")
            for i, doc in enumerate(supporting_docs, 1):
                self.logger.info(f"  {i}. {doc['title']}")
            
            # Create target downloads file
            targets_file = os.path.join(output_path, "target_downloads.json")
            target_downloads = []
            
            for doc in supporting_docs:
                recommended_filename = self.create_recommended_filename(doc)
                target_downloads.append({
                    'title': doc['title'],
                    'url': doc['url'],
                    'recommended_filename': recommended_filename,
                    'doc_number': doc['doc_number'],
                    'ad_value': doc['ad_value'],
                    'parent_item_number': doc.get('parent_item_number', ''),
                    'parent_item_text': doc.get('parent_item_text', ''),
                })
            
            with open(targets_file, 'w', encoding='utf-8') as f:
                json.dump(target_downloads, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"[SAVED] Target downloads saved to: {targets_file}")
            self.logger.info(f"[TARGETS] Created {len(target_downloads)} download targets")
            
            return {
                'analysis_file': analysis_file,
                'targets_file': targets_file,
                'supporting_docs_count': len(supporting_docs),
                'target_downloads': target_downloads
            }
            
        except Exception as e:
            self.logger.error(f"[ERROR] HTML analysis failed: {str(e)}")
            return None
    
    def create_recommended_filename(self, doc):
        """Create filename with 'Item X.Y' prefix.

        Format: Item {parent_item_number} {clean_title}.pdf
        Total filename capped at 120 characters (prefix + title + .pdf).
        """
        title = doc['title']
        item_number = doc.get('parent_item_number', '')

        # Strip "Supporting Document N - " prefix (old agenda format)
        clean_title = re.sub(
            r'^Supporting Document \d+\s*[-:]?\s*', '', title, flags=re.IGNORECASE
        ).strip()

        # Remove filesystem-unsafe characters
        safe_title = re.sub(r'[<>:"/\\|?*]', '', clean_title)
        safe_title = re.sub(r'\s+', ' ', safe_title).strip()

        prefix = f"Item {item_number} " if item_number else ""

        # Cap total filename at 120 chars
        max_title_len = 120 - len(prefix) - 4  # 4 = len('.pdf')
        if max_title_len < 10:
            max_title_len = 10
        if len(safe_title) > max_title_len:
            safe_title = safe_title[:max_title_len]

        return f"{prefix}{safe_title}.pdf"

def write_run_summary(output_folder, meeting_title, agenda_url,
                      target_downloads, download_result, combined_pdf_path=None):
    """Write a markdown-formatted _run_summary.txt into the meeting folder.

    Always written even when zero documents were found.
    Returns the path to the written file.
    """
    run_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    found = len(target_downloads)
    downloaded = download_result.get('successful_downloads', 0)
    failed = download_result.get('failed_downloads', 0)

    lines = [
        f'# {meeting_title} — Supporting Documents Run',
        '',
        f'**Run date:** {run_date}',
        f'**URL:** {agenda_url}',
        '',
        '## Documents',
        '',
        '| Item | Title | Status | File |',
        '|------|-------|--------|------|',
    ]

    for target in target_downloads:
        item_num = target.get('parent_item_number', '')
        title = target.get('title', '')[:60]
        filename = target.get('recommended_filename', '')
        filepath = os.path.join(output_folder, filename)
        status = 'Downloaded' if os.path.isfile(filepath) else 'Failed'
        lines.append(f'| {item_num} | {title} | {status} | {filename} |')

    lines += [
        '',
        '## Summary',
        f'- Supporting documents found: {found}',
        f'- Downloaded: {downloaded}  Failed: {failed}',
    ]

    if combined_pdf_path:
        lines.append(f'- Combined PDF: {os.path.basename(combined_pdf_path)}')
    else:
        lines.append('- Combined PDF: Not generated — use --combine to create')

    summary_path = os.path.join(output_folder, '_run_summary.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    return summary_path


def main():
    parser = argparse.ArgumentParser(description='Council Document Scraper - Three-Stage Approach')
    parser.add_argument('agenda_url', help='Council agenda URL')
    parser.add_argument('--output-folder', default='council_docs', help='Output folder')
    parser.add_argument('--meeting-date', help='Meeting date for folder naming (e.g., 2025-09-09)')
    parser.add_argument('--no-selenium', action='store_true', help='Disable Selenium (requests only)')
    parser.add_argument('--log-level', default='INFO', help='Logging level (DEBUG, INFO, WARNING, ERROR)')
    
    args = parser.parse_args()
    
    scraper = CouncilDocumentScraper(args.output_folder, args.log_level)
    result = scraper.scrape_agenda(
        args.agenda_url, 
        args.meeting_date,
        use_selenium=not args.no_selenium
    )
    
    # Output JSON for N8N to consume
    print(json.dumps(result, indent=2))
    
    # Exit with appropriate code
    sys.exit(0 if result['status'] == 'success' else 1)

if __name__ == "__main__":
    main()
