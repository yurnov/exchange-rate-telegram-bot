#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SQLite database module for storing exchange rate data.

This module provides database operations for storing ALL exchange rates
from Monobank and NBU APIs with timestamp-based deduplication.
"""

import logging
import sqlite3
import os
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class ExchangeRateDatabase:
    """SQLite database handler for exchange rate storage."""

    def __init__(self, db_path: str = "data/exchange_rates.db"):
        """
        Initialize database connection and create schema.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = None

        # Ensure data directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logger.info(f"Created data directory: {db_dir}")

        self._connect()
        self._initialize_schema()

    def _connect(self):
        """Establish database connection with optimized settings."""
        try:
            # Note: check_same_thread=False is safe here because:
            # 1. The bot runs in a single-threaded event loop (telegram bot)
            # 2. All database operations happen in the same thread (scheduled task)
            # 3. SQLite WAL mode provides process-level concurrency if needed
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # Enable WAL mode for better concurrent access
            self.conn.execute("PRAGMA journal_mode=WAL")
            # Enable foreign key constraints
            self.conn.execute("PRAGMA foreign_keys=ON")
            logger.info(f"Connected to database: {self.db_path}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Error connecting to database: {str(e)}")
            raise

    def _initialize_schema(self):
        """Create database schema if it doesn't exist."""
        try:
            cursor = self.conn.cursor()

            # Create currencies reference table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS currencies (
                    code INTEGER PRIMARY KEY,
                    alpha_code TEXT NOT NULL,
                    name TEXT,
                    symbol TEXT
                )
            """
            )

            # Insert common currency codes from Monobank/NBU APIs
            currencies = [
                (840, 'USD', 'US Dollar', '$'),
                (978, 'EUR', 'Euro', '€'),
                (980, 'UAH', 'Ukrainian Hryvnia', '₴'),
                (985, 'PLN', 'Polish Zloty', 'zł'),
                (826, 'GBP', 'British Pound', '£'),
                (392, 'JPY', 'Japanese Yen', '¥'),
                (756, 'CHF', 'Swiss Franc', 'CHF'),
                (156, 'CNY', 'Chinese Yuan', '¥'),
                (784, 'AED', 'UAE Dirham', 'AED'),
                (36, 'AUD', 'Australian Dollar', 'A$'),
                (124, 'CAD', 'Canadian Dollar', 'C$'),
                (203, 'CZK', 'Czech Koruna', 'Kč'),
                (208, 'DKK', 'Danish Krone', 'kr'),
                (348, 'HUF', 'Hungarian Forint', 'Ft'),
                (376, 'ILS', 'Israeli Shekel', '₪'),
                (356, 'INR', 'Indian Rupee', '₹'),
                (578, 'NOK', 'Norwegian Krone', 'kr'),
                (752, 'SEK', 'Swedish Krona', 'kr'),
                (702, 'SGD', 'Singapore Dollar', 'S$'),
                (949, 'TRY', 'Turkish Lira', '₺'),
                (946, 'RON', 'Romanian Leu', 'lei'),
                (975, 'BGN', 'Bulgarian Lev', 'лв'),
                (981, 'GEL', 'Georgian Lari', '₾'),
                (498, 'MDL', 'Moldovan Leu', 'L'),
                (933, 'BYN', 'Belarusian Ruble', 'Br'),
                (398, 'KZT', 'Kazakhstani Tenge', '₸'),
                (944, 'AZN', 'Azerbaijani Manat', '₼'),
                (682, 'SAR', 'Saudi Riyal', '﷼'),
                (634, 'QAR', 'Qatari Riyal', '﷼'),
                (414, 'KWD', 'Kuwaiti Dinar', 'KD'),
                (48, 'BHD', 'Bahraini Dinar', 'BD'),
                (512, 'OMR', 'Omani Rial', '﷼'),
                (400, 'JOD', 'Jordanian Dinar', 'JD'),
                (818, 'EGP', 'Egyptian Pound', '£'),
                (788, 'TND', 'Tunisian Dinar', 'DT'),
                (504, 'MAD', 'Moroccan Dirham', 'MAD'),
                (710, 'ZAR', 'South African Rand', 'R'),
                (986, 'BRL', 'Brazilian Real', 'R$'),
                (484, 'MXN', 'Mexican Peso', '$'),
                (32, 'ARS', 'Argentine Peso', '$'),
                (152, 'CLP', 'Chilean Peso', '$'),
                (170, 'COP', 'Colombian Peso', '$'),
                (604, 'PEN', 'Peruvian Sol', 'S/'),
                (858, 'UYU', 'Uruguayan Peso', '$U'),
                (764, 'THB', 'Thai Baht', '฿'),
                (458, 'MYR', 'Malaysian Ringgit', 'RM'),
                (360, 'IDR', 'Indonesian Rupiah', 'Rp'),
                (608, 'PHP', 'Philippine Peso', '₱'),
                (704, 'VND', 'Vietnamese Dong', '₫'),
                (410, 'KRW', 'South Korean Won', '₩'),
                (344, 'HKD', 'Hong Kong Dollar', 'HK$'),
                (901, 'TWD', 'Taiwan Dollar', 'NT$'),
                (554, 'NZD', 'New Zealand Dollar', 'NZ$'),
                (941, 'RSD', 'Serbian Dinar', 'RSD'),
                (807, 'MKD', 'Macedonian Denar', 'ден'),
                (191, 'HRK', 'Croatian Kuna', 'kn'),
                (144, 'LKR', 'Sri Lankan Rupee', 'Rs'),
                (586, 'PKR', 'Pakistani Rupee', 'Rs'),
                (50, 'BDT', 'Bangladeshi Taka', '৳'),
                (404, 'KES', 'Kenyan Shilling', 'KSh'),
                (566, 'NGN', 'Nigerian Naira', '₦'),
                (834, 'TZS', 'Tanzanian Shilling', 'TSh'),
                (800, 'UGX', 'Ugandan Shilling', 'USh'),
                (690, 'SCR', 'Seychellois Rupee', 'SR'),
                (480, 'MUR', 'Mauritian Rupee', 'Rs'),
                (72, 'BWP', 'Botswana Pula', 'P'),
                (516, 'NAD', 'Namibian Dollar', 'N$'),
                (968, 'SRD', 'Surinamese Dollar', '$'),
                (417, 'KGS', 'Kyrgyzstani Som', 'с'),
                (860, 'UZS', 'Uzbekistani Som', "so'm"),
                (972, 'TJS', 'Tajikistani Somoni', 'ЅМ'),
                (51, 'AMD', 'Armenian Dram', '֏'),
                (971, 'AFN', 'Afghan Afghani', '؋'),
                (368, 'IQD', 'Iraqi Dinar', 'IQD'),
                (422, 'LBP', 'Lebanese Pound', '£'),
                (434, 'LYD', 'Libyan Dinar', 'LD'),
                (886, 'YER', 'Yemeni Rial', '﷼'),
                (706, 'SOS', 'Somali Shilling', 'Sh'),
                (938, 'SDG', 'Sudanese Pound', 'SDG'),
                (230, 'ETB', 'Ethiopian Birr', 'Br'),
                (262, 'DJF', 'Djiboutian Franc', 'Fdj'),
                (108, 'BIF', 'Burundian Franc', 'FBu'),
                (976, 'CDF', 'Congolese Franc', 'FC'),
                (270, 'GMD', 'Gambian Dalasi', 'D'),
                (324, 'GNF', 'Guinean Franc', 'FG'),
                (936, 'GHS', 'Ghanaian Cedi', 'GH₵'),
                (943, 'MZN', 'Mozambican Metical', 'MT'),
                (454, 'MWK', 'Malawian Kwacha', 'MK'),
                (748, 'SZL', 'Swazi Lilangeni', 'L'),
                (694, 'SLL', 'Sierra Leonean Leone', 'Le'),
                (950, 'XAF', 'Central African CFA Franc', 'FCFA'),
                (952, 'XOF', 'West African CFA Franc', 'CFA'),
                (969, 'MGA', 'Malagasy Ariary', 'Ar'),
                (496, 'MNT', 'Mongolian Tugrik', '₮'),
                (116, 'KHR', 'Cambodian Riel', '៛'),
                (418, 'LAK', 'Lao Kip', '₭'),
                (524, 'NPR', 'Nepalese Rupee', 'Rs'),
                (96, 'BND', 'Brunei Dollar', 'B$'),
                (352, 'ISK', 'Icelandic Króna', 'kr'),
                (68, 'BOB', 'Bolivian Boliviano', 'Bs'),
                (600, 'PYG', 'Paraguayan Guarani', '₲'),
                (188, 'CRC', 'Costa Rican Colon', '₡'),
                (558, 'NIO', 'Nicaraguan Cordoba', 'C$'),
                (192, 'CUP', 'Cuban Peso', '$'),
                (973, 'AOA', 'Angolan Kwanza', 'Kz'),
                (8, 'ALL', 'Albanian Lek', 'L'),
                (12, 'DZD', 'Algerian Dinar', 'DA'),
            ]

            cursor.executemany(
                "INSERT OR IGNORE INTO currencies (code, alpha_code, name, symbol) VALUES (?, ?, ?, ?)", currencies
            )

            # Create main exchange rates table with dual timestamps
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS exchange_rates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    api_timestamp INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    currency_code_a INTEGER NOT NULL,
                    currency_code_b INTEGER NOT NULL,
                    rate_buy REAL,
                    rate_sell REAL,
                    rate_cross REAL,
                    UNIQUE(source, currency_code_a, currency_code_b, api_timestamp),
                    FOREIGN KEY (currency_code_a) REFERENCES currencies(code),
                    FOREIGN KEY (currency_code_b) REFERENCES currencies(code)
                )
            """
            )

            # Create indexes for efficient queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rates_timestamp ON exchange_rates(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rates_api_timestamp ON exchange_rates(api_timestamp)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rates_currency_pair ON exchange_rates(currency_code_a, currency_code_b, api_timestamp)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rates_source ON exchange_rates(source, api_timestamp)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rates_currency_a ON exchange_rates(currency_code_a, api_timestamp)"
            )

            self.conn.commit()
            logger.info("Database schema initialized successfully")

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Error initializing database schema: {str(e)}")
            raise

    def _ensure_currency_codes_exist(self, currency_codes: set):
        """
        Ensure currency codes exist in the currencies table.
        Auto-insert any missing codes with placeholder data.

        Args:
            currency_codes: Set of currency code integers to check
        """
        try:
            cursor = self.conn.cursor()

            for code in currency_codes:
                # Insert currency code if it doesn't exist
                # Use INSERT OR IGNORE to handle race conditions
                cursor.execute(
                    "INSERT OR IGNORE INTO currencies (code, alpha_code, name, symbol) VALUES (?, ?, ?, ?)",
                    (code, f"CUR{code}", f"Currency {code}", ""),
                )

            self.conn.commit()

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning(f"Error ensuring currency codes exist: {str(e)}")
            self.conn.rollback()

    def insert_exchange_rates(
        self, rates: List[Tuple[str, int, str, int, int, Optional[float], Optional[float], Optional[float]]]
    ) -> Tuple[int, int]:
        """
        Insert exchange rates into database using INSERT OR IGNORE for deduplication.

        Args:
            rates: List of tuples (timestamp, api_timestamp, source, currency_code_a,
                   currency_code_b, rate_buy, rate_sell, rate_cross)

        Returns:
            Tuple of (inserted_count, ignored_count)
        """
        if not rates:
            return 0, 0

        try:
            # Extract all unique currency codes from the rates
            currency_codes = set()
            for rate in rates:
                currency_codes.add(rate[3])  # currency_code_a
                currency_codes.add(rate[4])  # currency_code_b

            # Ensure all currency codes exist in the currencies table
            self._ensure_currency_codes_exist(currency_codes)

            cursor = self.conn.cursor()

            # Use INSERT OR IGNORE - SQLite will automatically skip duplicates
            # based on UNIQUE constraint
            cursor.executemany(
                """
                INSERT OR IGNORE INTO exchange_rates
                (timestamp, api_timestamp, source, currency_code_a, currency_code_b,
                 rate_buy, rate_sell, rate_cross)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                rates,
            )

            inserted_count = cursor.rowcount
            ignored_count = len(rates) - inserted_count

            self.conn.commit()

            return inserted_count, ignored_count

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Error inserting exchange rates: {str(e)}")
            self.conn.rollback()
            return 0, len(rates)

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
