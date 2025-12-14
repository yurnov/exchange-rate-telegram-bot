# Project Overview

This repository contains an Exchange Rate Telegram Bot - a lightweight Python application running in a Docker container that provides real-time exchange rates for USD 🇺🇸, EUR 🇪🇺, and PLN 🇵🇱 to Ukrainian Hryvnia (UAH 🇺🇦). The bot fetches data from both Monobank API and National Bank of Ukraine (NBU) API, offering users current market rates, official rates, and built-in currency conversion capabilities.

The bot is designed to be minimal, easy to deploy, and efficient, making it ideal for personal use or small communities interested in Ukrainian currency exchange rates.

## Development Status

- **Active Development Branch**: `development` - Use this as the base branch for new features and changes
- **Stable Branch**: `main` - Production-ready releases only
- **Current Focus**: Implementing SQLite time-series database storage (Issue #18) to replace/extend CSV-based logging with support for all available currency pairs (~130 total from Monobank and NBU APIs)

# Technology Stack

## Current Stack
- **Language**: Python 3.14
- **Framework**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v22.5
- **HTTP Client**: requests v2.32.5
- **Configuration**: python-dotenv v1.2.1 for environment management
- **Scheduling**: schedule v1.2.2 for periodic rate updates
- **Containerization**: Docker (based on Python 3.14-slim image)
- **APIs**:
  - [Monobank API](https://api.monobank.ua/docs/) - for market exchange rates (buy/sell), ~100 currency pairs
  - [NBU API](https://bank.gov.ua/ua/open-data/api-dev) - for official exchange rates, ~30 currencies

## Planned Additions (See Issue #18)
- **Database**: SQLite (embedded, built-in to Python)
- **Orchestration**: Docker Compose for volume management
- **Data Storage**: Time-series database for historical exchange rate data with intelligent deduplication

# Coding Guidelines

## Code Style
- Follow PEP 8 guidelines
- Use [Black](https://github.com/psf/black) for code formatting with the following settings:
  - Line length: 120 characters
  - Skip string normalization: enabled (`--skip-string-normalization`)
- Disable pylint checks for R (refactoring), C (convention), and W1203 (logging-fstring-interpolation)
- Keep functions focused and maintainable

## Comments and Documentation
- Add docstrings for new functions
- Keep comments clear and concise
- Use English for all code, comments, and documentation

## Error Handling
- Use broad exception handling where appropriate with proper logging
- Always log errors with meaningful context
- Provide user-friendly error messages in bot responses

## Configuration
- Use environment variables for all configurable parameters
- Provide sensible defaults for optional configuration
- Validate configuration values on startup

## Database Design (Issue #18)
- Use SQLite for time-series storage (built-in to Python, no extra dependencies)
- Store ALL currency pairs from APIs (~130 total), not just displayed currencies
- Implement dual timestamp tracking:
  - `timestamp`: Our polling time (for audit/debug)
  - `api_timestamp`: API's actual update time from the `date` field (authoritative)
- Use `INSERT OR IGNORE` with UNIQUE constraints for automatic deduplication
- Expected storage reduction: 40-60% through timestamp-based deduplication
- Schema: ISO 4217 numeric currency codes with normalized lookup table
- See `docs/IMPLEMENTATION_PLAN.md` for detailed architecture and schema design

## Docker Best Practices
- Keep images minimal and lightweight
- Use Python slim images as base
- Ignore linting rules DL3008, SC3009, DL3013 for Dockerfile

# Project Structure

```
exchange-rate-telegram-bot/
├── .github/                      # GitHub configuration
│   ├── workflows/               # CI/CD workflows
│   │   ├── tests.yml           # Development branch testing
│   │   └── release.yml         # Main branch release workflow
│   ├── dependabot.yml          # Dependency update configuration
│   └── copilot-instructions.md # This file - Copilot configuration
├── bot/                         # Application code
│   ├── main.py                 # Main bot application with all handlers
│   └── database.py             # (Planned) SQLite database module
├── docs/                        # Documentation (development branch)
│   └── IMPLEMENTATION_PLAN.md  # Detailed plan for Issue #18 (SQLite storage)
├── scripts/                     # (Planned) Utility scripts
│   └── migrate_csv_to_db.py   # CSV to SQLite migration script
├── data/                        # (Planned) Data directory (volume mount)
│   ├── exchange_rates.db      # SQLite database
│   └── exchange_rates.csv     # CSV file (if LOG_RATE=True)
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore patterns
├── Dockerfile                  # Docker container definition
├── docker-compose.yml          # (Planned) Docker Compose configuration
├── requirements.txt            # Python dependencies
├── README.md                   # User documentation
├── CHANGELOG.md               # Version history
└── LICENSE                    # MIT License
```

## Key Files

- **bot/main.py**: Contains all bot logic including:
  - Exchange rate fetching from Monobank and NBU APIs
  - Telegram command handlers (`/start`, `/help`, `/rate`, `/mono`, `/nbu`, `/usd`, `/eur`, `/pln`, `/calc`)
  - Currency conversion logic
  - Scheduled rate updates
  - Optional CSV logging functionality

- **.env.example**: Template for required environment variables
  - `BOT_TOKEN` (required): Telegram bot token
  - `PULL_INTERVAL` (optional): Rate update interval (15-3600 seconds, default: 300)
  - `LOG_RATE` (optional): Enable CSV logging (True/False, default: False)
  - `LOG_LEVEL` (optional): Logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL, default: INFO)
  - `DB_ENABLED` (planned): Enable SQLite database logging (True/False, default: False)
  - `DB_PATH` (planned): Path to SQLite database file (default: data/exchange_rates.db)

- **docs/IMPLEMENTATION_PLAN.md** (development branch): Comprehensive technical documentation for Issue #18
  - Database selection analysis (SQLite vs. InfluxDB vs. QuestDB)
  - Schema design with dual timestamp approach
  - Per-pair timestamp optimization strategy
  - Implementation phases and acceptance criteria
  - SQL query examples for analytics and charting
  - Future enhancement roadmap (Grafana integration, API endpoints)

# Resources and References

## External Documentation
- [Telegram Bot API](https://core.telegram.org/bots/api) - Official Telegram Bot API documentation
- [python-telegram-bot Documentation](https://docs.python-telegram-bot.org/) - Framework documentation
- [Monobank API Documentation](https://api.monobank.ua/docs/) - Monobank API reference
- [NBU API Documentation](https://bank.gov.ua/ua/open-data/api-dev) - National Bank of Ukraine API reference
- [PEP 8](https://peps.python.org/pep-0008/) - Python style guide
- [Black Code Style](https://black.readthedocs.io/) - Black formatter documentation

## Repository Links
- [Issues](https://github.com/yurnov/exchange-rate-telegram-bot/issues) - Bug reports and feature requests
- [Pull Requests](https://github.com/yurnov/exchange-rate-telegram-bot/pulls) - Code contributions
- [Live Bot](https://t.me/mono_rate_bot) - Hosted instance for testing
- [Issue #18](https://github.com/yurnov/exchange-rate-telegram-bot/issues/18) - SQLite time-series storage implementation (active development)
- [Implementation Plan](https://github.com/yurnov/exchange-rate-telegram-bot/blob/development/docs/IMPLEMENTATION_PLAN.md) - Detailed technical documentation for database implementation

## Development Resources
- Docker images are published to [GitHub Container Registry](https://github.com/yurnov/exchange-rate-telegram-bot/pkgs/container/xratebot)
- CI/CD workflows automatically build, lint, and publish images
- Use `ghcr.io/yurnov/xratebot:latest` for the latest stable version
- Use `ghcr.io/yurnov/xratebot:dev` for development versions
