# Project Overview

This repository contains an Exchange Rate Telegram Bot - a lightweight Python application running in a Docker container that provides real-time exchange rates for USD 🇺🇸, EUR 🇪🇺, and PLN 🇵🇱 to Ukrainian Hryvnia (UAH 🇺🇦). The bot fetches data from both Monobank API and National Bank of Ukraine (NBU) API, offering users current market rates, official rates, and built-in currency conversion capabilities.

The bot is designed to be minimal, easy to deploy, and efficient, making it ideal for personal use or small communities interested in Ukrainian currency exchange rates.

# Technology Stack

- **Language**: Python 3.14
- **Framework**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v22.5
- **HTTP Client**: requests v2.32.5
- **Configuration**: python-dotenv v1.2.1 for environment management
- **Scheduling**: schedule v1.2.2 for periodic rate updates
- **Containerization**: Docker (based on Python 3.14-slim image)
- **APIs**:
  - [Monobank API](https://api.monobank.ua/docs/) - for market exchange rates (buy/sell)
  - [NBU API](https://bank.gov.ua/ua/open-data/api-dev) - for official exchange rates

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
│   └── main.py                 # Main bot application with all handlers
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore patterns
├── Dockerfile                  # Docker container definition
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

## Development Resources
- Docker images are published to [GitHub Container Registry](https://github.com/yurnov/exchange-rate-telegram-bot/pkgs/container/xratebot)
- CI/CD workflows automatically build, lint, and publish images
- Use `ghcr.io/yurnov/xratebot:latest` for the latest stable version
- Use `ghcr.io/yurnov/xratebot:dev` for development versions
