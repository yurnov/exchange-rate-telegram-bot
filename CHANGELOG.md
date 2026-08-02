# Changelog

## v0.10.0

[Added support of backup sidecar container](https://github.com/yurnov/exchange-rate-telegram-bot/pull/48)

Backup sidecar tuned for low-resource hosts:
- Snapshots are taken with `VACUUM INTO` (smaller output, not restarted by concurrent writes) and staged on a mounted volume instead of the container layer
- Page cache is flushed and released while writing, so a large snapshot no longer stalls the whole host in writeback
- Snapshots are gzipped (level 1 by default) directly into the upload stream, so the data is read once and no compressed copy is written to disk
- Uploads use a single transfer thread with bounded buffers instead of boto3's ten concurrent parts
- The process runs at `nice 10` and the lowest best-effort I/O priority, and the container has memory, CPU and PID caps
- Old backups are deleted in batches, or left to an S3 lifecycle rule with `BACKUP_RETENTION=0`
- Added per-phase timings, a JSON status file, an optional log file, a hard timeout and clean `SIGTERM` handling

## v0.9.0

[Added support of Turkish lira](https://github.com/yurnov/exchange-rate-telegram-bot/pull/46)

## v0.8.0

[Support of SQLite database implemented](https://github.com/yurnov/exchange-rate-telegram-bot/pull/25)

## v0.7.0

[3PP lifecycle](https://github.com/yurnov/exchange-rate-telegram-bot/pull/28):
- Python 3.14
- Dependency updated
- Dockerfile refactored to use requirements.txt for correct Dependabot action

## v0.6.0

[EUR<=>USD conversion support added](https://github.com/yurnov/exchange-rate-telegram-bot/pull/25)

## v0.5.0

New `/calc` command - Parses input like `/calc 100 USD` to UAH and returns converted amount with rate used [#22](https://github.com/yurnov/exchange-rate-telegram-bot/pull/22)

## v0.4.0

NBU rates added

## v0.3.0

[Optinal logging exchange rates to CSV file](https://github.com/yurnov/exchange-rate-telegram-bot/issues/4)
Log level for application log is configurable

## v0.2.1

Code is same as `v0.2.0`, just fix in README.md

## v0.2.0

Instead of individual API call for each `/rate` bot command rates pulled in configurable interval

## 0.1.1

Version with fix of `/start` answer

## 0.1.0 (yanked)

Version yanked due to code error

## [pre-0.1.0](c218c5c43a8d3a3c477740b424e7d8ea53e487cf)

First working version