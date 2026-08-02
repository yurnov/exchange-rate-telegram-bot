# Exchange Rate Telegram Bot

![python-version](https://img.shields.io/badge/python-3.14-blue.svg)
[![python-telegram-bot](https://img.shields.io/badge/Python-Telegram_bot-blue.svg)](https://github.com/python-telegram-bot/python-telegram-bot)
[![license](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Publish image](https://github.com/yurnov/exchange-rate-telegram-bot/actions/workflows/release.yml/badge.svg)](https://github.com/yurnov/exchange-rate-telegram-bot/actions/workflows/release.yml)

A lightweight [Telegram bot](https://core.telegram.org/bots/api) running in a Docker container that provides real-time exchange rates for USD 🇺🇸, EUR 🇪🇺, PLN 🇵🇱, and TRY 🇹🇷 to Ukrainian Hryvnia (UAH 🇺🇦). The bot fetches data from both [Monobank API](https://api.monobank.ua/) and [National Bank of Ukraine (NBU) API](https://bank.gov.ua/).

## Features

- **Real-time Exchange Rates**: Fetches current rates from Monobank and NBU APIs
- **Multiple Data Sources**: Compare rates from Monobank (buy/sell) and NBU (official)
- **Currency Converter**: Built-in calculator for currency conversions
- **Automatic Updates**: Configurable rate refresh interval (15-3600 seconds)
- **CSV Logging**: Optional logging of exchange rates with timestamps
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
| `/try` | Get TRY exchange rates (all sources) |
| `/calc` | Convert currencies (e.g., `/calc 100 USD to UAH`, `/calc 100 EUR to USD`) |

### Currency Converter Usage

Convert amounts between currencies using the `/calc` command:

```
/calc 100 USD to UAH
/calc 1000 UAH to EUR
/calc 500 PLN to UAH
/calc 100 TRY to UAH
/calc 500 UAH to TRY
/calc 100 EUR to USD
/calc 200 USD to EUR
```

**Note**: Conversions must involve UAH (to or from), or be between EUR and USD. The bot uses Monobank sell rates when converting foreign currency to UAH (for USD and EUR), and buy rates when converting UAH to foreign currency. For PLN and TRY, a single cross rate is used for conversions to/from UAH. EUR ↔ USD conversions use the direct exchange rate provided by Monobank.

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

#### CSV Logging Format (Legacy)

When `LOG_RATE=True`, the bot creates `exchange_rates.csv` with the following format:
```
Date Time, USD Buy Rate, USD Sell Rate, EUR Buy Rate, EUR Sell Rate, PLN Exchange Rate
2025-11-30 10:15:30,41.20,41.60,43.50,44.00,10.25
```
However, legacy CSV logging is not recommended for new deployments. SQLite database storage is suggested instead for better performance and data integrity.

<details>
<summary>Migration from CSV to SQLite Database</summary>

The Docker image includes a migration script (`migrate_csv_to_db.py`) to convert existing CSV data to SQLite format.

**Basic usage with defaults:**
```bash
python /bot/scripts/migrate_csv_to_db.py
```

**Dry run to test migration:**
```bash
python /bot/scripts/migrate_csv_to_db.py --dry-run
```

**Custom file paths:**
```bash
python /bot/scripts/migrate_csv_to_db.py --csv-file /custom/path/rates.csv --db-file /custom/path/db.sqlite
```

**All options combined:**
```bash
python /bot/scripts/migrate_csv_to_db.py --csv-file ../data/old_rates.csv --dry-run --verbose
```

</details>

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

### Option 3: Use Docker Compose (Recommended)

Docker Compose provides a convenient way to manage the bot with persistent data storage.

1. Create a `.env` file with your bot token (use `.env.example` as template):

```bash
cp .env.example .env
# Edit .env and add your BOT_TOKEN
```

2. Create a `data` directory for persistent storage:

```bash
mkdir -p data
```

3. Start the bot using Docker Compose:

```bash
docker compose up -d
```

4. View logs:

```bash
docker compose logs -f bot
```

5. Stop the bot:

```bash
docker compose down
```

The Docker Compose configuration automatically:
- Mounts the `./data` directory to persist database and CSV files
- Loads environment variables from `.env` file
- Restarts the container automatically unless manually stopped
- Includes a health check to monitor bot status

### Running with CSV Logging

When exchange rate logging is enabled (`LOG_RATE=True`), the bot will save exchange rates to a CSV file.

**With Docker Compose:** The `./data` directory is already mounted, so CSV files will be automatically persisted in `./data/exchange_rates.csv`.

**With standalone Docker:** Mount a CSV file to persist data:

```bash
touch exchange_rates.csv
docker run --rm -d \
  --env-file .env \
  -v ./exchange_rates.csv:/bot/exchange_rates.csv \
  ghcr.io/yurnov/xratebot:latest
```

### Option 4: Try the Live Bot

Start a conversation with the hosted bot: [@mono_rate_bot](https://t.me/mono_rate_bot)

## Database Backup

The bot includes an optional backup container that can securely upload SQLite database snapshots to any S3-compatible object storage.

### Enabling and Configuring Backup

1. Copy the example backup environment file:

```bash
cp .env.backup.example .env.backup
```

2. Edit `.env.backup` and configure your credentials:
   - Set `BACKUP_ENABLED=true`
   - Define S3 configuration (`S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`)
   - If using an alternative S3 provider (like MinIO, Cloudflare R2, DigitalOcean), uncomment and configure `S3_ENDPOINT_URL`

### Running Backup Once

To execute a single backup instance and promptly exit (e.g., when executed from an external cron job), use the `once` backup mode.

**Using Docker Compose:**

```bash
docker compose run --rm -e BACKUP_MODE=once backup
```

**Using Docker CLI:**

```bash
docker run --rm \
  --env-file .env.backup \
  -e BACKUP_MODE=once \
  -e BACKUP_TMPDIR=/backup/work \
  -e BACKUP_STATUS_FILE=/backup/work/last_backup.json \
  --memory 192m --cpus 0.5 \
  -v ./data:/bot/data:ro \
  -v exchange-rate-telegram-bot_backup-work:/backup/work \
  ghcr.io/yurnov/xratebot-backup:latest
```

> The data volume is mounted read-only. SQLite needs the `-shm` file to read a database in WAL mode and cannot create one on a read-only mount, so the bot container must be running (it holds that file open). If it is not, the backup fails with `attempt to write a readonly database`.

### Running Scheduled Backup

To run the backup container continuously to process backups on a set schedule (defined by the `BACKUP_INTERVAL` variable), run Docker compose with the backup profile:

```bash
docker compose --profile backup up -d
```

### Backup Resource Usage

The backup is designed to stay out of the way on a small VM (512 MiB RAM, one shared vCPU), where a naive "copy the database, then upload it" backup can drive the load average into the double digits and make the host unreachable. What it does:

| Behaviour | Why it matters |
| --- | --- |
| `VACUUM INTO` snapshot (`BACKUP_METHOD`) | Skips free pages, so the snapshot is smaller than the database, and — unlike the online backup API — it is never restarted from scratch when the bot writes mid-copy |
| Snapshot staged on a mounted volume (`BACKUP_TMPDIR`) | Keeps a multi-hundred-megabyte temporary file out of the container layer, and off `tmpfs`, where it would consume RAM |
| `fsync` + `posix_fadvise(DONTNEED)` every 64 MiB (`BACKUP_DROP_CACHE`) | The kernel never accumulates the whole snapshot as dirty pages, so it never stalls the host — including `sshd` — while flushing them |
| Gzip streamed into the upload (`BACKUP_COMPRESS`, `BACKUP_COMPRESS_LEVEL`) | The snapshot is read exactly once and no compressed copy is written to disk. Typically a 5-10x smaller upload for very little CPU; a shorter upload is also less TLS work. On a slow disk, avoiding the extra read and write matters more than the compression itself |
| Single upload thread with bounded buffers (`BACKUP_UPLOAD_CONCURRENCY`, `BACKUP_MULTIPART_CHUNKSIZE`) | boto3 defaults to 10 concurrent 8 MiB parts — ~80 MiB of buffers plus TLS on ten threads, which is enough to get the process OOM-killed before it can log anything |
| `nice 10` and the lowest best-effort I/O priority (`BACKUP_NICE`, `BACKUP_IONICE`) | The backup yields to the bot without being starved. Higher niceness is counter-productive: at 19 the process is weighted 15 against 1024 for a normal-priority one, so it loses ~70x on a contended CPU |
| Memory and CPU caps in `docker-compose.yml` | If a backup no longer fits, it is OOM-killed inside its own cgroup instead of taking the host down |
| Batched retention deletes, or none at all (`BACKUP_RETENTION`) | One `DeleteObjects` call instead of one request per object; `BACKUP_RETENTION=0` hands expiry to an S3 lifecycle rule, which costs the host nothing |
| Hard timeout (`BACKUP_TIMEOUT`) | A stalled upload fails and is retried instead of hanging forever |

For a ~0.5 GB database this typically means around 50-100 MiB uploaded per run, a peak RSS well under 100 MiB, and one pass over the data rather than three — which on a slow disk is the difference between a backup that finishes in under a minute and one that appears to hang.

Staging needs free space for the snapshot itself (never more than the database); the compressed copy only ever exists in memory, a chunk at a time.

Tuning knobs live in `.env.backup`; the container's memory and CPU caps live in `docker-compose.yml`:

```yaml
    cpus: 0.75
    mem_limit: 320m
    memswap_limit: 320m
```

Page cache counts towards `mem_limit`, so a limit that is too tight forces the cgroup into constant reclaim while the snapshot streams through it, which is slower than having no limit at all. 320 MiB leaves room on a 512 MiB host; do not drop it much below that.

### Troubleshooting Backups

Every cycle writes a JSON summary and a log file to the `backup-work` volume, so a failure can be diagnosed after the fact — useful when the host was too busy to accept an ssh connection at the time:

```bash
docker run --rm -v exchange-rate-telegram-bot_backup-work:/w alpine cat /w/last_backup.json
docker run --rm -v exchange-rate-telegram-bot_backup-work:/w alpine tail -50 /w/backup.log
```

The `phase` field of `last_backup.json` (`snapshot`, `compress`, `upload`, `cleanup`, `done`) shows where a run stopped. If the file says nothing at all and the container exited unexpectedly, the process was killed rather than failing:

```bash
docker inspect --format '{{.State.OOMKilled}} {{.State.ExitCode}}' exchange-rate-bot-backup
dmesg -T | grep -i -E 'oom|killed process'
```

## Technical Details

### Architecture

- **Language**: Python 3.14
- **Framework**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
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
├── backup/
│   ├── Dockerfile        # Backup container definition
│   └── requirements.txt  # Backup sidecar dependencies (boto3)
├── bot/
│   ├── main.py           # Main bot application
│   └── backup.py         # Database backup script
├── .env.example          # Environment variables template
├── .env.backup.example   # Backup environment variables template
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

