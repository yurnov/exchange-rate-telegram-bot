# Exchange Rate Telegram Bot

![python-version](https://img.shields.io/badge/python-3.12-blue.svg)
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
- **CSV Logging**: Optional logging of exchange rates with timestamps
- **Minimal Configuration**: Only requires a bot token to get started
- **Docker-Ready**: Runs in a lightweight container based on Python 3.12-slim

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
| `/calc` | Convert currencies (e.g., `/calc 100 USD to UAH`) |

### Currency Converter Usage

Convert amounts between currencies using the `/calc` command:

```
/calc 100 USD to UAH
/calc 1000 UAH to EUR
/calc 500 PLN to UAH
```

**Note**: All conversions must involve UAH (to or from). The bot uses Monobank sell rates when converting foreign currency to UAH, and buy rates when converting UAH to foreign currency.

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
| `LOG_LEVEL` | Application logging level | `INFO` | `DEBUG/INFO/WARNING/ERROR/CRITICAL` |

**Important**: Setting `PULL_INTERVAL` below 30 seconds is not recommended as it may trigger rate limiting from Monobank API (`{'errorDescription': 'Too many requests'}`).

#### CSV Logging Format

When `LOG_RATE=True`, the bot creates `exchange_rates.csv` with the following format:
```
Date Time, USD Buy Rate, USD Sell Rate, EUR Buy Rate, EUR Sell Rate, PLN Exchange Rate
2025-11-30 10:15:30,41.20,41.60,43.50,44.00,10.25
```


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

### Option 3: Try the Live Bot

Start a conversation with the hosted bot: [@mono_rate_bot](https://t.me/mono_rate_bot)

## Technical Details

### Architecture

- **Language**: Python 3.12
- **Framework**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v20.7
- **APIs**: 
  - [Monobank API](https://api.monobank.ua/docs/) - for market exchange rates
  - [NBU API](https://bank.gov.ua/ua/open-data/api-dev) - for official exchange rates
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
│   └── main.py           # Main bot application
├── .env.example          # Environment variables template
├── Dockerfile            # Docker container definition
├── CHANGELOG.md          # Version history
├── LICENSE               # MIT License
└── README.md            # This file
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

