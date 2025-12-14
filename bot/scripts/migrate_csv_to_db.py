#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Migration script to import historical exchange rates from CSV to SQLite database.

This script reads exchange_rates.csv and imports the data into the SQLite database
using the ExchangeRateDatabase class from bot/database.py.
"""

import sys
import logging
import re
import argparse
from datetime import datetime
from typing import List, Tuple, Optional
from pathlib import Path
from ..database import ExchangeRateDatabase

# Default configuration
DEFAULT_CSV_FILE = '../data/exchange_rates.csv'
DEFAULT_DB_FILE = '../data/exchange_rates.db'
BATCH_SIZE = 1000  # Process records in batches for better performance

# Setup logging
logger = logging.getLogger(__name__)

# Regex pattern to match CSV lines - using simple float pattern
CSV_PATTERN = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),([0-9.]+),([0-9.]+),([0-9.]+),([0-9.]+),([0-9.]+)$'


def parse_csv_line(line: str) -> Optional[Tuple]:
    """
    Parse and validate a CSV line.

    Returns:
        Tuple of (timestamp_str, usd_buy, usd_sell, eur_buy, eur_sell, pln_cross) or None
    """
    line = line.strip()
    if not line:  # Skip empty lines
        return None

    match = re.match(CSV_PATTERN, line)
    if not match:
        return None

    try:
        timestamp_str = match.group(1)
        usd_buy = float(match.group(2))
        usd_sell = float(match.group(3))
        eur_buy = float(match.group(4))
        eur_sell = float(match.group(5))
        pln_cross = float(match.group(6))

        # Validate timestamp format
        datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

        return (timestamp_str, usd_buy, usd_sell, eur_buy, eur_sell, pln_cross)
    except (ValueError, AttributeError, IndexError) as e:
        logger.warning(f"Error parsing line: {e}")
        return None


def deduplicate_rates(csv_records: List[Tuple]) -> List[Tuple]:
    """
    Deduplicate consecutive identical rates, keeping only the first timestamp.

    Args:
        csv_records: List of parsed CSV records

    Returns:
        List of deduplicated records (timestamp, rates...)
    """
    if not csv_records:
        return []

    deduplicated = []
    prev_rates = None
    first_timestamp = None

    for record in csv_records:
        timestamp_str, usd_buy, usd_sell, eur_buy, eur_sell, pln_cross = record
        current_rates = (usd_buy, usd_sell, eur_buy, eur_sell, pln_cross)

        if current_rates != prev_rates:
            # Rates changed - store the previous group if exists
            if prev_rates is not None:
                deduplicated.append((first_timestamp, *prev_rates))

            # Start new group
            first_timestamp = timestamp_str
            prev_rates = current_rates

    # Don't forget the last group
    if prev_rates is not None:
        deduplicated.append((first_timestamp, *prev_rates))

    return deduplicated


def prepare_database_records(deduplicated_records: List[Tuple]) -> List[Tuple]:
    """
    Convert deduplicated CSV records to database format.
    Each CSV line becomes 3 database records (USD, EUR, PLN).

    Returns:
        List of tuples for insert_exchange_rates():
        (timestamp, api_timestamp, source, currency_code_a, currency_code_b,
         rate_buy, rate_sell, rate_cross)
    """
    db_records = []

    for record in deduplicated_records:
        timestamp_str, usd_buy, usd_sell, eur_buy, eur_sell, pln_cross = record

        # Convert to datetime object
        dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        api_timestamp = int(dt.timestamp())

        # USD record (840 USD to 980 UAH)
        db_records.append(
            (
                timestamp_str,
                api_timestamp,
                'monobank',
                840,  # USD
                980,  # UAH
                usd_buy,
                usd_sell,
                None,  # No cross rate for USD
            )
        )

        # EUR record (978 EUR to 980 UAH)
        db_records.append(
            (
                timestamp_str,
                api_timestamp,
                'monobank',
                978,  # EUR
                980,  # UAH
                eur_buy,
                eur_sell,
                None,  # No cross rate for EUR
            )
        )

        # PLN record (985 PLN to 980 UAH)
        db_records.append(
            (
                timestamp_str,
                api_timestamp,
                'monobank',
                985,  # PLN
                980,  # UAH
                None,  # No buy rate for PLN
                None,  # No sell rate for PLN
                pln_cross,
            )
        )

    return db_records


def migrate_csv_to_sqlite(csv_file: str, db_file: str, dry_run: bool = False):
    """
    Main migration function.

    Args:
        csv_file: Path to the CSV file to migrate
        db_file: Path to the SQLite database file
        dry_run: If True, parse and validate CSV but don't write to database

    Returns:
        int: 0 on success, 1 on failure
    """
    logger.info("Starting CSV to SQLite migration")
    logger.info(f"CSV file: {csv_file}")
    logger.info(f"Database file: {db_file}")
    if dry_run:
        logger.info("DRY RUN MODE - No data will be written to database")

    # Statistics
    stats = {
        'total_lines': 0,
        'valid_lines': 0,
        'invalid_lines': 0,
        'deduplicated_records': 0,
        'db_records_prepared': 0,
        'inserted': 0,
        'duplicates_skipped': 0,
    }

    try:
        # Read and parse CSV file
        logger.info("Reading CSV file...")
        csv_records = []
        failed_examples = []

        with open(csv_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                stats['total_lines'] += 1

                parsed = parse_csv_line(line)
                if parsed:
                    csv_records.append(parsed)
                    stats['valid_lines'] += 1
                elif line.strip():  # Only count non-empty invalid lines
                    stats['invalid_lines'] += 1
                    # Keep first 5 failed examples for debugging
                    if len(failed_examples) < 5:
                        failed_examples.append((line_num, line.strip()[:100]))

                # Progress reporting
                if line_num % 10000 == 0:
                    logger.info(f"Processed {line_num} lines...")

        logger.info(
            f"CSV parsing complete. Valid records: {stats['valid_lines']}, " f"Invalid: {stats['invalid_lines']}"
        )

        # Show failed examples if any
        if failed_examples:
            logger.warning("Examples of failed parsing:")
            for line_num, line_preview in failed_examples:
                logger.warning(f"  Line {line_num}: {line_preview}")

        if stats['valid_lines'] == 0:
            logger.error("No valid records found. Please check CSV format.")
            return 1

        # Deduplicate consecutive identical rates
        logger.info("Deduplicating consecutive identical rates...")
        deduplicated = deduplicate_rates(csv_records)
        stats['deduplicated_records'] = len(deduplicated)
        logger.info(f"After deduplication: {stats['deduplicated_records']} unique rate periods")

        # Prepare database records
        logger.info("Preparing database records...")
        db_records = prepare_database_records(deduplicated)
        stats['db_records_prepared'] = len(db_records)
        logger.info(f"Prepared {stats['db_records_prepared']} database records " f"(3 currencies per CSV record)")

        # Insert into database in batches (skip if dry run)
        if dry_run:
            logger.info("DRY RUN: Skipping database insertion")
            logger.info(f"Would insert {stats['db_records_prepared']} records into database")
        else:
            logger.info("Inserting records into database...")
            with ExchangeRateDatabase(db_file) as db:
                for i in range(0, len(db_records), BATCH_SIZE):
                    batch = db_records[i : i + BATCH_SIZE]
                    inserted, ignored = db.insert_exchange_rates(batch)
                    stats['inserted'] += inserted
                    stats['duplicates_skipped'] += ignored

                    if (i // BATCH_SIZE + 1) % 10 == 0:
                        logger.info(
                            f"Batch {i // BATCH_SIZE + 1}: Inserted {stats['inserted']} records, "
                            f"skipped {stats['duplicates_skipped']} duplicates so far..."
                        )

        # Final report
        logger.info("\n" + "=" * 60)
        logger.info("MIGRATION COMPLETE" + (" (DRY RUN)" if dry_run else ""))
        logger.info("=" * 60)
        logger.info(f"Total CSV lines processed:       {stats['total_lines']}")
        logger.info(f"Valid records:                  {stats['valid_lines']}")
        logger.info(f"Invalid/skipped lines:          {stats['invalid_lines']}")
        logger.info(f"After deduplication:            {stats['deduplicated_records']}")
        logger.info(f"Database records prepared:      {stats['db_records_prepared']}")
        if not dry_run:
            logger.info(f"Records inserted:               {stats['inserted']}")
            logger.info(f"Duplicates skipped:             {stats['duplicates_skipped']}")
        logger.info("=" * 60)

        return 0

    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_file}")
        return 1
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}", exc_info=True)
        return 1


def main():
    """Parse command-line arguments and run migration."""
    parser = argparse.ArgumentParser(
        description='Migrate exchange rates from CSV to SQLite database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (uses default paths)
  python migrate_csv_to_db.py

  # Dry run to test without writing to database
  python migrate_csv_to_db.py --dry-run

  # Verbose output
  python migrate_csv_to_db.py --verbose

  # Custom file paths
  python migrate_csv_to_db.py --csv-file /path/to/rates.csv --db-file /path/to/db.sqlite

  # Combination
  python migrate_csv_to_db.py --csv-file custom.csv --dry-run --verbose
        """,
    )

    parser.add_argument(
        '--csv-file', type=str, default=DEFAULT_CSV_FILE, help=f'Path to CSV file (default: {DEFAULT_CSV_FILE})'
    )

    parser.add_argument(
        '--db-file',
        type=str,
        default=DEFAULT_DB_FILE,
        help=f'Path to SQLite database file (default: {DEFAULT_DB_FILE})',
    )

    parser.add_argument('--dry-run', action='store_true', help='Perform a dry run without writing to database')

    parser.add_argument('--verbose', action='store_true', help='Enable verbose output (DEBUG level logging)')

    args = parser.parse_args()

    # Configure logging based on verbose flag
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Convert relative paths to absolute based on script location
    script_dir = Path(__file__).parent
    csv_file = str((script_dir / args.csv_file).resolve())
    db_file = str((script_dir / args.db_file).resolve())

    # Run migration
    return migrate_csv_to_sqlite(csv_file, db_file, args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
