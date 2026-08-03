# Exchange Rate Database Usage Guide

This document describes the SQLite database schema used to store Monobank exchange rates and provides examples of common queries for data analysis.

## Overview

The database stores historical exchange rate data from Monobank API with timestamp-based deduplication. Each currency pair has its own update timestamp from the API, enabling efficient storage and historical analysis.

**Note:** NBU (National Bank of Ukraine) rates are NOT stored in the database. They are fetched on-demand for display purposes only, as NBU provides infrequent updates (once per day) and maintains comprehensive historical data via their API.

## Database Schema

### Table: `currencies`

Reference table for ISO 4217 currency codes.

```sql
CREATE TABLE currencies (
    code INTEGER PRIMARY KEY,           -- ISO 4217 numeric code (e.g., 840 for USD)
    alpha_code TEXT NOT NULL,           -- ISO 4217 alpha code (e.g., 'USD')
    name TEXT,                          -- Currency name (e.g., 'US Dollar')
    symbol TEXT                         -- Currency symbol (e.g., '$')
);
```

**Key Points:**
- Pre-populated with ~107 common currencies
- New currency codes are auto-inserted when encountered in API responses
- Uses ISO 4217 numeric codes as primary keys (same as Monobank API)

**Sample Data:**
```
code | alpha_code | name                  | symbol
-----|------------|----------------------|--------
840  | USD        | US Dollar            | $
978  | EUR        | Euro                 | €
980  | UAH        | Ukrainian Hryvnia    | ₴
985  | PLN        | Polish Zloty         | zł
826  | GBP        | British Pound        | £
```

### Table: `exchange_rates`

Main table storing historical exchange rate data from Monobank.

```sql
CREATE TABLE exchange_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,        -- Our polling time (ISO 8601 format, for audit)
    api_timestamp INTEGER NOT NULL,     -- API's 'date' field (Unix timestamp, authoritative)
    source TEXT NOT NULL,               -- Data source ('monobank')
    currency_code_a INTEGER NOT NULL,   -- First currency code (ISO 4217 numeric)
    currency_code_b INTEGER NOT NULL,   -- Second currency code (ISO 4217 numeric)
    rate_buy REAL,                      -- Buy rate (can be NULL for cross rates)
    rate_sell REAL,                     -- Sell rate (can be NULL for cross rates)
    rate_cross REAL,                    -- Cross rate (can be NULL for buy/sell rates)
    UNIQUE(source, currency_code_a, currency_code_b, api_timestamp),
    FOREIGN KEY (currency_code_a) REFERENCES currencies(code),
    FOREIGN KEY (currency_code_b) REFERENCES currencies(code)
);
```

**Key Points:**
- **Dual timestamps**: `timestamp` tracks when we polled the API, `api_timestamp` is the authoritative update time from Monobank
- **Deduplication**: UNIQUE constraint on `(source, currency_code_a, currency_code_b, api_timestamp)` prevents duplicates
- **Three rate types**: `rate_buy`, `rate_sell` (for direct conversions), `rate_cross` (for indirect conversions)
- **Storage efficiency**: Typical 40-60% reduction through intelligent deduplication

**Sample Data:**
```
id | timestamp           | api_timestamp | source   | currency_code_a | currency_code_b | rate_buy | rate_sell | rate_cross
---|---------------------|---------------|----------|-----------------|-----------------|----------|-----------|------------
1  | 2024-12-03 10:00:00 | 1733228400    | monobank | 840             | 980             | 42.14    | 42.54     | NULL
2  | 2024-12-03 10:00:00 | 1733228400    | monobank | 978             | 980             | 48.90    | 49.50     | NULL
3  | 2024-12-03 10:00:00 | 1733228400    | monobank | 985             | 980             | NULL     | NULL      | 10.50
```

### Indexes

The only index on `exchange_rates` is the implicit one backing the `UNIQUE(source,
currency_code_a, currency_code_b, api_timestamp)` constraint, which serves the
`INSERT OR IGNORE` deduplication.

In production the table is write-only — the bot answers users from the live API and
the chart builder reads the CSV — so no secondary indexes are maintained. Five were
created historically (`idx_rates_timestamp`, `idx_rates_api_timestamp`,
`idx_rates_currency_pair`, `idx_rates_source`, `idx_rates_currency_a`); measured
with `dbstat` they held roughly two thirds of the database file and made every
insert update seven B-trees instead of two. Existing databases can drop them and
reclaim the space with a one-shot migration:

```bash
# Stop the bot first: the script refuses to run while the database is locked,
# and the final VACUUM would block the bot's inserts anyway.
python bot/scripts/drop_unused_indexes.py data/exchange_rates.db
```

For the ad-hoc analysis queries below, create the index you need on a **copy** of
the database (e.g. a restored backup), where it costs the production host nothing:

```sql
CREATE INDEX idx_rates_currency_pair ON exchange_rates(currency_code_a, currency_code_b, api_timestamp);
```

## Query Examples

### 1. Get Latest Exchange Rate for a Currency Pair

Get the most recent USD/UAH rate:

```sql
SELECT
    datetime(api_timestamp, 'unixepoch') as update_time,
    rate_buy,
    rate_sell
FROM exchange_rates
WHERE currency_code_a = 840  -- USD
  AND currency_code_b = 980  -- UAH
  AND source = 'monobank'
ORDER BY api_timestamp DESC
LIMIT 1;
```
<details>
<summary>Python Example</summary>

```python
import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/exchange_rates.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT
        api_timestamp,
        rate_buy,
        rate_sell
    FROM exchange_rates
    WHERE currency_code_a = 840 AND currency_code_b = 980
      AND source = 'monobank'
    ORDER BY api_timestamp DESC
    LIMIT 1
""")

result = cursor.fetchone()
if result:
    api_timestamp, rate_buy, rate_sell = result
    update_time = datetime.fromtimestamp(api_timestamp)
    print(f"USD/UAH at {update_time}: Buy={rate_buy}, Sell={rate_sell}")

conn.close()
```
</details>

### 2. Get Historical Rates for Time Range

Get all USD/UAH rates for the last 7 days:

```sql
SELECT
    datetime(api_timestamp, 'unixepoch') as update_time,
    rate_buy,
    rate_sell
FROM exchange_rates
WHERE currency_code_a = 840
  AND currency_code_b = 980
  AND api_timestamp >= strftime('%s', 'now', '-7 days')
ORDER BY api_timestamp ASC;
```

<details>
<summary>Python Example</summary>

```python
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/exchange_rates.db')
cursor = conn.cursor()

# Get rates for last 7 days
seven_days_ago = int((datetime.now() - timedelta(days=7)).timestamp())

cursor.execute("""
    SELECT api_timestamp, rate_buy, rate_sell
    FROM exchange_rates
    WHERE currency_code_a = 840 AND currency_code_b = 980
      AND api_timestamp >= ?
    ORDER BY api_timestamp ASC
""", (seven_days_ago,))

for row in cursor.fetchall():
    api_timestamp, rate_buy, rate_sell = row
    update_time = datetime.fromtimestamp(api_timestamp)
    print(f"{update_time}: Buy={rate_buy}, Sell={rate_sell}")

conn.close()
```
</details>

### 3. Get All Available Currency Pairs

List all currency pairs currently in the database:

```sql
SELECT DISTINCT
    c1.alpha_code as from_currency,
    c2.alpha_code as to_currency,
    COUNT(*) as rate_count,
    datetime(MIN(api_timestamp), 'unixepoch') as first_update,
    datetime(MAX(api_timestamp), 'unixepoch') as last_update
FROM exchange_rates e
JOIN currencies c1 ON e.currency_code_a = c1.code
JOIN currencies c2 ON e.currency_code_b = c2.code
WHERE e.source = 'monobank'
GROUP BY e.currency_code_a, e.currency_code_b
ORDER BY rate_count DESC;
```

<details>
<summary>Python Example</summary>

```python
import sqlite3

conn = sqlite3.connect('data/exchange_rates.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT DISTINCT
        c1.alpha_code,
        c2.alpha_code,
        COUNT(*) as rate_count
    FROM exchange_rates e
    JOIN currencies c1 ON e.currency_code_a = c1.code
    JOIN currencies c2 ON e.currency_code_b = c2.code
    GROUP BY e.currency_code_a, e.currency_code_b
    ORDER BY rate_count DESC
""")

print("Available currency pairs:")
for from_curr, to_curr, count in cursor.fetchall():
    print(f"  {from_curr}/{to_curr}: {count} rates")

conn.close()
```
</details>

### 4. Calculate Average Rate Over Time Period

Calculate average USD/UAH buy rate for last 30 days:

```sql
SELECT
    AVG(rate_buy) as avg_buy_rate,
    MIN(rate_buy) as min_buy_rate,
    MAX(rate_buy) as max_buy_rate,
    COUNT(*) as sample_count
FROM exchange_rates
WHERE currency_code_a = 840
  AND currency_code_b = 980
  AND api_timestamp >= strftime('%s', 'now', '-30 days')
  AND rate_buy IS NOT NULL;
```

<details>
<summary>Python Example</summary>

```python
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/exchange_rates.db')
cursor = conn.cursor()

thirty_days_ago = int((datetime.now() - timedelta(days=30)).timestamp())

cursor.execute("""
    SELECT
        AVG(rate_buy) as avg_buy,
        MIN(rate_buy) as min_buy,
        MAX(rate_buy) as max_buy,
        COUNT(*) as count
    FROM exchange_rates
    WHERE currency_code_a = 840 AND currency_code_b = 980
      AND api_timestamp >= ?
      AND rate_buy IS NOT NULL
""", (thirty_days_ago,))

avg, min_rate, max_rate, count = cursor.fetchone()
print(f"USD/UAH (last 30 days):")
print(f"  Average: {avg:.4f}")
print(f"  Min: {min_rate:.4f}")
print(f"  Max: {max_rate:.4f}")
print(f"  Samples: {count}")

conn.close()
```
</details>

### 5. Get Daily Rate Changes

Calculate daily rate changes for USD/UAH:

```sql
WITH daily_rates AS (
    SELECT
        DATE(datetime(api_timestamp, 'unixepoch')) as rate_date,
        AVG(rate_buy) as avg_buy,
        AVG(rate_sell) as avg_sell
    FROM exchange_rates
    WHERE currency_code_a = 840
      AND currency_code_b = 980
      AND api_timestamp >= strftime('%s', 'now', '-30 days')
    GROUP BY rate_date
)
SELECT
    rate_date,
    avg_buy,
    avg_sell,
    avg_buy - LAG(avg_buy) OVER (ORDER BY rate_date) as buy_change,
    avg_sell - LAG(avg_sell) OVER (ORDER BY rate_date) as sell_change
FROM daily_rates
ORDER BY rate_date DESC;
```

<details>
<summary>Python Example</summary>

```python
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/exchange_rates.db')
cursor = conn.cursor()

thirty_days_ago = int((datetime.now() - timedelta(days=30)).timestamp())

cursor.execute("""
    WITH daily_rates AS (
        SELECT
            DATE(datetime(api_timestamp, 'unixepoch')) as rate_date,
            AVG(rate_buy) as avg_buy,
            AVG(rate_sell) as avg_sell
        FROM exchange_rates
        WHERE currency_code_a = 840 AND currency_code_b = 980
          AND api_timestamp >= ?
        GROUP BY rate_date
    )
    SELECT
        rate_date,
        avg_buy,
        avg_sell
    FROM daily_rates
    ORDER BY rate_date DESC
    LIMIT 10
""", (thirty_days_ago,))

print("Daily USD/UAH rates (last 10 days):")
for rate_date, avg_buy, avg_sell in cursor.fetchall():
    print(f"  {rate_date}: Buy={avg_buy:.4f}, Sell={avg_sell:.4f}")

conn.close()
```
</details>

### 6. Get Rate Update Frequency

Analyze how often each currency pair is updated:

```sql
SELECT
    c1.alpha_code || '/' || c2.alpha_code as pair,
    COUNT(*) as update_count,
    (MAX(api_timestamp) - MIN(api_timestamp)) / 3600.0 / COUNT(*) as avg_hours_between_updates
FROM exchange_rates e
JOIN currencies c1 ON e.currency_code_a = c1.code
JOIN currencies c2 ON e.currency_code_b = c2.code
WHERE api_timestamp >= strftime('%s', 'now', '-7 days')
GROUP BY e.currency_code_a, e.currency_code_b
HAVING update_count > 1
ORDER BY avg_hours_between_updates ASC
LIMIT 20;
```

### 7. Export Rates to CSV (Using Python)

Export historical data to CSV for analysis:

```python
import sqlite3
import csv
from datetime import datetime

conn = sqlite3.connect('data/exchange_rates.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT
        datetime(e.api_timestamp, 'unixepoch') as update_time,
        c1.alpha_code as from_currency,
        c2.alpha_code as to_currency,
        e.rate_buy,
        e.rate_sell,
        e.rate_cross
    FROM exchange_rates e
    JOIN currencies c1 ON e.currency_code_a = c1.code
    JOIN currencies c2 ON e.currency_code_b = c2.code
    WHERE e.currency_code_a = 840 AND e.currency_code_b = 980
    ORDER BY e.api_timestamp ASC
""")

with open('usd_uah_rates.csv', 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['timestamp', 'from', 'to', 'buy', 'sell', 'cross'])
    writer.writerows(cursor.fetchall())

print("Data exported to usd_uah_rates.csv")
conn.close()
```

### 8. Create Time Series Data for Charting

Prepare data for plotting exchange rate trends:

```python
import sqlite3
from datetime import datetime, timedelta
import json

conn = sqlite3.connect('data/exchange_rates.db')
cursor = conn.cursor()

# Get hourly average rates for last 7 days
seven_days_ago = int((datetime.now() - timedelta(days=7)).timestamp())

cursor.execute("""
    SELECT
        strftime('%Y-%m-%d %H:00:00', datetime(api_timestamp, 'unixepoch')) as hour,
        AVG(rate_buy) as avg_buy,
        AVG(rate_sell) as avg_sell
    FROM exchange_rates
    WHERE currency_code_a = 840 AND currency_code_b = 980
      AND api_timestamp >= ?
      AND rate_buy IS NOT NULL
    GROUP BY hour
    ORDER BY hour ASC
""", (seven_days_ago,))

# Prepare data for charting
chart_data = {
    'labels': [],
    'buy_rates': [],
    'sell_rates': []
}

for hour, avg_buy, avg_sell in cursor.fetchall():
    chart_data['labels'].append(hour)
    chart_data['buy_rates'].append(round(avg_buy, 4))
    chart_data['sell_rates'].append(round(avg_sell, 4))

# Save as JSON for web visualization
with open('chart_data.json', 'w') as f:
    json.dump(chart_data, f, indent=2)

print(f"Chart data prepared: {len(chart_data['labels'])} data points")
conn.close()
```

## Database Maintenance

### Check Database Size

```sql
-- Get database file size (from command line)
-- sqlite3 data/exchange_rates.db "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();"
```

<details>
<summary>Python Example</summary>

```python
import sqlite3
import os

db_path = 'data/exchange_rates.db'
file_size = os.path.getsize(db_path)
print(f"Database size: {file_size / 1024 / 1024:.2f} MB")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM exchange_rates")
rate_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM currencies")
currency_count = cursor.fetchone()[0]

print(f"Exchange rates stored: {rate_count:,}")
print(f"Currency codes: {currency_count}")

conn.close()
```
</details>

### Vacuum Database (Reclaim Space)

```sql
VACUUM;
```

```python
import sqlite3

conn = sqlite3.connect('data/exchange_rates.db')
conn.execute("VACUUM")
print("Database optimized")
conn.close()
```

## Performance Tips

1. **Use indexes**: Production carries no secondary indexes (see [Indexes](#indexes)); for analysis work, create the index your query needs on a copy of the database
2. **Batch operations**: When inserting multiple rates, use transactions
3. **Date filtering**: Use Unix timestamps for date comparisons (faster than datetime functions)
4. **WAL mode**: Enabled by default for better concurrent read/write performance
5. **Prepared statements**: Use parameterized queries to avoid SQL injection and improve performance

## Common Analysis Patterns

### Volatility Analysis

```python
import sqlite3
import statistics
from datetime import datetime, timedelta

conn = sqlite3.connect('data/exchange_rates.db')
cursor = conn.cursor()

seven_days_ago = int((datetime.now() - timedelta(days=7)).timestamp())

cursor.execute("""
    SELECT rate_buy
    FROM exchange_rates
    WHERE currency_code_a = 840 AND currency_code_b = 980
      AND api_timestamp >= ?
      AND rate_buy IS NOT NULL
    ORDER BY api_timestamp ASC
""", (seven_days_ago,))

rates = [row[0] for row in cursor.fetchall()]

if len(rates) > 1:
    volatility = statistics.stdev(rates)
    mean_rate = statistics.mean(rates)
    cv = (volatility / mean_rate) * 100  # Coefficient of variation

    print(f"USD/UAH Rate Statistics (last 7 days):")
    print(f"  Mean: {mean_rate:.4f}")
    print(f"  Std Dev: {volatility:.4f}")
    print(f"  Coefficient of Variation: {cv:.2f}%")

conn.close()
```

### Trend Detection

```python
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/exchange_rates.db')
cursor = conn.cursor()

# Get first and last rates for last 30 days
thirty_days_ago = int((datetime.now() - timedelta(days=30)).timestamp())

cursor.execute("""
    SELECT MIN(api_timestamp), MAX(api_timestamp)
    FROM exchange_rates
    WHERE currency_code_a = 840 AND currency_code_b = 980
      AND api_timestamp >= ?
""", (thirty_days_ago,))

min_ts, max_ts = cursor.fetchone()

# Get rates at start and end
cursor.execute("""
    SELECT rate_buy FROM exchange_rates
    WHERE currency_code_a = 840 AND currency_code_b = 980
      AND api_timestamp = ?
""", (min_ts,))
start_rate = cursor.fetchone()[0]

cursor.execute("""
    SELECT rate_buy FROM exchange_rates
    WHERE currency_code_a = 840 AND currency_code_b = 980
      AND api_timestamp = ?
""", (max_ts,))
end_rate = cursor.fetchone()[0]

change_pct = ((end_rate - start_rate) / start_rate) * 100
direction = "increased" if change_pct > 0 else "decreased"

print(f"USD/UAH {direction} by {abs(change_pct):.2f}% over last 30 days")
print(f"  Start: {start_rate:.4f}")
print(f"  End: {end_rate:.4f}")

conn.close()
```

## Additional Resources

- **SQLite Documentation**: https://www.sqlite.org/docs.html
- **ISO 4217 Currency Codes**: https://en.wikipedia.org/wiki/ISO_4217
- **Monobank API**: https://api.monobank.ua/docs/
- **Python sqlite3 Module**: https://docs.python.org/3/library/sqlite3.html
