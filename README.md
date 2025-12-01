# Exchange Rate Telegram Bot

![python-version](https://img.shields.io/badge/python-3.14-blue.svg)
[![python-telegram-bot](https://img.shields.io/badge/Python-Telegram_bot-blue.svg)](https://github.com/python-telegram-bot/python-telegram-bot)
[![license](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Publish image](https://github.com/yurnov/exchange-rate-telegram-bot/actions/workflows/release.yml/badge.svg)](https://github.com/yurnov/exchange-rate-telegram-bot/actions/workflows/release.yml)

A lightweight [Telegram bot](https://core.telegram.org/bots/api) running in a Docker container that provides real-time exchange rates for USD 🇺🇸, EUR 🇪🇺, and PLN 🇵🇱 to Ukrainian Hryvnia (UAH 🇺🇦). The bot fetches data from both [Monobank API](https://api.monobank.ua/) and [National Bank of Ukraine (NBU) API](https://bank.gov.ua/).

## Features

- **Real-time Exchange Rates**: Fetches current rates from Monobank and NBU APIs
- **Multiple Data Sources**: Compare rates from Monobank (buy/sell) and NBU (official)
- **Currency Converter**: Built-in calculator for currency conversions
- **Automatic Updates**: Configurable rate refresh interval (15-3600 seconds)
- **Historical Data Storage**: Optional SQLite database for storing ALL exchange rates (100+ currency pairs)
- **CSV Logging**: Optional CSV logging for backward compatibility (USD, EUR, PLN only)
- **Data Migration**: Script to migrate existing CSV data to database
- **Minimal Configuration**: Only requires a bot token to get started
- **Docker-Ready**: Runs in a lightweight container based on Python 3.14-slim

## Prerequisites

- Docker engine on x86_64 host
- A [Telegram bot](https://core.telegram.org/bots#6-botfather) and its token (see [tutorial](https://core.telegram.org/bots/tutorial#obtain-your-bot-token))

## Available Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and get a welcome message |
| `/help` | Display available commands and usage instructions |
| `/rate` | Get all exchange rates (Monobank buy/sell + NBU official) |
| `/mono` | Get Monobank exchange rates only |
| `/nbu` | Get NBU official exchange rates only |
| `/usd` | Get USD exchange rates (all sources) |
| `/eur` | Get EUR exchange rates (all sources) |
| `/pln` | Get PLN exchange rates (all sources) |
| `/calc` | Convert currencies (e.g., `/calc 100 USD to UAH`, `/calc 100 EUR to USD`) |

### Currency Converter Usage

Convert amounts between currencies using the `/calc` command:

```
/calc 100 USD to UAH
/calc 1000 UAH to EUR
/calc 500 PLN to UAH
/calc 100 EUR to USD
/calc 200 USD to EUR
```

**Note**: Conversions must involve UAH (to or from), or be between EUR and USD. The bot uses Monobank sell rates when converting foreign currency to UAH, and buy rates when converting UAH to foreign currency. EUR ↔ USD conversions use the direct exchange rate provided by Monobank.

## Configuration

### Required Configuration

Create a `.env` file in the project directory (you can use `.env.example` as a template):

```bash
BOT_TOKEN=your_bot_token_here
```

Alternatively, provide `BOT_TOKEN` as an environment variable when running the container.

### Optional Configuration

| Variable | Description | Default | Valid Range |
|----------|-------------|---------|-------------|
| `PULL_INTERVAL` | Rate update interval in seconds | `300` | `15-3600` |
| `LOG_RATE` | Enable CSV logging of exchange rates | `False` | `True/False` |
| `DB_ENABLED` | Enable SQLite database logging | `False` | `True/False` |
| `DB_PATH` | Path to SQLite database file | `data/exchange_rates.db` | File path |
| `LOG_LEVEL` | Application logging level | `INFO` | `DEBUG/INFO/WARNING/ERROR/CRITICAL` |

**Important**: Setting `PULL_INTERVAL` below 30 seconds is not recommended as it may trigger rate limiting from Monobank API (`{'errorDescription': 'Too many requests'}`).

#### CSV Logging Format (Legacy)

When `LOG_RATE=True`, the bot creates `exchange_rates.csv` with the following format:
```
Date Time, USD Buy Rate, USD Sell Rate, EUR Buy Rate, EUR Sell Rate, PLN Exchange Rate
2025-11-30 10:15:30,41.20,41.60,43.50,44.00,10.25
```

#### Database Storage (Recommended)

When `DB_ENABLED=True`, the bot stores ALL exchange rates (100+ currency pairs from Monobank and NBU APIs) in a SQLite database. This enables:

- **Comprehensive Data**: Stores all available currency pairs, not just USD, EUR, PLN
- **Historical Analysis**: Query rates for any time period
- **Trend Analysis**: Perform SQL queries for analytics and charting
- **Data Export**: Easy export to CSV, JSON, or connect to Grafana

**Database Schema**:
- `currencies` table: ISO 4217 currency codes reference
- `exchange_rates` table: Historical rates with timestamps

**Storage Estimate**: ~7 GB for 5 years of complete data (~100 currency pairs, 5-minute intervals)


## Running

### Option 1: Build Your Own Docker Image

Clone the repository and navigate to the project directory:

```bash
git clone https://github.com/yurnov/exchange-rate-telegram-bot.git
cd exchange-rate-telegram-bot
```

Build the image:

```bash
docker build -t exchange-rate-telegram-bot .
```

Run the container:

```bash
docker run --rm -d --env-file .env exchange-rate-telegram-bot
```

### Option 2: Use Pre-built Docker Image

Pull and run the latest image from GitHub Container Registry:

```bash
docker pull ghcr.io/yurnov/xratebot:latest
docker run --rm -d --env-file .env ghcr.io/yurnov/xratebot:latest
```

Alternatively, provide the token directly as an environment variable:

```bash
docker run --rm -d -e BOT_TOKEN="your_bot_token" ghcr.io/yurnov/xratebot:latest
```

### Running with CSV Logging

When exchange rate logging is enabled (`LOG_RATE=True`), mount a CSV file to persist data:

```bash
touch exchange_rates.csv
docker run --rm -d \
  --env-file .env \
  -v ./exchange_rates.csv:/bot/exchange_rates.csv \
  ghcr.io/yurnov/xratebot:latest
```

### Running with Database (Recommended for Data Analysis)

When database logging is enabled (`DB_ENABLED=True`), mount a data directory to persist the database:

```bash
mkdir -p data
docker run --rm -d \
  --env-file .env \
  -e DB_ENABLED=True \
  -v ./data:/bot/data \
  ghcr.io/yurnov/xratebot:latest
```

### Option 3: Using Docker Compose (Recommended)

The easiest way to run the bot with persistent storage:

```bash
# Clone the repository
git clone https://github.com/yurnov/exchange-rate-telegram-bot.git
cd exchange-rate-telegram-bot

# Create .env file with your configuration
cp .env.example .env
# Edit .env and set BOT_TOKEN, DB_ENABLED=True, etc.

# Run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the bot
docker-compose down
```

The `docker-compose.yml` file automatically mounts the `./data` directory for database persistence.

### Option 4: Try the Live Bot

Start a conversation with the hosted bot: [@mono_rate_bot](https://t.me/mono_rate_bot)

## Data Migration

If you have existing CSV data from previous bot versions, you can migrate it to the SQLite database.

### Migration Script

```bash
# Basic migration
python scripts/migrate_csv_to_db.py \
  --csv-file exchange_rates.csv \
  --db-file data/exchange_rates.db

# Dry run (validate without inserting)
python scripts/migrate_csv_to_db.py \
  --csv-file exchange_rates.csv \
  --db-file data/exchange_rates.db \
  --dry-run

# Verbose output
python scripts/migrate_csv_to_db.py \
  --csv-file exchange_rates.csv \
  --db-file data/exchange_rates.db \
  --verbose
```

**Features**:
- Validates each CSV row before insertion
- Skips malformed rows (common due to API failures)
- Idempotent (re-runnable without duplicates)
- Provides detailed migration statistics

**Note**: The migration script only migrates USD, EUR, and PLN rates from the CSV. Going forward, the database will store all 100+ currency pairs automatically when `DB_ENABLED=True`.

## Querying Historical Data

Once the database is populated, you can query historical exchange rates using SQL:

```bash
# Connect to the database
sqlite3 data/exchange_rates.db

# Get latest USD/UAH rates
SELECT e.timestamp, e.rate_buy, e.rate_sell, e.rate_cross
FROM exchange_rates e
WHERE e.currency_code_a = 840 AND e.currency_code_b = 980
ORDER BY e.timestamp DESC LIMIT 10;

# Get daily average rates for EUR/UAH
SELECT DATE(timestamp) as day, 
       AVG(rate_sell) as avg_sell_rate,
       MIN(rate_sell) as min_rate,
       MAX(rate_sell) as max_rate
FROM exchange_rates 
WHERE currency_code_a = 978 AND currency_code_b = 980
  AND source = 'monobank'
GROUP BY DATE(timestamp)
ORDER BY day DESC;

# List all available currency pairs
SELECT DISTINCT c1.alpha_code || '/' || c2.alpha_code as pair,
       COUNT(*) as data_points
FROM exchange_rates e
JOIN currencies c1 ON e.currency_code_a = c1.code
JOIN currencies c2 ON e.currency_code_b = c2.code
GROUP BY e.currency_code_a, e.currency_code_b
ORDER BY data_points DESC;
```

For more complex queries and analytics examples, see [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

## Technical Details

### Architecture

- **Language**: Python 3.14
- **Framework**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- **Database**: SQLite (built-in, no external dependencies)
- **APIs**: 
  - [Monobank API](https://api.monobank.ua/docs/) - for market exchange rates (~100 currency pairs)
  - [NBU API](https://bank.gov.ua/ua/open-data/api-dev) - for official exchange rates (~30 currencies)
- **Scheduling**: Uses `schedule` library for periodic rate updates
- **Configuration**: `python-dotenv` for environment management
- **HTTP Client**: `requests` library

### Dependencies

```
requests
python-telegram-bot
python-dotenv
schedule
```

### Project Structure

```
exchange-rate-telegram-bot/
├── bot/
│   ├── main.py              # Main bot application
│   └── database.py          # SQLite database module
├── scripts/
│   └── migrate_csv_to_db.py # CSV to SQLite migration script
├── docs/
│   └── IMPLEMENTATION_PLAN.md # Database implementation details
├── data/                    # Data directory (created on first run)
│   └── exchange_rates.db    # SQLite database (when DB_ENABLED=True)
├── .env.example             # Environment variables template
├── docker-compose.yml       # Docker Compose configuration
├── Dockerfile               # Docker container definition
├── CHANGELOG.md             # Version history
├── LICENSE                  # MIT License
└── README.md               # This file
```

## Contributing

Contributions are welcome! Here's how you can help:

### Reporting Issues

- Use the [GitHub Issues](https://github.com/yurnov/exchange-rate-telegram-bot/issues) page to report bugs
- Provide detailed information about the issue, including steps to reproduce
- Include relevant logs and environment details

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Ensure code follows the existing style (we use [Black](https://github.com/psf/black) for formatting)
5. Test your changes thoroughly
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/your-username/exchange-rate-telegram-bot.git
cd exchange-rate-telegram-bot

# Install dependencies (no requirements.txt in repo)
pip install requests python-telegram-bot python-dotenv schedule

# Create .env file with your bot token
cp .env.example .env
# Edit .env and add your BOT_TOKEN

# Run the bot locally
python bot/main.py
```

### Code Style

- Follow PEP 8 guidelines
- Use Black for code formatting
- Add docstrings for new functions
- Keep functions focused and maintainable

## Disclaimer

This is a personal project and is not affiliated with Monobank/Universal Bank or Telegram Messenger Inc.

## License

Files included in this repository are available under the terms of the [MIT License](LICENSE). External dependencies such as [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) and [requests](https://github.com/psf/requests) are available under their own licenses.

