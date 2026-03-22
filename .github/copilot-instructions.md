# Project Overview

This repository contains an Exchange Rate Telegram Bot: a lightweight Python application that runs in Docker and provides real-time exchange rates for USD 🇺🇸, EUR 🇪🇺, PLN 🇵🇱, and TRY 🇹🇷 against Ukrainian Hryvnia (UAH 🇺🇦).

The bot fetches market rates from Monobank and official rates from NBU, supports currency conversion, stores Monobank history in SQLite, and includes an optional S3-compatible backup sidecar for the database.

## Development Status

- **Active Development Branch**: `development` (feature work and integration)
- **Stable Branch**: `main` (release branch)
- **Current State**: SQLite storage, CSV-to-SQLite migration, Docker Compose deployment, and backup sidecar are implemented

# Technology Stack

## Current Stack
- **Language**: Python 3.14
- **Bot Framework**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- **HTTP Client**: [requests](https://github.com/psf/requests)
- **Configuration**: [python-dotenv](https://github.com/theskumar/python-dotenv)
- **Scheduling**: [schedule](https://github.com/dbader/schedule)
- **Database**: SQLite (built into Python via `sqlite3`)
- **Backup (sidecar)**: [boto3](https://github.com/boto/boto3) for S3-compatible object storage uploads
- **Containerization**: Docker + Docker Compose
- **APIs**:
  - [Monobank API](https://api.monobank.ua/docs/) for market buy/sell/cross rates
  - [NBU API](https://bank.gov.ua/ua/open-data/api-dev) for official rates

# Coding Guidelines

## Code Style
- Follow PEP 8 guidelines
- Use [Black](https://github.com/psf/black) formatting with:
  - Line length: 120
  - Skip string normalization enabled (`--skip-string-normalization`)
- Disable pylint checks for R, C, and W1203
- Keep functions focused and maintainable

## Comments and Documentation
- Add docstrings for new functions
- Keep comments concise and meaningful
- Use English for code, comments, and documentation

## Error Handling
- Use exception handling with clear logging context
- Return user-friendly bot messages when errors affect commands

## Configuration
- Use environment variables for runtime configuration
- Keep sensible defaults for optional values
- Validate configuration values at startup

## Database Design
- Store **all Monobank currency pairs** returned by API, not only displayed pairs
- Use dual timestamp tracking:
  - `timestamp`: poll time in bot
  - `api_timestamp`: authoritative Monobank update timestamp
- Use `INSERT OR IGNORE` + UNIQUE constraint for deduplication
- Keep schema normalized via ISO 4217 numeric currency reference table
- NBU rates are used for display and not persisted in SQLite

## Docker Best Practices
- Keep bot and backup responsibilities isolated in separate images
- Use slim Python base image
- Persist data through mounted `data` directory
- Keep hadolint ignore list aligned with repository workflows (DL3008, SC3009, DL3013)

# Project Structure

```
exchange-rate-telegram-bot/
├── .github/
│   ├── workflows/
│   │   ├── tests.yml              # Lint + build for dev branches
│   │   ├── release.yml            # Release/tag/build on main
│   │   └── docker-lint.yml        # Dockerfile + compose lint
│   ├── dependabot.yml
│   └── copilot-instructions.md
├── backup/
│   ├── Dockerfile                 # Backup sidecar image
│   └── requirements.txt           # Backup dependencies
├── bot/
│   ├── main.py                    # Telegram bot runtime
│   ├── database.py                # SQLite storage module
│   ├── backup.py                  # S3 backup script
│   └── scripts/
│       └── migrate_csv_to_db.py   # CSV -> SQLite migration utility
├── data/
│   └── PLACEHOLDER                # Volume mount target for db/csv files
├── docs/
│   ├── DATABASE_USAGE.md          # Schema and query examples
│   └── DATABASE_AND_BACKUP.md     # WAL/autovacuum/backup design notes
├── .env.example
├── .env.backup.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
├── CHANGELOG.md
└── LICENSE
```

## Key Files

- **bot/main.py**
  - Monobank and NBU fetching
  - Command handlers: `/start`, `/help`, `/rate`, `/mono`, `/nbu`, `/usd`, `/eur`, `/pln`, `/try`, `/calc`
  - Currency conversion (UAH pairs + EUR↔USD)
  - Scheduled polling
  - Optional CSV logging
  - Optional SQLite logging via `DB_ENABLED`

- **bot/database.py**
  - SQLite schema initialization
  - Currency lookup table management
  - Batch insert with deduplication
  - WAL/pragma tuning and backup helpers

- **bot/backup.py**
  - Safe SQLite backup creation
  - Upload to S3-compatible storage
  - Retention cleanup
  - Scheduled and one-shot modes

- **bot/scripts/migrate_csv_to_db.py**
  - Imports legacy CSV history into SQLite
  - Validates and deduplicates source rows
  - Supports dry-run mode

- **.env.example**
  - `BOT_TOKEN` (required)
  - `PULL_INTERVAL` (optional, valid 15-3600, default 300)
  - `LOG_RATE` (optional)
  - `DB_ENABLED` (optional)
  - `DB_PATH` (optional, default `data/exchange_rates.db`)
  - `LOG_LEVEL` (optional)

- **.env.backup.example**
  - `BACKUP_ENABLED`
  - `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
  - Optional `S3_ENDPOINT_URL`, `S3_PREFIX`, `S3_REGION`
  - Optional `BACKUP_INTERVAL`, `BACKUP_RETENTION`, `BACKUP_MODE`
  - Optional `DB_PATH`, `LOG_LEVEL`

# CI/CD and Release Notes

- `tests.yml`: runs on `dev*` branches and PRs to `dev*`; installs bot and backup dependencies, runs Black and pylint, builds bot and backup images, pushes `:dev` images on `development` branch
- `docker-lint.yml`: lints Dockerfile and docker-compose on `main` and `dev*`
- `release.yml`: runs on `main`, tags release, updates image tags in compose file, builds and publishes both `xratebot` and `xratebot-backup` images to GHCR

# Resources and References

## External Documentation
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [python-telegram-bot Documentation](https://docs.python-telegram-bot.org/)
- [Monobank API Documentation](https://api.monobank.ua/docs/)
- [NBU API Documentation](https://bank.gov.ua/ua/open-data/api-dev)
- [PEP 8](https://peps.python.org/pep-0008/)
- [Black Code Style](https://black.readthedocs.io/)

## Repository Links
- [Issues](https://github.com/yurnov/exchange-rate-telegram-bot/issues)
- [Pull Requests](https://github.com/yurnov/exchange-rate-telegram-bot/pulls)
- [Live Bot](https://t.me/mono_rate_bot)
- [SQLite storage issue (historical)](https://github.com/yurnov/exchange-rate-telegram-bot/issues/18)

## Development Resources
- Bot image: `ghcr.io/yurnov/xratebot`
- Backup image: `ghcr.io/yurnov/xratebot-backup`
- CI workflows build/lint both bot and backup paths
