# Simple Exchange Rate Telegram Bot
![python-version](https://img.shields.io/badge/python-3.12-blue.svg)
[![python-telegram-bot](https://img.shields.io/badge/Python-Telegram_bot-blue.svg)](https://github.com/python-telegram-bot/python-telegram-bot)
[![license](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Publish image](https://github.com/yurnov/exchange-rate-telegram-bot/actions/workflows/publish.yml/badge.svg)](https://github.com/yurnov/exchange-rate-telegram-bot/actions/workflows/publish.yml)

A [Telegram bot](https://core.telegram.org/bots/api) that running in Docker container with minimal config and gather exchange rate for few currenies from [Monobank API](https://api.monobank.ua/).

## Prerequisites
- Docker engine on x86_64 host
- A [Telegram bot](https://core.telegram.org/bots#6-botfather) and its token (see [tutorial](https://core.telegram.org/bots/tutorial#obtain-your-bot-token)

## Configuration
Just provide `BOT_TOKEN` in the `.env` file, you may use `.env.example` as example. Alnetratively you may provide `BOT_TOKEN` as enviromental variable.

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
#### Ready-to-use Docker images
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

## Disclaimer
This is a personal project and is not affiliated with Monobank/Universal Bank and Telegram Messenger Inc.

## License
Files included in this repository is avaliable under terms of [MIT license](LICENSE). external dependency, such as [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) or [requests](https://github.com/psf/requests) is avaliable under their own licenses.




ghcr.io/yurnov/xratebot:latest