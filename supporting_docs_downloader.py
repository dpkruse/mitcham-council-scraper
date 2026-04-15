# supporting_docs_downloader.py
import requests
import os
import json
import logging
import time
from urllib.parse import urljoin


class SupportingDocsDownloader:
    def __init__(self, session=None, logger=None, base_url=None):
        self.session = session or requests.Session()
        self.logger = logger or self._setup_default_logger()
        self.base_url = base_url or 'https://mitcham.civicclerk.com.au/web/'

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def _setup_default_logger(self):
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def download_documents_from_json(self, targets_json_path, output_folder):
        """Download all documents listed in target_downloads.json."""
        try:
            with open(targets_json_path, 'r', encoding='utf-8') as f:
                targets = json.load(f)

            self.logger.info(f'[START] {len(targets)} documents to download')
            os.makedirs(output_folder, exist_ok=True)

            successful_downloads = 0
            failed_downloads = 0
            results = []

            for i, target in enumerate(targets, 1):
                self.logger.info(f'[DOWNLOAD {i}/{len(targets)}] {target.get("title", "Unknown")}')
                result = self.download_single_document(target, output_folder)
                results.append(result)

                if result['status'] == 'success':
                    successful_downloads += 1
                    self.logger.info(f'[SUCCESS] {result["filename"]} ({result.get("file_size", 0):,} bytes)')
                else:
                    failed_downloads += 1
                    self.logger.warning(f'[FAILED] {result.get("error", "Unknown error")}')

                time.sleep(1)

            self.logger.info(f'[COMPLETE] {successful_downloads} successful, {failed_downloads} failed')
            return {
                'status': 'complete',
                'total_targets': len(targets),
                'successful_downloads': successful_downloads,
                'failed_downloads': failed_downloads,
                'results': results,
                'output_folder': output_folder,
            }

        except Exception as e:
            self.logger.error(f'[CRITICAL] Download process failed: {e}')
            return {'status': 'error', 'error': str(e)}

    def download_single_document(self, target, output_folder):
        """Download one document via direct GET request.

        GenFile.aspx responds with Content-Type: application/pdf directly,
        so no redirect-following or browser interaction is needed.
        """
        raw_url = target.get('url', '')
        recommended_filename = target.get('recommended_filename', 'document.pdf')
        filepath = os.path.join(output_folder, recommended_filename)

        # Resolve relative URLs (e.g. ../GenFile.aspx?ad=123&token=abc)
        if raw_url.startswith('..'):
            url = urljoin(self.base_url, raw_url.lstrip('../'))
        elif raw_url.startswith('http'):
            url = raw_url
        else:
            url = urljoin(self.base_url, raw_url)

        self.logger.debug(f'[DOWNLOAD] {recommended_filename}')
        self.logger.debug(f'    URL: {url}')

        try:
            response = self.session.get(url, stream=True)
            response.raise_for_status()

            content_type = response.headers.get('content-type', '').lower()
            if 'application/pdf' in content_type or 'application/octet-stream' in content_type:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return {
                    'status': 'success',
                    'method': 'requests_direct',
                    'filename': recommended_filename,
                    'filepath': filepath,
                    'file_size': os.path.getsize(filepath),
                    'url': url,
                    'target': target,
                }
            else:
                self.logger.warning(f'[DOWNLOAD] Expected PDF, got {content_type}: {url}')
                return {
                    'status': 'unexpected_content_type',
                    'error': f'Expected application/pdf, got {content_type}',
                    'url': url,
                    'target': target,
                }

        except Exception as e:
            self.logger.warning(f'[DOWNLOAD] Failed: {e}')
            return {
                'status': 'error',
                'error': str(e),
                'url': url,
                'target': target,
            }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Download supporting documents from target_downloads.json')
    parser.add_argument('targets_json', help='Path to target_downloads.json')
    parser.add_argument('--output-folder', required=True, help='Output folder for downloads')
    parser.add_argument('--base-url', default='https://mitcham.civicclerk.com.au/web/', help='Base URL for relative links')
    parser.add_argument('--log-level', default='INFO', help='Logging level')
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level),
                        format='%(asctime)s - %(levelname)s - %(message)s')

    downloader = SupportingDocsDownloader(base_url=args.base_url)
    result = downloader.download_documents_from_json(args.targets_json, args.output_folder)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
