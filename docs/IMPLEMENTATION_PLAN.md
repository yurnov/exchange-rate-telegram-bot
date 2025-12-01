# Implementation Plan: Time-Series Database for Historical Exchange Rate Data

## Issue #18: Analysis and Planning Document

This document provides a detailed analysis and implementation plan for issue #18 (Use time-series database to store historical data), including updated requirements for subtasks #19, #20, and #21.

---

## 1. Executive Summary

The goal is to replace/extend the current CSV-based logging with a time-series database to store historical exchange rate data, enabling better data management, querying, and extension to additional currencies.

### Current State
- Exchange rates are logged to a CSV file when `LOG_RATE=True`
- CSV format: `Date Time, USD Buy Rate, USD Sell Rate, EUR Buy Rate, EUR Sell Rate, PLN Exchange Rate`
- Data is appended every `PULL_INTERVAL` seconds (default: 300s / 5 min)
- No database infrastructure exists
- **Important**: Monobank API provides individual `date` timestamps (Unix time) for each currency pair, with update frequencies varying significantly between pairs

### Requirements
- Store exchange rate data with 5-minute granularity
- **Store ALL exchange rates available from APIs** (not just USD, EUR, PLN)
- Support data storage for multiple years (estimated ~8-10 million records over 5 years)
- Low resource consumption (memory and CPU)
- Maintain backward compatibility with CSV logging
- Support migration from existing CSV data
- Use Docker Compose for service orchestration
- **Enable charting and trend analysis** through SQL queries and visualization tools
- **Utilize per-pair timestamps from API** to avoid storing redundant unchanged rates

---

## 1.1 Critical API Discovery: Per-Pair Timestamps

**Issue Context**: During initial planning (PR #29), the implementation plan didn't account for a critical feature of the Monobank API: **each currency pair has its own `date` timestamp** (Unix time format) indicating when that specific rate was last updated.

**Analysis of Actual API Response**:

Examining a real Monobank API response reveals significant timestamp variation:

```json
[
  {"currencyCodeA":840,"currencyCodeB":980,"date":1764576373,"rateBuy":42.14,"rateSell":42.5405},
  {"currencyCodeA":978,"currencyCodeB":980,"date":1764595273,"rateBuy":48.85,"rateSell":49.5},
  {"currencyCodeA":971,"currencyCodeB":980,"date":1764367205,"rateCross":0.6365},
  {"currencyCodeA":68,"currencyCodeB":980,"date":1764242111,"rateCross":6.2014}
]
```

In this single API response:
- USD/UAH (840/980): timestamp `1764576373` (recent)
- EUR/UAH (978/980): timestamp `1764595273` (18,900 seconds = ~5.25 hours newer than USD)
- AFN/UAH (971/980): timestamp `1764367205` (252,000 seconds = ~70 hours old!)
- BOB/UAH (68/980): timestamp `1764242111` (377,162 seconds = ~104.8 hours = ~4.4 days old!)

**Key Findings**:
1. **Timestamps vary widely**: From "just updated" to multiple days old in the same response
2. **Update frequency differs by pair**:
   - Major pairs (USD, EUR, PLN to UAH): Update every few minutes
   - Popular pairs: Update hourly
   - Exotic currencies: May update once per day or less
3. **Polling vs. actual updates**: If we poll every 5 minutes but a rate hasn't changed in days, we'd redundantly store the same rate 288 times per day

**Implementation Impact**:

This discovery fundamentally changes the storage strategy:

| Approach | Storage Behavior | 5-Year Estimate |
|----------|------------------|-----------------|
| **Naive** (ignore timestamps) | Store all ~100 pairs every 5 minutes | ~68.5M records, ~5-7 GB |
| **Optimized** (use per-pair timestamps) | Store only when rate actually changes | ~31.5M records, ~2.5-3.2 GB |

**Benefits of timestamp-aware storage**:
- **40-60% storage reduction**: Avoid redundant unchanged rates
- **Accurate historical data**: Timestamps reflect actual rate updates, not arbitrary polling times
- **Better analytics**: Queries show real rate changes, not polling artifacts
- **Efficient queries**: Smaller dataset, faster performance
- **Monitoring capability**: Can detect stale rates (pairs not updated in X hours)

This revised plan incorporates per-pair timestamp handling throughout the schema design, implementation phases, and query examples.

---

## 2. Database Selection Analysis

### Data Volume Estimation

The Monobank API returns approximately **100+ currency pairs** per request. To future-proof the database, we will store ALL available rates, not just the currently displayed currencies (USD, EUR, PLN).

#### Critical Discovery: Per-Pair Timestamps

**The Monobank API provides individual `date` timestamps for each currency pair**, not a single timestamp for the entire response. Analysis of actual API responses reveals:

- **Timestamp variation**: Currency pairs have different timestamps, with age differences ranging from seconds to multiple days
- **Update frequency patterns**:
  - **High-frequency pairs** (e.g., USD/UAH, EUR/UAH, PLN/UAH): Updated within minutes, reflecting active trading
  - **Low-frequency pairs** (e.g., exotic currencies): May be 1-4+ days old, indicating infrequent updates
  - Example: In a single API response, timestamps ranged from "just now" to 4.4 days old

#### Revised Storage Strategy

Instead of blindly storing all ~100 pairs every 5 minutes, we implement **timestamp-based change detection**:

1. **Store only when rate actually changes**: Check the API's `date` timestamp for each pair
2. **Track last-seen timestamp per pair**: Keep a cache of the most recent timestamp we've stored for each currency pair
3. **Insert only if timestamp is newer**: Only write to database if `API_timestamp > last_stored_timestamp`

This optimization significantly reduces redundant storage:
- **High-frequency pairs**: Still stored frequently (every 5-15 minutes)
- **Low-frequency pairs**: Stored only when actually updated (potentially once per day or less)
- **Estimated reduction**: 40-60% fewer database writes for infrequently-updated pairs

#### Updated Volume Estimation

- **Currency pairs per API call**: ~100 (Monobank) + ~30 (NBU) = ~130 rates
- **Polling interval**: 5 minutes (configurable, 15s-3600s)
- **Effective records per day** (with timestamp-based deduplication):
  - High-frequency pairs (~20): 288 intervals × 20 = ~5,760 records
  - Medium-frequency pairs (~40): ~60 intervals × 40 = ~2,400 records  
  - Low-frequency pairs (~40): ~12 intervals × 40 = ~480 records
  - NBU rates (~30): ~288 intervals × 30 = ~8,640 records (NBU updates once daily, but we poll every 5 min)
  - **Total per day**: ~17,280 records (vs. 37,440 without optimization)
- **Records per year**: ~6.3 million (vs. 13.7 million without optimization)
- **5-year storage**: ~31.5 million records (vs. 68.5 million)
- **Record size**: ~80-100 bytes per record
- **Total storage**: ~2.5-3.2 GB for 5 years (vs. ~5-7 GB without optimization)

**Note**: SQLite remains highly suitable for this volume. The timestamp-based approach also provides more accurate historical data, as it reflects the actual time each rate was updated by Monobank, not our polling time.

### Database Comparison

| Database | Min Memory | Docker Image Size | SQL Support | Best For |
|----------|-----------|-------------------|-------------|----------|
| **SQLite** | < 50 MB | Built into Python | Full SQL | Lightweight, embedded, low data volume |
| **InfluxDB** | 1-2 GB | ~300 MB | Flux/InfluxQL | Time-series native, larger scale |
| **QuestDB** | 8 GB | ~400 MB | SQL | High performance, larger scale |
| **ClickHouse** | 4+ GB | ~500 MB | SQL | Analytics, large scale OLAP |

### Recommendation: SQLite

**Rationale:**
1. **Extremely Low Resource Usage**: SQLite runs embedded within the Python application, requiring no separate container or process
2. **Suitable for Data Scale**: SQLite can handle databases up to 281 TB; our estimated ~7 GB for 5 years is well within capacity
3. **No Additional Infrastructure**: No separate database container needed
4. **Full SQL Support**: Standard SQL queries for data retrieval and analysis
5. **Python Native Support**: Built-in `sqlite3` module, no additional dependencies
6. **Simple Backup**: Single file database, easy to backup and migrate
7. **Backward Compatible**: Can run alongside existing CSV logging
8. **Analytics-Friendly**: Supports window functions, aggregations, and complex analytical queries for charting and trend analysis
9. **Grafana Compatible**: Can be connected to Grafana via SQLite datasource plugin for visualization dashboards
10. **Scalable**: Handles millions of records efficiently with proper indexing

**Trade-offs:**
- Not designed for high-concurrency writes (not a concern for this use case)
- No built-in time-series specific features (easily mitigated with proper schema design)
- Limited horizontal scaling (not needed for this use case)

### Alternative: InfluxDB (If Scalability Needed Later)
If the project grows to require:
- Multiple bots writing simultaneously
- Real-time analytics dashboards
- High-frequency data ingestion

Then InfluxDB would be a suitable upgrade path.

---

## 3. Implementation Architecture

### 3.1 Single Container Architecture (Recommended)

```
┌─────────────────────────────────────────┐
│          Docker Container               │
│  ┌───────────────────────────────────┐  │
│  │     exchange-rate-telegram-bot    │  │
│  │                                   │  │
│  │  ┌─────────┐    ┌─────────────┐  │  │
│  │  │  Bot    │───▶│  SQLite DB  │  │  │
│  │  │  Logic  │    │  (embedded) │  │  │
│  │  └─────────┘    └─────────────┘  │  │
│  │       │                          │  │
│  │       ▼                          │  │
│  │  ┌─────────────┐                 │  │
│  │  │  CSV File   │ (optional)      │  │
│  │  │  (legacy)   │                 │  │
│  │  └─────────────┘                 │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
         │              │
         ▼              ▼
   [Volume Mount]  [Volume Mount]
   exchange_rates.db  exchange_rates.csv
```

### 3.2 Docker Compose Stack (Future Extensibility)

While SQLite doesn't require a separate container, Docker Compose is still valuable for:
- Defining volume mounts
- Environment variable management
- Future extensibility (adding Grafana, backup services, etc.)

```yaml
version: '3.8'
services:
  bot:
    image: ghcr.io/yurnov/xratebot:latest
    env_file: .env
    volumes:
      - ./data:/bot/data
    restart: unless-stopped
```

---

## 4. Database Schema Design

### 4.1 Currency Codes Reference Table

Store ISO 4217 currency codes for lookup and display purposes:

```sql
CREATE TABLE IF NOT EXISTS currencies (
    code INTEGER PRIMARY KEY,  -- ISO 4217 numeric code
    alpha_code TEXT NOT NULL,  -- ISO 4217 alpha code (e.g., 'USD', 'EUR')
    name TEXT,                 -- Currency name (e.g., 'US Dollar')
    symbol TEXT                -- Currency symbol (e.g., '$', '€')
);

-- Common currencies from Monobank API
INSERT OR IGNORE INTO currencies (code, alpha_code, name) VALUES
    (840, 'USD', 'US Dollar'),
    (978, 'EUR', 'Euro'),
    (980, 'UAH', 'Ukrainian Hryvnia'),
    (985, 'PLN', 'Polish Zloty'),
    (826, 'GBP', 'British Pound'),
    (392, 'JPY', 'Japanese Yen'),
    (756, 'CHF', 'Swiss Franc'),
    (156, 'CNY', 'Chinese Yuan'),
    (784, 'AED', 'UAE Dirham'),
    (36, 'AUD', 'Australian Dollar'),
    (124, 'CAD', 'Canadian Dollar'),
    (203, 'CZK', 'Czech Koruna'),
    (208, 'DKK', 'Danish Krone'),
    (348, 'HUF', 'Hungarian Forint'),
    (376, 'ILS', 'Israeli Shekel'),
    (356, 'INR', 'Indian Rupee'),
    (578, 'NOK', 'Norwegian Krone'),
    (752, 'SEK', 'Swedish Krona'),
    (702, 'SGD', 'Singapore Dollar'),
    (949, 'TRY', 'Turkish Lira'),
    (946, 'RON', 'Romanian Leu'),
    (975, 'BGN', 'Bulgarian Lev'),
    (981, 'GEL', 'Georgian Lari'),
    (498, 'MDL', 'Moldovan Leu'),
    (933, 'BYN', 'Belarusian Ruble'),
    (398, 'KZT', 'Kazakhstani Tenge'),
    (944, 'AZN', 'Azerbaijani Manat'),
    (682, 'SAR', 'Saudi Riyal'),
    (634, 'QAR', 'Qatari Riyal'),
    (414, 'KWD', 'Kuwaiti Dinar'),
    (48, 'BHD', 'Bahraini Dinar'),
    (512, 'OMR', 'Omani Rial'),
    (400, 'JOD', 'Jordanian Dinar'),
    (818, 'EGP', 'Egyptian Pound'),
    (788, 'TND', 'Tunisian Dinar'),
    (504, 'MAD', 'Moroccan Dirham'),
    (710, 'ZAR', 'South African Rand'),
    (986, 'BRL', 'Brazilian Real'),
    (484, 'MXN', 'Mexican Peso'),
    (32, 'ARS', 'Argentine Peso'),
    (152, 'CLP', 'Chilean Peso'),
    (170, 'COP', 'Colombian Peso'),
    (604, 'PEN', 'Peruvian Sol'),
    (858, 'UYU', 'Uruguayan Peso'),
    (764, 'THB', 'Thai Baht'),
    (458, 'MYR', 'Malaysian Ringgit'),
    (360, 'IDR', 'Indonesian Rupiah'),
    (608, 'PHP', 'Philippine Peso'),
    (704, 'VND', 'Vietnamese Dong'),
    (410, 'KRW', 'South Korean Won'),
    (344, 'HKD', 'Hong Kong Dollar'),
    (901, 'TWD', 'Taiwan Dollar'),
    (554, 'NZD', 'New Zealand Dollar'),
    (941, 'RSD', 'Serbian Dinar'),
    (807, 'MKD', 'Macedonian Denar'),
    (191, 'HRK', 'Croatian Kuna'),
    (144, 'LKR', 'Sri Lankan Rupee'),
    (586, 'PKR', 'Pakistani Rupee'),
    (50, 'BDT', 'Bangladeshi Taka'),
    (404, 'KES', 'Kenyan Shilling'),
    (566, 'NGN', 'Nigerian Naira'),
    (834, 'TZS', 'Tanzanian Shilling'),
    (800, 'UGX', 'Ugandan Shilling'),
    (690, 'SCR', 'Seychellois Rupee'),
    (480, 'MUR', 'Mauritian Rupee'),
    (72, 'BWP', 'Botswana Pula'),
    (516, 'NAD', 'Namibian Dollar'),
    (968, 'SRD', 'Surinamese Dollar'),
    (417, 'KGS', 'Kyrgyzstani Som'),
    (860, 'UZS', 'Uzbekistani Som'),
    (972, 'TJS', 'Tajikistani Somoni'),
    (51, 'AMD', 'Armenian Dram'),
    (971, 'AFN', 'Afghan Afghani'),
    (368, 'IQD', 'Iraqi Dinar'),
    (422, 'LBP', 'Lebanese Pound'),
    (434, 'LYD', 'Libyan Dinar'),
    (886, 'YER', 'Yemeni Rial'),
    (706, 'SOS', 'Somali Shilling'),
    (938, 'SDG', 'Sudanese Pound'),
    (230, 'ETB', 'Ethiopian Birr'),
    (262, 'DJF', 'Djiboutian Franc'),
    (108, 'BIF', 'Burundian Franc'),
    (976, 'CDF', 'Congolese Franc'),
    (270, 'GMD', 'Gambian Dalasi'),
    (324, 'GNF', 'Guinean Franc'),
    (936, 'GHS', 'Ghanaian Cedi'),
    (943, 'MZN', 'Mozambican Metical'),
    (454, 'MWK', 'Malawian Kwacha'),
    (748, 'SZL', 'Swazi Lilangeni'),
    (694, 'SLL', 'Sierra Leonean Leone'),
    (950, 'XAF', 'Central African CFA Franc'),
    (952, 'XOF', 'West African CFA Franc'),
    (969, 'MGA', 'Malagasy Ariary'),
    (496, 'MNT', 'Mongolian Tugrik'),
    (116, 'KHR', 'Cambodian Riel'),
    (418, 'LAK', 'Lao Kip'),
    (524, 'NPR', 'Nepalese Rupee'),
    (96, 'BND', 'Brunei Dollar'),
    (352, 'ISK', 'Icelandic Krona'),
    (68, 'BOB', 'Bolivian Boliviano'),
    (600, 'PYG', 'Paraguayan Guarani'),
    (188, 'CRC', 'Costa Rican Colon'),
    (558, 'NIO', 'Nicaraguan Cordoba'),
    (192, 'CUP', 'Cuban Peso'),
    (973, 'AOA', 'Angolan Kwanza'),
    (8, 'ALL', 'Albanian Lek'),
    (12, 'DZD', 'Algerian Dinar');
```

### 4.2 Main Exchange Rates Table

```sql
CREATE TABLE IF NOT EXISTS exchange_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,        -- When we fetched this rate from the API (our polling time)
    api_timestamp INTEGER NOT NULL,     -- Unix timestamp from the API's 'date' field (when rate was actually updated)
    source TEXT NOT NULL,               -- 'monobank', 'nbu'
    currency_code_a INTEGER NOT NULL,   -- ISO 4217 numeric code (e.g., 840 for USD)
    currency_code_b INTEGER NOT NULL,   -- ISO 4217 numeric code (e.g., 980 for UAH)
    rate_buy REAL,                      -- Buy rate (NULL if not available)
    rate_sell REAL,                     -- Sell rate (NULL if not available)
    rate_cross REAL,                    -- Cross rate (NULL if not available)
    UNIQUE(source, currency_code_a, currency_code_b, api_timestamp),
    FOREIGN KEY (currency_code_a) REFERENCES currencies(code),
    FOREIGN KEY (currency_code_b) REFERENCES currencies(code)
);

-- Enable foreign key enforcement (must be run per connection in SQLite)
PRAGMA foreign_keys = ON;

CREATE INDEX idx_rates_timestamp ON exchange_rates(timestamp);
CREATE INDEX idx_rates_api_timestamp ON exchange_rates(api_timestamp);
CREATE INDEX idx_rates_currency_pair ON exchange_rates(currency_code_a, currency_code_b, api_timestamp);
CREATE INDEX idx_rates_source ON exchange_rates(source, api_timestamp);
CREATE INDEX idx_rates_currency_a ON exchange_rates(currency_code_a, api_timestamp);
```

**Key Design Decisions**:

1. **Dual Timestamp Approach**:
   - `timestamp`: When we polled the API (for debugging/audit purposes)
   - `api_timestamp`: When the rate was actually updated according to Monobank (the authoritative time)
   
2. **Unique Constraint**: `(source, currency_code_a, currency_code_b, api_timestamp)`
   - Prevents duplicate rates for the same currency pair with the same API timestamp
   - Allows idempotent inserts (re-running won't create duplicates)
   - Uses `api_timestamp` instead of our polling `timestamp` to accurately represent rate changes

3. **Change Detection Strategy**:
   - Before inserting, check if this `api_timestamp` already exists for this pair
   - Only insert if `api_timestamp` is newer than the last stored value
   - This automatically deduplicates unchanged rates across multiple API polls

**Note**: SQLite foreign key constraints are optional for this use case since:
1. Currency codes come directly from the API (trusted source)
2. New currency codes should be auto-inserted into the currencies table
3. The currencies table serves primarily as a lookup/display reference

### 4.3 Schema Benefits
- **Stores ALL rates**: Every currency pair from the API is captured
- **Efficient storage**: Single row per currency pair per unique rate update (buy, sell, cross in one row)
- **Timestamp accuracy**: Uses API-provided timestamps to reflect actual rate update times
- **Deduplication**: Automatic prevention of storing unchanged rates multiple times
- **Normalized**: Currency metadata stored separately for easy lookup
- **Flexible**: Supports any currency pair combination
- **ISO 4217 compliant**: Uses standard numeric currency codes
- **Queryable**: Efficient time-range and currency-specific queries
- **Unique Constraint**: Prevents duplicate entries based on actual rate update time (idempotent inserts)
- **Storage optimization**: 40-60% reduction in database size by avoiding redundant unchanged rates

### 4.4 Example Queries

```sql
-- Get latest USD/UAH rates (using currency codes and actual update times)
SELECT e.*, c1.alpha_code as from_currency, c2.alpha_code as to_currency,
       datetime(e.api_timestamp, 'unixepoch') as rate_updated_at
FROM exchange_rates e
JOIN currencies c1 ON e.currency_code_a = c1.code
JOIN currencies c2 ON e.currency_code_b = c2.code
WHERE e.currency_code_a = 840 AND e.currency_code_b = 980  -- USD to UAH
ORDER BY e.api_timestamp DESC LIMIT 10;

-- Get all available currency pairs with their latest update times
SELECT DISTINCT 
    c1.alpha_code as from_currency, 
    c2.alpha_code as to_currency,
    MAX(e.api_timestamp) as last_updated_unix,
    datetime(MAX(e.api_timestamp), 'unixepoch') as last_updated_datetime,
    COUNT(*) as data_points
FROM exchange_rates e
JOIN currencies c1 ON e.currency_code_a = c1.code
JOIN currencies c2 ON e.currency_code_b = c2.code
GROUP BY e.currency_code_a, e.currency_code_b
ORDER BY last_updated_unix DESC;

-- Get daily average EUR/UAH sell rate (using actual rate update times)
SELECT DATE(api_timestamp, 'unixepoch') as day, AVG(rate_sell) as avg_sell_rate
FROM exchange_rates 
WHERE currency_code_a = 978 AND currency_code_b = 980  -- EUR to UAH
GROUP BY DATE(api_timestamp, 'unixepoch')
ORDER BY day DESC;

-- Get rate history for past 24 hours (all currencies to UAH, using actual update times)
SELECT e.api_timestamp, 
       datetime(e.api_timestamp, 'unixepoch') as rate_updated_at,
       c.alpha_code as currency, 
       e.rate_buy, e.rate_sell, e.rate_cross
FROM exchange_rates e
JOIN currencies c ON e.currency_code_a = c.code
WHERE e.currency_code_b = 980  -- To UAH
  AND e.api_timestamp >= unixepoch('now', '-24 hours')
ORDER BY e.api_timestamp DESC, c.alpha_code;

-- Identify stale rates (not updated in last 24 hours) - useful for monitoring
SELECT c1.alpha_code as from_currency,
       c2.alpha_code as to_currency,
       MAX(e.api_timestamp) as last_update_unix,
       datetime(MAX(e.api_timestamp), 'unixepoch') as last_update_time,
       (unixepoch('now') - MAX(e.api_timestamp)) / 3600.0 as hours_since_update
FROM exchange_rates e
JOIN currencies c1 ON e.currency_code_a = c1.code
JOIN currencies c2 ON e.currency_code_b = c2.code
WHERE e.source = 'monobank'
GROUP BY e.currency_code_a, e.currency_code_b
HAVING hours_since_update > 24
ORDER BY hours_since_update DESC;

-- Compare our polling time vs API update time (for debugging)
SELECT currency_code_a, currency_code_b,
       datetime(timestamp) as our_poll_time,
       datetime(api_timestamp, 'unixepoch') as api_update_time,
       (unixepoch(timestamp) - api_timestamp) as lag_seconds
FROM exchange_rates
WHERE source = 'monobank'
ORDER BY timestamp DESC
LIMIT 20;
```

### 4.5 Analytics & Trend Analysis Queries

The schema supports various analytical queries for charting and trend analysis. All queries use `api_timestamp` for accurate representation of when rates actually changed:

```sql
-- Daily min/max/avg rates for USD/UAH (for candlestick-style charts)
-- Uses api_timestamp to reflect actual rate update times
SELECT 
    DATE(api_timestamp, 'unixepoch') as day,
    MIN(rate_sell) as min_rate,
    MAX(rate_sell) as max_rate,
    AVG(rate_sell) as avg_rate,
    (SELECT rate_sell FROM exchange_rates e2 
     WHERE DATE(e2.api_timestamp, 'unixepoch') = DATE(e1.api_timestamp, 'unixepoch')
     AND e2.currency_code_a = e1.currency_code_a 
     AND e2.currency_code_b = e1.currency_code_b 
     ORDER BY e2.api_timestamp ASC LIMIT 1) as open_rate,
    (SELECT rate_sell FROM exchange_rates e2 
     WHERE DATE(e2.api_timestamp, 'unixepoch') = DATE(e1.api_timestamp, 'unixepoch')
     AND e2.currency_code_a = e1.currency_code_a 
     AND e2.currency_code_b = e1.currency_code_b 
     ORDER BY e2.api_timestamp DESC LIMIT 1) as close_rate
FROM exchange_rates e1
WHERE currency_code_a = 840 AND currency_code_b = 980  -- USD/UAH
  AND source = 'monobank'
GROUP BY DATE(api_timestamp, 'unixepoch');

-- Weekly trend analysis for multiple currencies (using actual update times)
SELECT 
    strftime('%Y-W%W', datetime(api_timestamp, 'unixepoch')) as week,
    c.alpha_code as currency,
    AVG(rate_sell) as avg_rate,
    MIN(rate_sell) as min_rate,
    MAX(rate_sell) as max_rate,
    COUNT(*) as update_count
FROM exchange_rates e
JOIN currencies c ON e.currency_code_a = c.code
WHERE e.source = 'monobank' 
  AND e.currency_code_b = 980  -- To UAH
  AND e.rate_sell IS NOT NULL
GROUP BY week, e.currency_code_a
ORDER BY week DESC, currency;

-- Rate volatility (range) by currency over past 30 days
SELECT 
    c.alpha_code as currency,
    AVG(rate_sell) as avg_rate,
    MIN(rate_sell) as min_rate,
    MAX(rate_sell) as max_rate,
    MAX(rate_sell) - MIN(rate_sell) as range,
    COUNT(*) as data_points
FROM exchange_rates e
JOIN currencies c ON e.currency_code_a = c.code
WHERE e.api_timestamp >= unixepoch('now', '-30 days')
  AND e.currency_code_b = 980
  AND e.rate_sell IS NOT NULL
GROUP BY e.currency_code_a
ORDER BY range DESC;

-- Spread analysis (buy vs sell difference) for major currencies
SELECT 
    DATE(e.api_timestamp, 'unixepoch') as day,
    c.alpha_code as currency,
    AVG(e.rate_sell) as avg_sell,
    AVG(e.rate_buy) as avg_buy,
    AVG(e.rate_sell - e.rate_buy) as spread,
    AVG((e.rate_sell - e.rate_buy) / e.rate_buy * 100) as spread_percent
FROM exchange_rates e
JOIN currencies c ON e.currency_code_a = c.code
WHERE e.source = 'monobank' 
  AND e.currency_code_b = 980
  AND e.rate_buy IS NOT NULL 
  AND e.rate_sell IS NOT NULL
GROUP BY day, e.currency_code_a
ORDER BY day DESC, currency;

-- Compare Monobank vs NBU rates for USD
SELECT 
    DATE(api_timestamp, 'unixepoch') as day,
    AVG(CASE WHEN source = 'monobank' THEN rate_sell END) as monobank_sell,
    AVG(CASE WHEN source = 'nbu' THEN COALESCE(rate_cross, rate_sell) END) as nbu_official,
    AVG(CASE WHEN source = 'monobank' THEN rate_sell END) - 
    AVG(CASE WHEN source = 'nbu' THEN COALESCE(rate_cross, rate_sell) END) as difference
FROM exchange_rates
WHERE currency_code_a = 840 AND currency_code_b = 980
GROUP BY day
HAVING monobank_sell IS NOT NULL AND nbu_official IS NOT NULL
ORDER BY day DESC;

-- Moving average (7-day rolling average) for EUR/UAH
-- Note: This query uses actual rate update times, so window size may vary
SELECT 
    api_timestamp,
    datetime(api_timestamp, 'unixepoch') as update_time,
    rate_sell,
    AVG(rate_sell) OVER (
        ORDER BY api_timestamp 
        ROWS BETWEEN 2016 PRECEDING AND CURRENT ROW  -- Approximate 7 days of 5-min intervals
    ) as moving_avg_7d
FROM exchange_rates
WHERE source = 'monobank' 
  AND currency_code_a = 978 
  AND currency_code_b = 980
ORDER BY api_timestamp DESC;

-- Cross-currency analysis (EUR/USD rate)
SELECT 
    DATE(api_timestamp, 'unixepoch') as day,
    AVG(rate_buy) as avg_buy,
    AVG(rate_sell) as avg_sell,
    AVG((rate_buy + rate_sell) / 2) as mid_rate
FROM exchange_rates
WHERE currency_code_a = 978 AND currency_code_b = 840  -- EUR to USD
  AND source = 'monobank'
GROUP BY day
ORDER BY day DESC;

-- Most volatile currencies in the last 7 days
SELECT 
    c.alpha_code as currency,
    c.name as currency_name,
    MIN(e.rate_sell) as min_rate,
    MAX(e.rate_sell) as max_rate,
    (MAX(e.rate_sell) - MIN(e.rate_sell)) / AVG(e.rate_sell) * 100 as volatility_percent
FROM exchange_rates e
JOIN currencies c ON e.currency_code_a = c.code
WHERE e.api_timestamp >= unixepoch('now', '-7 days')
  AND e.currency_code_b = 980
  AND e.rate_sell IS NOT NULL
GROUP BY e.currency_code_a
HAVING COUNT(*) > 100  -- Ensure enough data points
ORDER BY volatility_percent DESC
LIMIT 10;

-- Update frequency analysis (how often each pair actually changes)
-- This helps understand which pairs are high vs low frequency
SELECT 
    c1.alpha_code || '/' || c2.alpha_code as pair,
    COUNT(*) as total_updates,
    MIN(api_timestamp) as first_seen,
    MAX(api_timestamp) as last_seen,
    datetime(MIN(api_timestamp), 'unixepoch') as first_seen_dt,
    datetime(MAX(api_timestamp), 'unixepoch') as last_seen_dt,
    (MAX(api_timestamp) - MIN(api_timestamp)) / 3600.0 as span_hours,
    COUNT(*) / ((MAX(api_timestamp) - MIN(api_timestamp)) / 3600.0) as updates_per_hour
FROM exchange_rates e
JOIN currencies c1 ON e.currency_code_a = c1.code
JOIN currencies c2 ON e.currency_code_b = c2.code
WHERE source = 'monobank'
  AND api_timestamp >= unixepoch('now', '-7 days')
GROUP BY e.currency_code_a, e.currency_code_b
HAVING span_hours > 1  -- Filter out very new pairs
ORDER BY updates_per_hour DESC;
```

---

## 5. Implementation Phases

### Phase 1: Database Infrastructure (Issue #20 - Updated)
**Priority: High | Effort: Low**

1. Create SQLite database module (`bot/database.py`)
   - Database initialization
   - Schema creation with dual timestamp fields (`timestamp` and `api_timestamp`)
   - Connection management
   - CRUD operations with timestamp-based change detection

2. Update Docker Compose configuration
   - Add volume mount for database file
   - Update `.env.example` with database settings

3. Add database configuration options
   - `DB_ENABLED` - Enable/disable database logging (default: False for backward compatibility)
   - `DB_PATH` - Path to SQLite database file

4. Implement timestamp-based deduplication logic
   - Cache last-seen `api_timestamp` per currency pair (in-memory)
   - Query database on startup to populate cache
   - Only insert rates when `api_timestamp` from API is newer than cached value

### Phase 2: Exchange Rate Storage (Issue #19 - Updated)
**Priority: High | Effort: Medium**

1. Update `get_exchange_rates()` function
   - Extract `date` field from each currency pair in Monobank API response
   - Implement timestamp-based change detection before inserting
   - Add database insertion only for rates with new `api_timestamp` values
   - Implement error handling for database operations
   - Ensure both Monobank and NBU rates are stored (NBU doesn't provide per-rate timestamps, so use polling time)

2. Maintain backward compatibility
   - CSV logging continues to work when `LOG_RATE=True`
   - Database logging works when `DB_ENABLED=True`
   - Both can be enabled simultaneously

3. Add data validation
   - Validate rates before insertion
   - Handle duplicate entries gracefully using UNIQUE constraint
   - Log statistics on how many rates were new vs. skipped (unchanged)

4. Optimize for efficiency
   - Batch insert all new rates in a single transaction
   - Use in-memory cache to track last-seen timestamps per pair
   - Minimize database queries by checking cache first

### Phase 3: CSV Migration Script (Issue #21 - Updated)
**Priority: Medium | Effort: Medium**

1. Create migration script (`scripts/migrate_csv_to_db.py`)
   - Parse existing CSV file
   - Validate each row (skip malformed entries)
   - Insert valid records into database
   - Generate migration report

2. Migration features
   - Idempotent (re-runnable)
   - Progress reporting
   - Error logging for skipped rows
   - Dry-run mode

3. CSV format handling
   - Parse current format: `Date Time, USD Buy, USD Sell, EUR Buy, EUR Sell, PLN Cross`
   - Handle malformed rows gracefully
   - Log statistics (total rows, migrated, skipped)

### Phase 4: Documentation and Testing
**Priority: Medium | Effort: Low**

1. Update README.md
   - Add database configuration options
   - Update Docker Compose examples
   - Document migration process

2. Add tests
   - Unit tests for database module
   - Integration tests for rate storage
   - Migration script tests

---

## 6. Updated Subtask Definitions

### Issue #19: Add storing of exchange rates to database
**Updated Title**: Add SQLite database storage for ALL exchange rates with timestamp-based deduplication

**Updated Description**:
Implement SQLite-based storage for ALL exchange rates fetched from Monobank and NBU APIs. Store complete API responses with proper timestamp handling to enable future analysis of any currency pair while avoiding redundant storage of unchanged rates.

**Key Implementation Detail**: 
The Monobank API provides individual `date` timestamps (Unix time) for each currency pair. These timestamps indicate when each specific rate was last updated by Monobank, and they vary significantly between pairs (some pairs update every few minutes, others only every few days). We must use these per-pair timestamps to:
1. Track the actual update time of each rate (not just our polling time)
2. Avoid storing duplicate unchanged rates across multiple API polls
3. Reduce database size by 40-60% through intelligent deduplication

**Acceptance Criteria**:
- [ ] Create `bot/database.py` module with SQLite operations
- [ ] Implement database schema with:
  - `currencies` table for ISO 4217 currency code lookup
  - `exchange_rates` table with dual timestamps:
    - `timestamp`: Our polling time (for audit/debug)
    - `api_timestamp`: API's `date` field (authoritative update time)
- [ ] Extract `date` field from each currency pair in Monobank API response
- [ ] Implement timestamp-based change detection:
  - Maintain in-memory cache of last-seen `api_timestamp` per currency pair
  - Only insert rates when `api_timestamp` is newer than cached value
  - Use UNIQUE constraint on `(source, currency_code_a, currency_code_b, api_timestamp)` to prevent duplicates
- [ ] Update `get_exchange_rates()` to store ALL rates from API when `DB_ENABLED=True`
- [ ] Store complete Monobank API response (~100 currency pairs per call, but only changed rates)
- [ ] Store complete NBU API response (~30 currencies per call)
- [ ] Store rate_buy, rate_sell, and rate_cross in a single row per currency pair
- [ ] Batch insert all new rates in a single transaction for performance
- [ ] Log statistics: total pairs fetched, new rates stored, unchanged rates skipped
- [ ] Maintain backward compatibility with CSV logging (CSV still logs only USD, EUR, PLN)
- [ ] Add `DB_ENABLED` and `DB_PATH` environment variables
- [ ] Update `.env.example` with new configuration options

**Technical Notes**:
- Use Python's built-in `sqlite3` module
- Store database in `/bot/data/exchange_rates.db` (configurable)
- Enable WAL mode for better concurrent access
- Use ISO 4217 numeric currency codes from API directly
- Implement efficient in-memory cache (dict) for last-seen timestamps: `{(source, code_a, code_b): api_timestamp}`
- On startup, populate cache from database: `SELECT source, currency_code_a, currency_code_b, MAX(api_timestamp) FROM exchange_rates GROUP BY ...`
- Add appropriate indexes for time-range and currency-pair queries on both `timestamp` and `api_timestamp`
- For NBU rates, use current polling time as `api_timestamp` since NBU doesn't provide per-rate timestamps

---

### Issue #20: Docker compose setup
**Updated Title**: Docker Compose configuration with volume mounts

**Updated Description**:
Create Docker Compose configuration for the exchange rate bot with proper volume mounts for database and CSV persistence.

**Acceptance Criteria**:
- [ ] Create `docker-compose.yml` file
- [ ] Define bot service with proper configuration
- [ ] Add volume mounts for:
  - Database file (`./data/exchange_rates.db`)
  - CSV file (`./data/exchange_rates.csv`)
- [ ] Configure environment variables via `.env` file
- [ ] Add health check for bot container
- [ ] Update README.md with Docker Compose usage instructions
- [ ] Optionally add Grafana service for visualization (future enhancement)

**Example Configuration**:
```yaml
version: '3.8'
services:
  bot:
    image: ghcr.io/yurnov/xratebot:latest
    env_file: .env
    volumes:
      - ./data:/bot/data
    restart: unless-stopped
```

---

### Issue #21: Migration script from CSV to database
**Updated Title**: CSV to SQLite migration script

**Updated Description**:
Create a Python script to migrate historical exchange rate data from CSV files to the SQLite database.

**Acceptance Criteria**:
- [ ] Create `scripts/migrate_csv_to_db.py`
- [ ] Parse CSV format: `Date Time, USD Buy, USD Sell, EUR Buy, EUR Sell, PLN Cross`
- [ ] Validate each row before insertion:
  - Check date/time format
  - Validate numeric rate values
  - Skip malformed rows
- [ ] Make migration idempotent (re-runnable without duplicates)
- [ ] Provide command-line options:
  - `--csv-file` - Path to CSV file
  - `--db-file` - Path to database file
  - `--dry-run` - Validate without inserting
  - `--verbose` - Detailed output
- [ ] Generate migration report:
  - Total rows processed
  - Rows successfully migrated
  - Rows skipped (with reasons)
- [ ] Add script to Docker image or provide standalone usage instructions

**Example Usage**:
```bash
python scripts/migrate_csv_to_db.py \
  --csv-file ./exchange_rates.csv \
  --db-file ./data/exchange_rates.db \
  --verbose
```

---

## 7. Configuration Changes

### New Environment Variables

| Variable | Description | Default | Valid Values |
|----------|-------------|---------|--------------|
| `DB_ENABLED` | Enable SQLite database logging | `False` | `True/False` |
| `DB_PATH` | Path to SQLite database file | `data/exchange_rates.db` | File path |

### Updated `.env.example`

```bash
# Telegram API token
BOT_TOKEN=your_bot_token
# PULL_INTERVAL in seconds, must be between 15 and 3600, default is 300 (Optional)
# PULL_INTERVAL=300
# Save rate to CSV file (Optional), default is False
# LOG_RATE=False
# Enable SQLite database logging (Optional), default is False
# DB_ENABLED=False
# Path to SQLite database file (Optional), default is data/exchange_rates.db
# DB_PATH=data/exchange_rates.db
# Log level (Optional), default is INFO
# LOG_LEVEL=INFO
```

---

## 8. File Structure After Implementation

```
exchange-rate-telegram-bot/
├── bot/
│   ├── main.py           # Updated with database integration
│   └── database.py       # NEW: SQLite database module
├── scripts/
│   └── migrate_csv_to_db.py  # NEW: Migration script
├── data/                 # NEW: Data directory (mounted volume)
│   ├── exchange_rates.db # SQLite database
│   └── exchange_rates.csv # CSV file (if LOG_RATE=True)
├── docs/
│   └── IMPLEMENTATION_PLAN.md  # This document
├── .env.example          # Updated with new variables
├── docker-compose.yml    # NEW: Docker Compose configuration
├── Dockerfile            # Updated if needed
├── CHANGELOG.md
├── LICENSE
├── README.md             # Updated with new instructions
└── requirements.txt      # Unchanged (sqlite3 is built-in)
```

---

## 9. Timeline and Dependencies

```
Phase 1 (Issue #20) ──┬──▶ Phase 2 (Issue #19) ──▶ Phase 3 (Issue #21)
                      │
                      └──▶ Can be done in parallel with Phase 2
```

### Recommended Order
1. **Issue #20** (Docker Compose) - Create infrastructure first
2. **Issue #19** (Database Storage) - Implement core functionality
3. **Issue #21** (Migration) - Migrate existing data last

### Estimated Effort
- Phase 1: 2-4 hours
- Phase 2: 4-6 hours
- Phase 3: 2-4 hours
- Phase 4 (Documentation): 1-2 hours
- **Total: 9-16 hours**

---

## 10. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Data loss during migration | High | Backup CSV before migration, implement dry-run mode |
| Performance impact on bot | Low | SQLite operations are fast, async writes if needed |
| Backward compatibility break | Medium | Make database optional, keep CSV logging |
| Disk space issues | Low | SQLite with WAL mode, regular vacuuming |
| Concurrent access issues | Low | SQLite handles single-writer, our use case is single-threaded |

---

## 11. Future Enhancements (Out of Scope)

These items are noted for potential future development but are not part of the current implementation plan:

1. **Grafana Dashboard**: Visualize exchange rate trends (see Section 11.1)
2. **API Endpoint**: HTTP API to query historical rates
3. **Data Export**: Export database to various formats (CSV, JSON, Excel)
4. **Rate Alerts**: Notify users when rates cross thresholds
5. **Extended Currency Support**: Add more currency pairs
6. **InfluxDB Migration**: If horizontal scaling becomes necessary

### 11.1 Grafana Integration (Future Phase)

For charting and visualization, Grafana can be added to the Docker Compose stack:

```yaml
version: '3.8'
services:
  bot:
    image: ghcr.io/yurnov/xratebot:latest
    env_file: .env
    volumes:
      - ./data:/bot/data
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
      - ./data:/data:ro  # Read-only access to SQLite database
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_INSTALL_PLUGINS=frser-sqlite-datasource
    depends_on:
      - bot
    restart: unless-stopped

volumes:
  grafana-data:
```

**Grafana Dashboard Capabilities:**
- Line charts showing rate trends over time
- Candlestick charts for daily open/high/low/close
- Spread analysis (buy vs sell difference)
- Monobank vs NBU rate comparison
- Currency pair correlation analysis
- Custom alerts when rates exceed thresholds

**SQLite Plugin for Grafana:**
The `frser-sqlite-datasource` plugin enables direct SQLite queries from Grafana, allowing real-time dashboard updates.

### 11.2 Data Export Options

For external analysis tools (Excel, Python pandas, etc.):

```bash
# Export to CSV
sqlite3 -header -csv data/exchange_rates.db \
  "SELECT * FROM exchange_rates WHERE timestamp >= '2024-01-01'" > export.csv

# Export to JSON
sqlite3 -json data/exchange_rates.db \
  "SELECT * FROM exchange_rates ORDER BY timestamp DESC LIMIT 1000" > export.json
```

Python integration for advanced analysis:
```python
import pandas as pd
import sqlite3

conn = sqlite3.connect('data/exchange_rates.db')
df = pd.read_sql_query("""
    SELECT timestamp, currency_code, rate_type, rate 
    FROM exchange_rates 
    WHERE source = 'monobank'
    ORDER BY timestamp
""", conn)

# Create pivot table for analysis
pivot = df.pivot_table(
    index='timestamp', 
    columns=['currency_code', 'rate_type'], 
    values='rate'
)
```

---

## 12. Conclusion

The recommended approach uses SQLite as an embedded time-series database, providing:

- **Minimal resource footprint**: No additional containers or services
- **Simple operations**: Single file database, easy backup
- **Full backward compatibility**: CSV logging remains available
- **Future-proof design**: Stores ALL ~100+ currency pairs from API, not just displayed currencies
- **ISO 4217 compliant**: Uses standard numeric currency codes for maximum compatibility
- **Docker Compose ready**: Prepared for future service additions
- **Analytics-ready**: Rich SQL query support for trend analysis, aggregations, and charting
- **Visualization-ready**: Compatible with Grafana and Python data analysis tools (pandas, matplotlib)
- **Scalable**: Handles millions of records efficiently (estimated ~31.5M records over 5 years with optimization)
- **Intelligent deduplication**: Uses API-provided per-pair timestamps to avoid storing unchanged rates
  - **40-60% storage reduction**: Only stores rates when they actually change
  - **Accurate timestamps**: Records actual rate update times, not just polling times
  - **Efficient queries**: Dual timestamp fields enable both audit trails and accurate time-series analysis
- **Update frequency awareness**: Automatically adapts to different update patterns (high-frequency pairs like USD/UAH vs. low-frequency exotic currencies)

### Key Innovation: Per-Pair Timestamp Utilization

The critical insight from analyzing the actual Monobank API is that **each currency pair has its own `date` timestamp**, reflecting when that specific rate was last updated. This varies significantly:

- **High-frequency pairs** (USD/UAH, EUR/UAH, PLN/UAH): Updated every few minutes
- **Medium-frequency pairs**: Updated hourly or several times per day  
- **Low-frequency pairs** (exotic currencies): Updated once per day or less frequently

By using these per-pair timestamps for change detection, we:
1. **Reduce storage by 40-60%**: Don't store redundant unchanged rates
2. **Improve data accuracy**: Record the actual update time, not our arbitrary polling time
3. **Enable better analytics**: Queries reflect real rate changes, not polling artifacts
4. **Optimize performance**: Fewer database writes, faster queries on smaller dataset

This plan maintains the project's lightweight nature while significantly improving data storage, querying, and analysis capabilities for all available currencies, with smart optimization based on actual API behavior.

---

*Document created: December 2025*
*Last updated: December 2025 (Revised to incorporate per-pair timestamp optimization)*
*Related issues: #18, #19, #20, #21*
