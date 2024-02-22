# Simple Exchange Rate Telegram Bot
![python-version](https://img.shields.io/badge/python-3.12-blue.svg)
[![python-telegram-bot](https://img.shields.io/badge/Python-Telegram_bot-blue.svg)](https://github.com/python-telegram-bot/python-telegram-bot)
[![license](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Publish image](https://github.com/yurnov/exchange-rate-telegram-bot/actions/workflows/release.yml/badge.svg)](https://github.com/yurnov/exchange-rate-telegram-bot/actions/workflows/release.yml)

A [Telegram bot](https://core.telegram.org/bots/api) that running in Docker container with minimal config and gather exchange rate for few currenies from [Monobank API](https://api.monobank.ua/).

## Prerequisites
- Docker engine on x86_64 host
- A [Telegram bot](https://core.telegram.org/bots#6-botfather) and its token (see [tutorial](https://core.telegram.org/bots/tutorial#obtain-your-bot-token))

## Configuration
Just provide `BOT_TOKEN` in the `.env` file, you may use `.env.example` as example. Alnetratively you may provide `BOT_TOKEN` as enviromental variable.

Optionally you can provide a `PULL_INTERVAL` in seconds to update rates every defined amount of seconds. Default value is 300. Value lower that 20 is not accepted, and lower that 30 is not recommended as it may lead throtling from Monobank side with answers like `{'errorDescription': 'Too many requests'}`

Optionally bot can log exchange rates into CSV file `exchange_rates.csv`. Set `LOG_RATE` to `True` to enable logging.

Default log level in INFO, you can override it with `LOG_LEVEL` varaible.

## Running
### Build own Docker image

Clone the repository and navigate to the project directory:

```shell
git clone git@github.com:yurnov/exchange-rate-telegram-bot.git
cd exchange-rate-telegram-bot
```

Build image

```shell
docker build . -t exchange-rate-telegram-bot
```

Run container

```shell
docker run --rm -d --env-file .env exchange-rate-telegram-bot
```
### Ready-to-use Docker images
You can also use the Docker image from GitHub Container Registry:
```shell
docker pull ghcr.io/yurnov/xratebot:latest
docker run --rm -d --env-file .env ghcr.io/yurnov/xratebot:latest
```

Alternatively, you may use enviroment varaible:
```shell
docker pull ghcr.io/yurnov/xratebot:latest
docker run --rm -d -e BOT_TOKEN="1111111111:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" ghcr.io/yurnov/xratebot:latest
```

Do not forget to bind (mount) a CSV file in case when exchange rates loggin is enabled with `LOG_RATE`:
```shell
touch exchange_rates.csv && \
docker run --rm -it --env-file .env -v ./exchange_rates.csv:/bot/exchange_rates.csv ghcr.io/yurnov/xratebot:latest
```

### Ready-to-use Telegram Bot
Start telegram conversation with [mono_rate_bot](https://t.me/mono_rate_bot) 

## Disclaimer
This is a personal project and is not affiliated with Monobank/Universal Bank and Telegram Messenger Inc.

## License
Files included in this repository is avaliable under terms of [MIT license](LICENSE). external dependency, such as [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) or [requests](https://github.com/psf/requests) is avaliable under their own licenses.
