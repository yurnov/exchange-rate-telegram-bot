#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SQLite database module for storing exchange rate historical data.
Stores ALL exchange rates from APIs (Monobank and NBU) for comprehensive analysis.

Thread Safety Note:
This module uses check_same_thread=False for SQLite connection to allow access
from the scheduler thread. The bot architecture uses a single writer thread
(scheduler) for all database operations, making this safe for this use case.
For multi-threaded write scenarios, consider using a connection pool or 
thread-local connections.
"""

import sqlite3
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import os
import threading

logger = logging.getLogger(__name__)


class ExchangeRateDatabase:
    """
    SQLite database manager for exchange rates.
    
    Thread Safety:
    - Designed for single-writer, multiple-reader pattern
    - All write operations should be called from the same thread (scheduler)
    - Uses WAL mode for better concurrent read access
    """

    def __init__(self, db_path: str = "data/exchange_rates.db"):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()  # Lock for thread-safe operations
        self._ensure_data_directory()
        
    def _ensure_data_directory(self):
        """Create data directory if it doesn't exist."""
        data_dir = os.path.dirname(self.db_path)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
            logger.info(f"Created data directory: {data_dir}")
    
    def connect(self):
        """
        Establish database connection and initialize schema.
        
        Note: Uses check_same_thread=False to allow scheduler thread access.
        This is safe for single-writer scenarios like this bot.
        """
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # Enable foreign key constraints
            self.conn.execute("PRAGMA foreign_keys = ON")
            # Enable WAL mode for better concurrent access
            self.conn.execute("PRAGMA journal_mode = WAL")
            logger.info(f"Connected to database: {self.db_path}")
            self._initialize_schema()
        except sqlite3.Error as e:
            logger.error(f"Error connecting to database: {e}")
            raise
    
    def _initialize_schema(self):
        """Create database tables if they don't exist."""
        try:
            cursor = self.conn.cursor()
            
            # Create currencies reference table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS currencies (
                    code INTEGER PRIMARY KEY,
                    alpha_code TEXT NOT NULL,
                    name TEXT,
                    symbol TEXT
                )
            """)
            
            # Create main exchange rates table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS exchange_rates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    source TEXT NOT NULL,
                    currency_code_a INTEGER NOT NULL,
                    currency_code_b INTEGER NOT NULL,
                    rate_buy REAL,
                    rate_sell REAL,
                    rate_cross REAL,
                    UNIQUE(timestamp, source, currency_code_a, currency_code_b)
                )
            """)
            
            # Create indexes for efficient queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_rates_timestamp 
                ON exchange_rates(timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_rates_currency_pair 
                ON exchange_rates(currency_code_a, currency_code_b, timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_rates_source 
                ON exchange_rates(source, timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_rates_currency_a 
                ON exchange_rates(currency_code_a, timestamp)
            """)
            
            self.conn.commit()
            logger.info("Database schema initialized successfully")
            
            # Populate currencies table with common currencies
            self._populate_currencies()
            
        except sqlite3.Error as e:
            logger.error(f"Error initializing database schema: {e}")
            raise
    
    def _populate_currencies(self):
        """Populate currencies table with ISO 4217 currency codes."""
        currencies = [
            (840, 'USD', 'US Dollar', '$'),
            (978, 'EUR', 'Euro', '€'),
            (980, 'UAH', 'Ukrainian Hryvnia', '₴'),
            (985, 'PLN', 'Polish Zloty', 'zł'),
            (826, 'GBP', 'British Pound', '£'),
            (392, 'JPY', 'Japanese Yen', '¥'),
            (756, 'CHF', 'Swiss Franc', 'CHF'),
            (156, 'CNY', 'Chinese Yuan', '¥'),
            (784, 'AED', 'UAE Dirham', 'د.إ'),
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
            (414, 'KWD', 'Kuwaiti Dinar', 'د.ك'),
            (48, 'BHD', 'Bahraini Dinar', '.د.ب'),
            (512, 'OMR', 'Omani Rial', '﷼'),
            (400, 'JOD', 'Jordanian Dinar', 'د.ا'),
            (818, 'EGP', 'Egyptian Pound', '£'),
            (788, 'TND', 'Tunisian Dinar', 'د.ت'),
            (504, 'MAD', 'Moroccan Dirham', 'د.م.'),
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
            (941, 'RSD', 'Serbian Dinar', 'дин'),
            (807, 'MKD', 'Macedonian Denar', 'ден'),
            (191, 'HRK', 'Croatian Kuna', 'kn'),
            (144, 'LKR', 'Sri Lankan Rupee', 'Rs'),
            (586, 'PKR', 'Pakistani Rupee', '₨'),
            (50, 'BDT', 'Bangladeshi Taka', '৳'),
            (404, 'KES', 'Kenyan Shilling', 'KSh'),
            (566, 'NGN', 'Nigerian Naira', '₦'),
            (834, 'TZS', 'Tanzanian Shilling', 'TSh'),
            (800, 'UGX', 'Ugandan Shilling', 'USh'),
            (690, 'SCR', 'Seychellois Rupee', '₨'),
            (480, 'MUR', 'Mauritian Rupee', '₨'),
            (72, 'BWP', 'Botswana Pula', 'P'),
            (516, 'NAD', 'Namibian Dollar', 'N$'),
            (968, 'SRD', 'Surinamese Dollar', '$'),
            (417, 'KGS', 'Kyrgyzstani Som', 'с'),
            (860, 'UZS', 'Uzbekistani Som', "so'm"),
            (972, 'TJS', 'Tajikistani Somoni', 'ЅМ'),
            (51, 'AMD', 'Armenian Dram', '֏'),
            (971, 'AFN', 'Afghan Afghani', '؋'),
            (368, 'IQD', 'Iraqi Dinar', 'ع.د'),
            (422, 'LBP', 'Lebanese Pound', 'ل.ل'),
            (434, 'LYD', 'Libyan Dinar', 'ل.د'),
            (886, 'YER', 'Yemeni Rial', '﷼'),
            (706, 'SOS', 'Somali Shilling', 'Sh'),
            (938, 'SDG', 'Sudanese Pound', '£'),
            (230, 'ETB', 'Ethiopian Birr', 'Br'),
            (262, 'DJF', 'Djiboutian Franc', 'Fdj'),
            (108, 'BIF', 'Burundian Franc', 'FBu'),
            (976, 'CDF', 'Congolese Franc', 'FC'),
            (270, 'GMD', 'Gambian Dalasi', 'D'),
            (324, 'GNF', 'Guinean Franc', 'FG'),
            (936, 'GHS', 'Ghanaian Cedi', '₵'),
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
            (524, 'NPR', 'Nepalese Rupee', '₨'),
            (96, 'BND', 'Brunei Dollar', 'B$'),
            (352, 'ISK', 'Icelandic Krona', 'kr'),
            (68, 'BOB', 'Bolivian Boliviano', 'Bs.'),
            (600, 'PYG', 'Paraguayan Guarani', '₲'),
            (188, 'CRC', 'Costa Rican Colon', '₡'),
            (558, 'NIO', 'Nicaraguan Cordoba', 'C$'),
            (192, 'CUP', 'Cuban Peso', '$'),
            (973, 'AOA', 'Angolan Kwanza', 'Kz'),
            (8, 'ALL', 'Albanian Lek', 'L'),
            (12, 'DZD', 'Algerian Dinar', 'د.ج'),
        ]
        
        try:
            cursor = self.conn.cursor()
            cursor.executemany(
                "INSERT OR IGNORE INTO currencies (code, alpha_code, name, symbol) VALUES (?, ?, ?, ?)",
                currencies
            )
            self.conn.commit()
            logger.debug(f"Populated currencies table with {len(currencies)} entries")
        except sqlite3.Error as e:
            logger.error(f"Error populating currencies table: {e}")
    
    def insert_exchange_rates(self, rates: List[Dict[str, Any]], source: str, timestamp: Optional[datetime] = None):
        """
        Insert exchange rates from API response.
        Thread-safe operation using lock.
        
        Args:
            rates: List of rate dictionaries from API
            source: Data source ('monobank' or 'nbu')
            timestamp: Optional timestamp (defaults to current time)
        """
        if not self.conn:
            logger.error("Database connection not established")
            return
        
        if timestamp is None:
            timestamp = datetime.now()
        
        # Format timestamp as ISO 8601 string
        timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        inserted_count = 0
        skipped_count = 0
        
        # Use lock for thread-safe database access
        with self._lock:
            try:
                cursor = self.conn.cursor()
                
                for rate_data in rates:
                    try:
                        if source == 'monobank':
                            # Monobank API format
                            currency_code_a = rate_data.get('currencyCodeA')
                            currency_code_b = rate_data.get('currencyCodeB')
                            rate_buy = rate_data.get('rateBuy')
                            rate_sell = rate_data.get('rateSell')
                            rate_cross = rate_data.get('rateCross')
                        elif source == 'nbu':
                            # NBU API format - need to adapt
                            currency_code_a = rate_data.get('r030')  # NBU numeric code
                            currency_code_b = 980  # UAH
                            rate_buy = None
                            rate_sell = None
                            rate_cross = rate_data.get('rate')
                        else:
                            logger.warning(f"Unknown source: {source}")
                            continue
                        
                        # Insert or ignore if duplicate
                        cursor.execute("""
                            INSERT OR IGNORE INTO exchange_rates 
                            (timestamp, source, currency_code_a, currency_code_b, rate_buy, rate_sell, rate_cross)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (timestamp_str, source, currency_code_a, currency_code_b, rate_buy, rate_sell, rate_cross))
                        
                        if cursor.rowcount > 0:
                            inserted_count += 1
                        else:
                            skipped_count += 1
                            
                    except (KeyError, TypeError) as e:
                        logger.warning(f"Error processing rate data: {e}")
                        continue
                
                self.conn.commit()
                logger.info(f"Inserted {inserted_count} rates from {source}, skipped {skipped_count} duplicates")
                
            except sqlite3.Error as e:
                logger.error(f"Error inserting exchange rates: {e}")
                self.conn.rollback()
    
    def get_latest_rates(self, currency_code_a: Optional[int] = None, 
                        currency_code_b: Optional[int] = None,
                        source: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get latest exchange rates with optional filtering.
        
        Args:
            currency_code_a: Filter by source currency code
            currency_code_b: Filter by target currency code
            source: Filter by data source
            
        Returns:
            List of rate dictionaries
        """
        if not self.conn:
            logger.error("Database connection not established")
            return []
        
        try:
            cursor = self.conn.cursor()
            
            query = """
                SELECT e.timestamp, e.source, e.currency_code_a, e.currency_code_b,
                       e.rate_buy, e.rate_sell, e.rate_cross,
                       c1.alpha_code as from_currency, c2.alpha_code as to_currency
                FROM exchange_rates e
                LEFT JOIN currencies c1 ON e.currency_code_a = c1.code
                LEFT JOIN currencies c2 ON e.currency_code_b = c2.code
                WHERE 1=1
            """
            params = []
            
            if currency_code_a:
                query += " AND e.currency_code_a = ?"
                params.append(currency_code_a)
            
            if currency_code_b:
                query += " AND e.currency_code_b = ?"
                params.append(currency_code_b)
            
            if source:
                query += " AND e.source = ?"
                params.append(source)
            
            query += " ORDER BY e.timestamp DESC LIMIT 100"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    'timestamp': row[0],
                    'source': row[1],
                    'currency_code_a': row[2],
                    'currency_code_b': row[3],
                    'rate_buy': row[4],
                    'rate_sell': row[5],
                    'rate_cross': row[6],
                    'from_currency': row[7],
                    'to_currency': row[8],
                })
            
            return results
            
        except sqlite3.Error as e:
            logger.error(f"Error getting latest rates: {e}")
            return []
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
