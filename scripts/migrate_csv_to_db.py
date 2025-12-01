#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
CSV to SQLite migration script for exchange rate data.
Migrates historical exchange rate data from CSV files to SQLite database.
"""

import argparse
import csv
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import database module
sys.path.insert(0, str(Path(__file__).parent.parent / "bot"))

# Import database module with error handling
try:
    from database import ExchangeRateDatabase
except ImportError as e:
    print(f"Error: Cannot import database module: {e}")
    print("Please ensure the database.py file exists in the bot/ directory.")
    sys.exit(1)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def parse_csv_row(row):
    """
    Parse a CSV row and extract exchange rate data.
    
    CSV format: Date Time, USD Buy Rate, USD Sell Rate, EUR Buy Rate, EUR Sell Rate, PLN Exchange Rate
    
    Args:
        row: CSV row as list of strings
        
    Returns:
        Tuple of (timestamp, rates_list) or (None, None) if invalid
    """
    try:
        if len(row) < 6:
            return None, None
        
        # Parse timestamp
        timestamp_str = row[0].strip()
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning(f"Invalid timestamp format: {timestamp_str}")
            return None, None
        
        # Parse rates
        try:
            usd_buy = float(row[1].strip()) if row[1].strip() else None
            usd_sell = float(row[2].strip()) if row[2].strip() else None
            eur_buy = float(row[3].strip()) if row[3].strip() else None
            eur_sell = float(row[4].strip()) if row[4].strip() else None
            pln_cross = float(row[5].strip()) if row[5].strip() else None
        except (ValueError, IndexError) as e:
            logger.warning(f"Invalid rate values in row: {e}")
            return None, None
        
        # Create rate records (Monobank format)
        rates = []
        
        # USD/UAH rate
        if usd_buy is not None and usd_sell is not None:
            rates.append({
                'currencyCodeA': 840,  # USD
                'currencyCodeB': 980,  # UAH
                'rateBuy': usd_buy,
                'rateSell': usd_sell,
                'rateCross': None
            })
        
        # EUR/UAH rate
        if eur_buy is not None and eur_sell is not None:
            rates.append({
                'currencyCodeA': 978,  # EUR
                'currencyCodeB': 980,  # UAH
                'rateBuy': eur_buy,
                'rateSell': eur_sell,
                'rateCross': None
            })
        
        # PLN/UAH rate
        if pln_cross is not None:
            rates.append({
                'currencyCodeA': 985,  # PLN
                'currencyCodeB': 980,  # UAH
                'rateBuy': None,
                'rateSell': None,
                'rateCross': pln_cross
            })
        
        return timestamp, rates
        
    except Exception as e:
        logger.warning(f"Error parsing CSV row: {e}")
        return None, None


def migrate_csv_to_db(csv_file, db_file, dry_run=False, verbose=False):
    """
    Migrate CSV data to SQLite database.
    
    Args:
        csv_file: Path to CSV file
        db_file: Path to SQLite database file
        dry_run: If True, validate without inserting
        verbose: If True, show detailed output
    
    Returns:
        Dictionary with migration statistics
    """
    if verbose:
        logger.setLevel(logging.DEBUG)
    
    stats = {
        'total_rows': 0,
        'valid_rows': 0,
        'invalid_rows': 0,
        'migrated_rates': 0,
        'skipped_duplicates': 0,
        'errors': []
    }
    
    # Check if CSV file exists
    if not os.path.exists(csv_file):
        logger.error(f"CSV file not found: {csv_file}")
        return stats
    
    # Initialize database (unless dry run)
    db = None
    if not dry_run:
        try:
            db = ExchangeRateDatabase(db_file)
            db.connect()
            logger.info(f"Connected to database: {db_file}")
        except Exception as e:
            logger.error(f"Error connecting to database: {e}")
            return stats
    
    # Read and process CSV file
    logger.info(f"Reading CSV file: {csv_file}")
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            
            for row_num, row in enumerate(reader, start=1):
                stats['total_rows'] += 1
                
                # Parse CSV row
                timestamp, rates = parse_csv_row(row)
                
                if timestamp is None or not rates:
                    stats['invalid_rows'] += 1
                    stats['errors'].append(f"Row {row_num}: Invalid format")
                    if verbose:
                        logger.debug(f"Skipping invalid row {row_num}: {row}")
                    continue
                
                stats['valid_rows'] += 1
                
                if verbose:
                    logger.debug(f"Row {row_num}: {timestamp} - {len(rates)} rates")
                
                # Insert rates into database
                if not dry_run and db:
                    try:
                        # Track counts before insert
                        before_count = stats['migrated_rates']
                        
                        db.insert_exchange_rates(rates, 'monobank', timestamp)
                        
                        # Calculate inserted vs skipped
                        stats['migrated_rates'] += len(rates)
                        
                    except Exception as e:
                        logger.error(f"Error inserting row {row_num}: {e}")
                        stats['errors'].append(f"Row {row_num}: {str(e)}")
                else:
                    # In dry-run mode, just count what would be migrated
                    stats['migrated_rates'] += len(rates)
    
    except Exception as e:
        logger.error(f"Error reading CSV file: {e}")
        stats['errors'].append(f"File read error: {str(e)}")
    
    # Close database connection
    if db:
        db.close()
    
    return stats


def main():
    """Main entry point for the migration script."""
    parser = argparse.ArgumentParser(
        description='Migrate exchange rate data from CSV to SQLite database'
    )
    parser.add_argument(
        '--csv-file',
        type=str,
        default='exchange_rates.csv',
        help='Path to CSV file (default: exchange_rates.csv)'
    )
    parser.add_argument(
        '--db-file',
        type=str,
        default='data/exchange_rates.db',
        help='Path to SQLite database file (default: data/exchange_rates.db)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate CSV without inserting into database'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed output'
    )
    
    args = parser.parse_args()
    
    # Print configuration
    logger.info("=" * 60)
    logger.info("CSV to SQLite Migration Script")
    logger.info("=" * 60)
    logger.info(f"CSV File: {args.csv_file}")
    logger.info(f"Database File: {args.db_file}")
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info(f"Verbose: {args.verbose}")
    logger.info("=" * 60)
    
    # Run migration
    stats = migrate_csv_to_db(
        args.csv_file,
        args.db_file,
        dry_run=args.dry_run,
        verbose=args.verbose
    )
    
    # Print results
    logger.info("=" * 60)
    logger.info("Migration Results")
    logger.info("=" * 60)
    logger.info(f"Total rows processed: {stats['total_rows']}")
    logger.info(f"Valid rows: {stats['valid_rows']}")
    logger.info(f"Invalid rows: {stats['invalid_rows']}")
    logger.info(f"Exchange rates migrated: {stats['migrated_rates']}")
    
    if stats['errors']:
        logger.warning(f"Errors encountered: {len(stats['errors'])}")
        if args.verbose:
            for error in stats['errors'][:10]:  # Show first 10 errors
                logger.warning(f"  - {error}")
            if len(stats['errors']) > 10:
                logger.warning(f"  ... and {len(stats['errors']) - 10} more errors")
    
    logger.info("=" * 60)
    
    if args.dry_run:
        logger.info("DRY RUN completed - no data was written to database")
    else:
        logger.info("Migration completed successfully")
    
    return 0 if stats['valid_rows'] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
