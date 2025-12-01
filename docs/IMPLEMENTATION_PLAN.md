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

### Requirements
- Store exchange rate data with 5-minute granularity
- Support data storage for multiple years (estimated ~500,000 records over 5 years)
- Low resource consumption (memory and CPU)
- Maintain backward compatibility with CSV logging
- Support migration from existing CSV data
- Use Docker Compose for service orchestration

---

## 2. Database Selection Analysis

### Data Volume Estimation
- **Polling interval**: 5 minutes (configurable, 15s-3600s)
- **Records per day**: 288 (at 5-minute intervals)
- **Records per year**: ~105,000
- **5-year storage**: ~525,000 records
- **Record size**: ~100-150 bytes per record
- **Total storage**: < 100 MB for 5 years of data

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
2. **Perfect for Data Scale**: Our estimated data volume (< 100 MB for 5 years) is well within SQLite's optimal range
3. **No Additional Infrastructure**: No separate database container needed
4. **Full SQL Support**: Standard SQL queries for data retrieval and analysis
5. **Python Native Support**: Built-in `sqlite3` module, no additional dependencies
6. **Simple Backup**: Single file database, easy to backup and migrate
7. **Backward Compatible**: Can run alongside existing CSV logging

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

### 4.1 Main Exchange Rates Table

```sql
CREATE TABLE IF NOT EXISTS exchange_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    source TEXT NOT NULL,  -- 'monobank', 'nbu'
    currency_code TEXT NOT NULL,  -- 'USD', 'EUR', 'PLN'
    rate_type TEXT NOT NULL,  -- 'buy', 'sell', 'cross', 'official'
    rate REAL NOT NULL,
    UNIQUE(timestamp, source, currency_code, rate_type)
);

CREATE INDEX idx_rates_timestamp ON exchange_rates(timestamp);
CREATE INDEX idx_rates_currency ON exchange_rates(currency_code, timestamp);
CREATE INDEX idx_rates_source ON exchange_rates(source, timestamp);
```

### 4.2 Schema Benefits
- **Normalized**: Easy to add new currencies without schema changes
- **Flexible**: Supports multiple sources (Monobank, NBU)
- **Queryable**: Efficient time-range and currency-specific queries
- **Unique Constraint**: Prevents duplicate entries (idempotent inserts)

### 4.3 Example Queries

```sql
-- Get latest USD rates
SELECT * FROM exchange_rates 
WHERE currency_code = 'USD' 
ORDER BY timestamp DESC LIMIT 10;

-- Get daily average EUR sell rate
SELECT DATE(timestamp) as day, AVG(rate) as avg_rate
FROM exchange_rates 
WHERE currency_code = 'EUR' AND rate_type = 'sell'
GROUP BY DATE(timestamp);

-- Get rate history for past 24 hours
SELECT * FROM exchange_rates 
WHERE timestamp >= datetime('now', '-24 hours')
ORDER BY timestamp DESC;
```

---

## 5. Implementation Phases

### Phase 1: Database Infrastructure (Issue #20 - Updated)
**Priority: High | Effort: Low**

1. Create SQLite database module (`bot/database.py`)
   - Database initialization
   - Schema creation
   - Connection management
   - CRUD operations

2. Update Docker Compose configuration
   - Add volume mount for database file
   - Update `.env.example` with database settings

3. Add database configuration options
   - `DB_ENABLED` - Enable/disable database logging (default: False for backward compatibility)
   - `DB_PATH` - Path to SQLite database file

### Phase 2: Exchange Rate Storage (Issue #19 - Updated)
**Priority: High | Effort: Medium**

1. Update `get_exchange_rates()` function
   - Add database insertion after fetching rates
   - Implement error handling for database operations
   - Ensure both Monobank and NBU rates are stored

2. Maintain backward compatibility
   - CSV logging continues to work when `LOG_RATE=True`
   - Database logging works when `DB_ENABLED=True`
   - Both can be enabled simultaneously

3. Add data validation
   - Validate rates before insertion
   - Handle duplicate entries gracefully

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
**Updated Title**: Add SQLite database storage for exchange rates

**Updated Description**:
Implement SQLite-based storage for exchange rates fetched from Monobank and NBU APIs.

**Acceptance Criteria**:
- [ ] Create `bot/database.py` module with SQLite operations
- [ ] Implement database schema for exchange rates
- [ ] Update `get_exchange_rates()` to store rates in database when `DB_ENABLED=True`
- [ ] Store all rate types: USD buy/sell, EUR buy/sell, PLN cross, USD NBU, EUR NBU, PLN NBU
- [ ] Handle duplicate entries gracefully (use UPSERT or ignore)
- [ ] Maintain backward compatibility with CSV logging
- [ ] Add `DB_ENABLED` and `DB_PATH` environment variables
- [ ] Update `.env.example` with new configuration options

**Technical Notes**:
- Use Python's built-in `sqlite3` module
- Store database in `/bot/data/exchange_rates.db` (configurable)
- Enable WAL mode for better concurrent access
- Add appropriate indexes for time-range queries

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

1. **Grafana Dashboard**: Visualize exchange rate trends
2. **API Endpoint**: HTTP API to query historical rates
3. **Data Export**: Export database to various formats
4. **Rate Alerts**: Notify users when rates cross thresholds
5. **Extended Currency Support**: Add more currency pairs
6. **InfluxDB Migration**: If horizontal scaling becomes necessary

---

## 12. Conclusion

The recommended approach uses SQLite as an embedded time-series database, providing:

- **Minimal resource footprint**: No additional containers or services
- **Simple operations**: Single file database, easy backup
- **Full backward compatibility**: CSV logging remains available
- **Extensible design**: Normalized schema supports additional currencies
- **Docker Compose ready**: Prepared for future service additions

This plan maintains the project's lightweight nature while significantly improving data storage and querying capabilities.

---

*Document created: December 2025*
*Last updated: December 2025*
*Related issues: #18, #19, #20, #21*
