# supporting_docs_downloader.py
import requests
from bs4 import BeautifulSoup
import os
import json
import logging
import time
import re
import glob
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class SupportingDocsDownloader:
    def __init__(self, session=None, logger=None, use_selenium=True, download_folder=None, base_url=None):
        self.session = session or requests.Session()
        self.logger = logger or self._setup_default_logger()
        self.use_selenium = use_selenium
        self.download_folder = download_folder
        self.driver = None
        
        # Set default base URL for Mitcham council
        self.base_url = base_url or 'https://mitcham.civicclerk.com.au/web/'
        
        # Set up user agent
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def _setup_default_logger(self):
        """Setup default logger if none provided"""
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def _setup_selenium_driver(self, download_folder):
        """Setup Selenium WebDriver with download preferences"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            
            # Set download preferences
            prefs = {
                "download.default_directory": os.path.abspath(download_folder),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "plugins.always_open_pdf_externally": True,
                "safebrowsing.enabled": False
            }
            chrome_options.add_experimental_option("prefs", prefs)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.logger.info("[SELENIUM] WebDriver initialized successfully")
            return True
            
        except Exception as e:
            self.logger.warning(f"[SELENIUM] Failed to initialize WebDriver: {str(e)}")
            self.logger.info("[SELENIUM] Falling back to requests-only mode")
            self.use_selenium = False
            return False
    
    def download_documents_from_json(self, targets_json_path, output_folder):
        """Main method to download documents from target_downloads.json"""
        
        try:
            # Load target downloads
            with open(targets_json_path, 'r', encoding='utf-8') as f:
                targets = json.load(f)
            
            self.logger.info(f"[START] Loading {len(targets)} documents from {targets_json_path}")
            
            # Create output folder
            os.makedirs(output_folder, exist_ok=True)
            
            # Setup Selenium if requested and store download folder for file renaming
            if self.use_selenium:
                self.download_folder = output_folder
                self._setup_selenium_driver(output_folder)
            
            # Download each document
            results = []
            successful_downloads = 0
            failed_downloads = 0
            
            for i, target in enumerate(targets, 1):
                self.logger.info(f"[DOWNLOAD {i}/{len(targets)}] {target.get('title', 'Unknown')}")
                
                result = self.download_single_document(target, output_folder)
                results.append(result)
                
                if result['status'] == 'success':
                    successful_downloads += 1
                    self.logger.info(f"[SUCCESS] {result['filename']} ({result.get('file_size', 0):,} bytes)")
                else:
                    failed_downloads += 1
                    self.logger.warning(f"[FAILED] {result.get('error', 'Unknown error')}")
                
                # Small delay between downloads
                time.sleep(1)
            
            # Cleanup
            if self.driver:
                self.driver.quit()
            
            # Summary
            self.logger.info(f"[COMPLETE] {successful_downloads} successful, {failed_downloads} failed")
            
            return {
                'status': 'complete',
                'total_targets': len(targets),
                'successful_downloads': successful_downloads,
                'failed_downloads': failed_downloads,
                'results': results,
                'output_folder': output_folder
            }
            
        except Exception as e:
            if self.driver:
                self.driver.quit()
            self.logger.error(f"[CRITICAL] Download process failed: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def download_single_document(self, target, output_folder):
        """Download a single document with two-stage redirect handling"""
        
        raw_url = target.get('url')
        recommended_filename = target.get('recommended_filename', 'document.pdf')
        filepath = os.path.join(output_folder, recommended_filename)
        
        # Fix URL resolution - handle relative URLs
        if raw_url.startswith('..'):
            clean_url = raw_url.lstrip('../')
            url = urljoin(self.base_url, clean_url)
        elif raw_url.startswith('http'):
            url = raw_url
        else:
            url = urljoin(self.base_url, raw_url)
        
        self.logger.debug(f"[DOWNLOAD] {recommended_filename}")
        self.logger.debug(f"    Raw URL: {raw_url}")
        self.logger.debug(f"    Full URL: {url}")
        self.logger.debug(f"    Target filename: {recommended_filename}")
        
        # Stage 1: Get the initial GenFile.aspx page (may contain redirect)
        stage1_result = self._stage1_get_redirect_page(url, filepath, target)
        if stage1_result['status'] == 'direct_pdf':
            # Lucky! Got PDF directly - ensure it's saved with recommended name
            stage1_result['filename'] = recommended_filename
            return stage1_result
        elif stage1_result['status'] == 'redirect_found':
            # Found redirect, proceed to stage 2 with recommended filename
            return self._stage2_follow_redirect(stage1_result['redirect_url'], filepath, target, recommended_filename)
        else:
            # Stage 1 failed
            return stage1_result
    
    def _stage1_get_redirect_page(self, url, filepath, target):
        """Stage 1: Get GenFile.aspx page and look for redirect"""
        
        try:
            self.logger.debug(f"[STAGE1] Getting initial page: {url}")
            
            response = self.session.get(url, stream=True)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '').lower()
            
            if 'application/pdf' in content_type or 'application/octet-stream' in content_type:
                # Direct PDF download - save it
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                file_size = os.path.getsize(filepath)
                self.logger.debug(f"[STAGE1] Direct PDF download successful")
                
                return {
                    'status': 'direct_pdf',
                    'method': 'direct_download',
                    'filename': os.path.basename(filepath),
                    'filepath': filepath,
                    'file_size': file_size,
                    'url': url,
                    'target': target
                }
            
            elif 'text/html' in content_type:
                # HTML page - look for redirect
                html_content = response.text
                redirect_url = self._extract_redirect_url(html_content, url)
                
                if redirect_url:
                    self.logger.debug(f"[STAGE1] Found redirect URL: {redirect_url}")
                    return {
                        'status': 'redirect_found',
                        'redirect_url': redirect_url,
                        'url': url,
                        'target': target
                    }
                else:
                    # Save HTML for inspection
                    html_filepath = filepath.replace('.pdf', '_stage1_response.html')
                    with open(html_filepath, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    
                    return {
                        'status': 'no_redirect_found',
                        'error': 'No UserControls/pdf redirect found in HTML',
                        'html_file': html_filepath,
                        'url': url,
                        'target': target
                    }
            
            else:
                return {
                    'status': 'unsupported_content_type',
                    'error': f'Unsupported content type: {content_type}',
                    'url': url,
                    'target': target
                }
                
        except Exception as e:
            self.logger.debug(f"[STAGE1] Failed: {str(e)}")
            return {
                'status': 'stage1_error',
                'error': str(e),
                'url': url,
                'target': target
            }
    
    def _extract_redirect_url(self, html_content, base_url):
        """Extract redirect URL from HTML content"""
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for script tags containing UserControls/pdf
            script_tags = soup.find_all('script')
            
            for script in script_tags:
                if script.string and 'UserControls/pdf' in script.string:
                    # Extract the path using regex
                    match = re.search(r'UserControls\/pdf[^"\']+', script.string)
                    if match:
                        path = match.group(0)
                        
                        # Build the full redirect URL
                        # Transform UserControls/pdf/DocStream.aspx to UserControls/pdf/web/DocPDFWrapper.aspx
                        if 'DocStream.aspx' in path:
                            path = path.replace('DocStream.aspx', 'web/DocPDFWrapper.aspx')
                        
                        redirect_url = urljoin(self.base_url, path)
                        return redirect_url
            
            return None
            
        except Exception as e:
            self.logger.debug(f"[REDIRECT] Error extracting redirect URL: {str(e)}")
            return None
    
    def _stage2_follow_redirect(self, redirect_url, filepath, target, recommended_filename):
        """Stage 2: Follow redirect to PDF viewer and click download button"""
        
        if self.use_selenium and self.driver:
            return self._stage2_selenium_download(redirect_url, filepath, target, recommended_filename)
        else:
            return self._stage2_requests_download(redirect_url, filepath, target)
    
    def _stage2_selenium_download(self, redirect_url, filepath, target, recommended_filename):
        """Stage 2 with Selenium: Navigate to PDF viewer and click download button"""
        
        try:
            self.logger.debug(f"[STAGE2-SELENIUM] Navigating to: {redirect_url}")
            
            # Navigate to the PDF viewer page
            self.driver.get(redirect_url)
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Look for the download button
            try:
                download_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "download"))
                )
                
                self.logger.debug(f"[STAGE2-SELENIUM] Found download button, clicking...")
                download_button.click()
                
                # Wait for download to complete
                self.logger.debug(f"[STAGE2-SELENIUM] Waiting for file download...")
                downloaded_file = self._wait_for_any_new_pdf(self.download_folder, timeout=60)
                
                if downloaded_file is not None:  # CHECK FOR NONE!
                    # Rename the downloaded file to recommended filename
                    final_path = os.path.join(self.download_folder, recommended_filename)
                    
                    try:
                        # If target filename already exists, remove it
                        if os.path.exists(final_path):
                            os.remove(final_path)
                            self.logger.debug(f"[RENAME] Removed existing file: {recommended_filename}")
                        
                        # Rename downloaded file to recommended name
                        os.rename(downloaded_file, final_path)
                        file_size = os.path.getsize(final_path)
                        
                        self.logger.info(f"[RENAME] Renamed '{os.path.basename(downloaded_file)}' to '{recommended_filename}'")
                        
                        return {
                            'status': 'success',
                            'method': 'selenium_download',
                            'filename': recommended_filename,
                            'filepath': final_path,
                            'file_size': file_size,
                            'url': redirect_url,
                            'target': target
                        }
                        
                    except Exception as rename_error:
                        self.logger.error(f"[RENAME] Error renaming file: {rename_error}")
                        # Return success anyway with original filename
                        return {
                            'status': 'success',
                            'method': 'selenium_download',
                            'filename': os.path.basename(downloaded_file),
                            'filepath': downloaded_file,
                            'file_size': os.path.getsize(downloaded_file),
                            'url': redirect_url,
                            'target': target,
                            'rename_error': str(rename_error)
                        }
                else:
                    return {
                        'status': 'download_timeout',
                        'error': 'File did not appear after clicking download button',
                        'url': redirect_url,
                        'target': target
                    }
                
            except TimeoutException:
                # Download button not found, try alternative approaches
                self.logger.debug(f"[STAGE2-SELENIUM] Download button not found, trying alternatives")
                
                # Try to find any clickable download elements
                download_selectors = [
                    "button[class*='download']",
                    "a[class*='download']",
                    "button[title*='download']",
                    "a[title*='download']"
                ]
                
                for selector in download_selectors:
                    try:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                        element.click()
                        self.logger.debug(f"[STAGE2-SELENIUM] Clicked alternative download element: {selector}")
                        
                        downloaded_file = self._wait_for_any_new_pdf(self.download_folder)
                        if downloaded_file:
                            # Rename to recommended filename
                            final_path = os.path.join(self.download_folder, recommended_filename)
                            if os.path.exists(final_path):
                                os.remove(final_path)
                            os.rename(downloaded_file, final_path)
                            
                            file_size = os.path.getsize(final_path)
                            return {
                                'status': 'success',
                                'method': 'selenium_alternative',
                                'filename': recommended_filename,
                                'filepath': final_path,
                                'file_size': file_size,
                                'url': redirect_url,
                                'target': target
                            }
                        
                    except NoSuchElementException:
                        continue
                
                return {
                    'status': 'no_download_button',
                    'error': 'No download button found on PDF viewer page',
                    'url': redirect_url,
                    'target': target
                }
                
        except Exception as e:
            self.logger.debug(f"[STAGE2-SELENIUM] Failed: {str(e)}")
            return {
                'status': 'stage2_selenium_error',
                'error': str(e),
                'url': redirect_url,
                'target': target
            }
    
    def _stage2_requests_download(self, redirect_url, filepath, target):
        """Stage 2 with requests: Try to download PDF directly from viewer page"""
        
        try:
            self.logger.debug(f"[STAGE2-REQUESTS] Attempting direct download from: {redirect_url}")
            
            response = self.session.get(redirect_url, stream=True)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '').lower()
            
            if 'application/pdf' in content_type:
                # Direct PDF download
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                file_size = os.path.getsize(filepath)
                
                return {
                    'status': 'success',
                    'method': 'requests_direct',
                    'filename': os.path.basename(filepath),
                    'filepath': filepath,
                    'file_size': file_size,
                    'url': redirect_url,
                    'target': target
                }
            else:
                # Save HTML for manual inspection
                html_filepath = filepath.replace('.pdf', '_stage2_response.html')
                with open(html_filepath, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                
                return {
                    'status': 'stage2_html_received',
                    'error': 'Got HTML instead of PDF from redirect URL',
                    'html_file': html_filepath,
                    'url': redirect_url,
                    'target': target
                }
                
        except Exception as e:
            self.logger.debug(f"[STAGE2-REQUESTS] Failed: {str(e)}")
            return {
                'status': 'stage2_requests_error',
                'error': str(e),
                'url': redirect_url,
                'target': target
            }
    
    def _wait_for_any_new_pdf(self, download_folder, timeout=60):
        """Wait for any new PDF file to appear in download folder"""
        
        # Get existing PDF files before download starts
        start_time = time.time()
        existing_pdfs = set()
        try:
            existing_pdfs = set(glob.glob(os.path.join(download_folder, '*.pdf')))
            self.logger.debug(f"[FILE-WAIT] Found {len(existing_pdfs)} existing PDFs before download")
        except Exception as e:
            self.logger.debug(f"[FILE-WAIT] Error listing existing files: {e}")
        
        while time.time() - start_time < timeout:
            try:
                # Get current PDF files
                current_pdfs = set(glob.glob(os.path.join(download_folder, '*.pdf')))
                new_pdfs = current_pdfs - existing_pdfs
                
                self.logger.debug(f"[FILE-WAIT] Current PDFs: {len(current_pdfs)}, New: {len(new_pdfs)}")
                
                if new_pdfs:
                    # Found new PDF file(s)
                    new_file = list(new_pdfs)[0]  # Get first new file
                    
                    try:
                        file_size = os.path.getsize(new_file)
                        if file_size > 0:
                            # Wait a bit more to ensure download is complete
                            time.sleep(3)
                            final_size = os.path.getsize(new_file)
                            
                            if final_size == file_size:  # File size stable
                                self.logger.debug(f"[FILE-WAIT] Found new PDF: {os.path.basename(new_file)} ({final_size} bytes)")
                                return new_file
                            else:
                                self.logger.debug(f"[FILE-WAIT] File still downloading: {file_size} -> {final_size} bytes")
                                
                    except OSError as e:
                        self.logger.debug(f"[FILE-WAIT] Error accessing file {new_file}: {e}")
                        continue
                
                time.sleep(1)
                
            except Exception as e:
                self.logger.debug(f"[FILE-WAIT] Error during file detection: {e}")
                time.sleep(1)
        
        self.logger.debug(f"[FILE-WAIT] Timeout after {timeout} seconds - no new PDF found")
        return None

def main():
    """Standalone usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Download supporting documents from target_downloads.json')
    parser.add_argument('targets_json', help='Path to target_downloads.json file')
    parser.add_argument('--output-folder', required=True, help='Output folder for downloads')
    parser.add_argument('--base-url', default='https://mitcham.civicclerk.com.au/web/', help='Base URL for relative links')
    parser.add_argument('--no-selenium', action='store_true', help='Disable Selenium (requests only)')
    parser.add_argument('--log-level', default='INFO', help='Logging level')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Create downloader
    downloader = SupportingDocsDownloader(
        use_selenium=not args.no_selenium,
        download_folder=args.output_folder,
        base_url=args.base_url
    )
    
    # Download documents
    result = downloader.download_documents_from_json(args.targets_json, args.output_folder)
    
    # Output result
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
