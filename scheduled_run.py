"""scheduled_run.py
Orchestrator for the weekly Friday council agenda scrape.

Usage:
    python scheduled_run.py                            # auto-discover, skip done
    python scheduled_run.py --url URL [--force]        # specific meeting, optionally force
    python scheduled_run.py --dry-run                  # show what would run, no downloads
"""
import argparse
import logging
import os
import sys
from datetime import datetime

from council_document_scraper import CouncilDocumentScraper
from meeting_discovery import discover_latest_council_meetings

OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), 'council_docs')
RUN_LOG = os.path.join(os.path.dirname(__file__), 'run_log.txt')


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('council_scraper.log', encoding='utf-8'),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)


def append_run_log(entries: list):
    """Append a timestamped block to run_log.txt."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(RUN_LOG, 'a', encoding='utf-8') as f:
        f.write('\n=== Run at ' + timestamp + ' ===\n')
        for line in entries:
            f.write(line + '\n')


def main():
    parser = argparse.ArgumentParser(description='Mitcham Council Agenda Scraper - Scheduled Run')
    parser.add_argument('--url', help='Override: scrape this specific agenda URL')
    parser.add_argument('--force', action='store_true',
                        help='Re-scrape even if already downloaded')
    parser.add_argument('--dry-run', action='store_true',
                        help='Discover and show meetings without downloading')
    args = parser.parse_args()

    logger = setup_logging()
    scraper = CouncilDocumentScraper(output_folder=OUTPUT_FOLDER)
    log_entries = []

    # --- Determine meetings to process ---
    if args.url:
        meetings = [{'title': 'Manual override', 'url': args.url, 'meeting_id': 0}]
        logger.info('[SCHEDULED] Using provided URL: ' + args.url)
    else:
        meetings = discover_latest_council_meetings()
        if not meetings:
            msg = 'No meetings discovered. Check portal or config.json.'
            logger.error('[SCHEDULED] ' + msg)
            append_run_log([msg])
            sys.exit(1)

    logger.info('[SCHEDULED] ' + str(len(meetings)) + ' meeting(s) discovered')

    # --- Process each meeting ---
    scraped_count = 0
    skipped_count = 0

    for meeting in meetings:
        url = meeting['url']
        title = meeting.get('title', 'Unknown')
        logger.info('[SCHEDULED] Considering: ' + title)

        sanitised = scraper.sanitize_folder_name(title)
        folder_path = os.path.join(OUTPUT_FOLDER, sanitised)

        if not args.force and scraper.is_already_scraped(folder_path):
            msg = 'SKIP (already done): ' + title
            logger.info('[SCHEDULED] ' + msg)
            log_entries.append(msg)
            skipped_count += 1
            continue

        if args.dry_run:
            msg = 'DRY-RUN (would scrape): ' + title + ' | ' + url
            logger.info('[SCHEDULED] ' + msg)
            log_entries.append(msg)
            continue

        logger.info('[SCHEDULED] Scraping: ' + title)
        result = scraper.scrape_agenda(url)

        if result['status'] == 'success':
            msg = ('OK: ' + result['meeting_title'] + ' | '
                   + str(result['total_supporting_docs']) + ' docs found | '
                   + str(result['successful_downloads']) + ' downloaded | '
                   + str(result['failed_downloads']) + ' failed')
        else:
            msg = 'ERROR: ' + title + ' | ' + result.get('error_message', 'unknown error')

        logger.info('[SCHEDULED] ' + msg)
        log_entries.append(msg)
        scraped_count += 1

    summary = ('Summary: ' + str(scraped_count) + ' scraped, '
               + str(skipped_count) + ' skipped'
               + (' [DRY RUN]' if args.dry_run else ''))
    logger.info('[SCHEDULED] ' + summary)
    log_entries.append(summary)
    append_run_log(log_entries)


if __name__ == '__main__':
    main()
