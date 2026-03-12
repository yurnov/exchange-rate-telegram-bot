# Database Handling & S3 Backup - Analysis and Design

## Overview

This document analyzes options for improving SQLite database handling (WAL mode, autovacuum)
and adding S3-compatible backup support for the Exchange Rate Telegram Bot.

---

## 1. SQLite Database Handling Improvements

### 1.1 WAL (Write-Ahead Logging) Mode

**Current state:** WAL mode is already enabled via `PRAGMA journal_mode=WAL`.

**What WAL produces:**
- `exchange_rates.db-wal` — the Write-Ahead Log file containing uncommitted changes
- `exchange_rates.db-shm` — shared memory file used for inter-process coordination

**Important considerations:**
- Both `-wal` and `-shm` files **must** be preserved alongside the main `.db` file
- Volume mounts in Docker must include the entire directory, not just the `.db` file
- Backups must account for WAL — using SQLite's online backup API (`sqlite3.Connection.backup()`)
  safely consolidates WAL into the backup copy

**Improvements implemented:**
- **WAL checkpoint on close:** Ensures all WAL changes are written back to the main database
  file when the bot shuts down cleanly (`PRAGMA wal_checkpoint(TRUNCATE)`)
- **`PRAGMA synchronous=FULL`:** Maximum durability — ensures every committed transaction is
  on disk before continuing. Critical in resource-constrained environments where the container
  can be evicted (SIGKILL) at any time. While `NORMAL` would offer better write throughput,
  `FULL` is the right choice when fault-tolerance is the priority and the write pattern is
  light (a few inserts every few minutes)
- **`PRAGMA busy_timeout=5000`:** Prevents `database is locked` errors by waiting up to
  5 seconds for locks to be released, which is important when backup operations run
  concurrently with the main bot

### 1.2 Autovacuum

**Options analyzed:**

| Mode | Description | Pros | Cons |
|------|-------------|------|------|
| `NONE` (default) | No automatic vacuuming | No overhead | Database file never shrinks |
| `FULL` | Automatically reclaims space after each transaction | No manual intervention needed | Small write overhead per transaction |
| `INCREMENTAL` | Reclaims space only when `PRAGMA incremental_vacuum` is called | Fine-grained control over when vacuuming occurs | Requires explicit scheduling |

**Decision: `FULL` autovacuum**

Rationale:
- Exchange rate data is append-only (INSERT OR IGNORE), so deletions are rare, but when
  they occur, space should be reclaimed immediately to keep the DB file small
- In a resource-constrained environment where the container may be evicted at any time,
  `FULL` mode ensures space is reclaimed automatically after each transaction
- `INCREMENTAL` mode requires explicit scheduling of `PRAGMA incremental_vacuum` calls,
  which may never execute if the container is evicted before the scheduled time
- The per-transaction overhead of `FULL` mode is negligible for the bot's light write
  pattern (a few inserts every few minutes)

**Note:** `auto_vacuum` must be set before the first table is created. For existing databases,
a `VACUUM` command is needed to change the mode, which rewrites the entire database file.

### 1.3 Cache Size

**Decision:** Use SQLite default cache size (2MB)

In a resource-constrained environment where the container is frequently evicted due to
memory pressure, keeping the default 2MB cache avoids contributing to memory consumption.
The bot's write pattern (periodic inserts every few minutes) does not benefit significantly
from a larger cache.

---

## 2. S3 Backup - Options Analysis

### Option A: Integrated Backup in Main Bot Process

The backup logic runs inside the main bot container as a scheduled task.

| Aspect | Details |
|--------|---------|
| **Pros** | Simple deployment (single container), no inter-process coordination needed, direct access to database connection for safe backup |
| **Cons** | boto3 dependency added to main container (~50MB), backup I/O competes with bot operations, backup failure could affect bot stability, tight coupling of concerns |

### Option B: Sidecar Container with Shared Volume

A separate container runs alongside the bot, sharing the data volume.
It periodically creates a backup and uploads to S3.

| Aspect | Details |
|--------|---------|
| **Pros** | Complete isolation — backup failures don't affect bot, independent resource allocation, can use different schedules/retry logic, follows single-responsibility principle, main bot image stays lean |
| **Cons** | Requires Docker Compose (or orchestrator), shared volume coordination, must use SQLite's backup API to handle WAL safely, slightly more complex deployment |

### Option C: External CronJob / Kubernetes Job

An external cron job or Kubernetes CronJob triggers backups.

| Aspect | Details |
|--------|---------|
| **Pros** | Platform-native scheduling, good for Kubernetes deployments, zero overhead when not running |
| **Cons** | Platform-dependent, requires additional infrastructure configuration, not portable |

### Recommended: Option B — Sidecar Container

**Rationale:**
1. **Separation of concerns:** The bot's primary job is serving exchange rates; backup is an
   operational concern that should be isolated
2. **Fault isolation:** A backup failure (network timeout, S3 auth error) cannot crash or
   slow down the bot
3. **Lean main image:** No need to add boto3 (~50MB) to the main bot container
4. **Flexibility:** The sidecar's backup schedule, retry logic, and S3 configuration are
   fully independent
5. **SQLite safety:** Using the `sqlite3.Connection.backup()` API creates a consistent
   snapshot even while the bot is writing to the database with WAL mode

### Implementation Details

The sidecar container:
1. Uses SQLite's online backup API to create a safe copy of the database
2. Uploads the backup to S3-compatible storage (AWS S3, MinIO, Backblaze B2, etc.)
3. Supports configurable backup intervals and retention
4. Runs as a lightweight Python container with only `boto3` as an additional dependency
5. Shares the `./data` volume with the main bot container (read-only access is sufficient)

### Backup Script Design

The backup script (`bot/backup.py`) is designed to work in multiple modes:
- **Sidecar mode:** Runs continuously with periodic backups (default)
- **One-shot mode:** Runs a single backup and exits (for cron jobs / Kubernetes Jobs)

```
Environment Variables:
  S3_ENDPOINT_URL    — S3-compatible endpoint (e.g., https://s3.amazonaws.com)
  S3_BUCKET          — Target bucket name
  S3_PREFIX          — Key prefix for backup files (default: backups/)
  S3_ACCESS_KEY      — Access key ID
  S3_SECRET_KEY      — Secret access key
  S3_REGION          — AWS region (default: us-east-1)
  BACKUP_INTERVAL    — Seconds between backups in sidecar mode (default: 86400 = 24h)
  BACKUP_RETENTION   — Number of backup copies to retain (default: 7)
  DB_PATH            — Path to SQLite database (default: data/exchange_rates.db)
  BACKUP_MODE        — "scheduled" (default) or "once"
  LOG_LEVEL          — Logging level (default: INFO)
```

---

## 3. Docker Compose Configuration

The `docker-compose.yml` includes an optional `backup` service:

```yaml
services:
  bot:
    image: ghcr.io/yurnov/xratebot:v0.9.0
    volumes:
      - ./data:/bot/data
    env_file: .env
    restart: unless-stopped

  backup:
    build:
      context: .
      dockerfile: Dockerfile.backup
    volumes:
      - ./data:/bot/data:ro  # Read-only access to database
    env_file: .env.backup
    restart: unless-stopped
    depends_on:
      - bot
    profiles:
      - backup  # Only starts when explicitly enabled
```

To enable backup: `docker compose --profile backup up -d`

---

## 4. File Structure

```
exchange-rate-telegram-bot/
├── backup/
│   ├── Dockerfile            # Backup sidecar container
│   └── requirements.txt      # Backup sidecar dependencies (boto3)
├── bot/
│   ├── main.py               # Main bot application
│   └── backup.py             # Backup database snapshot script
├── data/
│   └── exchange_rates.db     # SQLite database
├── .env.example              # Updated with new DB and backup variables
└── docs                      # Documentation and examples
```
