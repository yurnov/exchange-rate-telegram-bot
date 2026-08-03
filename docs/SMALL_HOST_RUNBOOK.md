# Runbook: stabilising a 512 MiB / 1 shared vCPU host

Step-by-step instructions for the smallest DigitalOcean droplet (512 MiB RAM, one
shared vCPU, no swap) running the bot, the backup sidecar and nothing else.

## Symptoms this fixes

`dmesg` shows the OOM killer firing every 30–60 minutes around the clock, killing
`fwupd`, `appstreamcli`, `apt-get`, `apt-check` and `unattended-upgr` (and
occasionally a `python`):

```
Out of memory: Killed process 563185 (appstreamcli) ... anon-rss:87192kB ...
Out of memory: Killed process 563232 (apt-get)      ... anon-rss:87936kB ...
Out of memory: Killed process 566341 (fwupd)        ... anon-rss:88832kB ...
```

Those are Ubuntu's automatic-maintenance jobs, each needing ~85–90 MiB. The kills
are **not caused by the backup** (which runs once a day): the host sits at its
memory ceiling at steady state, so every periodic job tips it over, dies, and is
retried by its systemd timer — which also means security updates never complete.

Separately, roughly **two thirds of the database file was secondary indexes that
nothing reads** (the table is write-only in production), inflating every insert,
checkpoint, snapshot and upload. This runbook removes them.

Do the steps in order; each is independently useful.

## Step 1 — Add swap (biggest single fix)

DigitalOcean droplets ship without swap, so every memory spike is fatal instead of
merely slow:

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Prefer reclaiming page cache over swapping processes out
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swap.conf
sudo sysctl -p /etc/sysctl.d/99-swap.conf
```

Verify:

```bash
swapon --show   # should list /swapfile, 1G
free -h         # Swap line no longer 0B
```

> DigitalOcean's docs discourage swap to spare SSD wear. On a 512 MiB droplet the
> trade-off is clearly worth it: with `vm.swappiness=10` the swap is touched only
> under real pressure, exactly when the alternative is the OOM killer.

## Step 2 — Remove the maintenance jobs being killed anyway

`fwupd` distributes firmware updates — pointless inside a VM. `appstream` and
`update-notifier-common` refresh desktop-oriented package metadata:

```bash
sudo systemctl mask fwupd.service fwupd-refresh.timer
sudo apt-get purge -y appstream update-notifier-common
```

**Keep `unattended-upgrades`** — it installs security patches. It was one of the
processes dying, but with swap from Step 1 it can now finish its runs.

Verify what still wakes up periodically:

```bash
systemctl list-timers --all
```

Expect `apt-daily.timer`, `apt-daily-upgrade.timer` and standard systemd timers;
`fwupd-refresh.timer` should show as masked.

## Step 3 — Take a backup before touching the database

The migration in Step 4 rewrites the whole database file. Get a fresh backup first:

```bash
cd ~/exchange-rate/exchange-rate-telegram-bot
docker compose run --rm -e BACKUP_MODE=once backup
cat backup-work/last_backup.json   # expect "success": true, "phase": "done"
```

## Step 4 — Drop the unused indexes and compact the database

This is a one-time migration (new databases are created without the indexes since
this release). It roughly **halves the database file**, and with it the duration,
CPU, disk and page-cache cost of every future backup. It also activates
`auto_vacuum=FULL`, which `PRAGMA` alone silently does not do on a pre-existing
database until the next full `VACUUM`.

The bot must be stopped: the final `VACUUM` needs exclusive access (the script
checks and refuses to run otherwise). Expect a few minutes of runtime on a slow
disk and free disk space of at least the current database size (also checked).

```bash
cd ~/exchange-rate/exchange-rate-telegram-bot

# 1. Pull images containing this change, so the bot does not recreate the indexes
docker compose pull

# 2. Stop the bot
docker compose stop bot

# 3. Run the migration with the droplet's own python3 against the mounted data dir
python3 bot/scripts/drop_unused_indexes.py data/exchange_rates.db

# 4. Start the bot again
docker compose up -d bot
```

The script logs sizes before/after and the space reclaimed, and finishes with
`auto_vacuum=1`. The only index left on `exchange_rates` is the implicit UNIQUE
one that deduplication relies on.

If the repository is not checked out on the droplet, fetch just the script:

```bash
curl -fsSLO https://raw.githubusercontent.com/yurnov/exchange-rate-telegram-bot/main/bot/scripts/drop_unused_indexes.py
python3 drop_unused_indexes.py data/exchange_rates.db
```

## Step 5 — Deploy the compose changes

This release adds two lines to `docker-compose.yml`; if you maintain a locally
modified compose file on the droplet, port them over:

- `oom_score_adj: 500` on the **backup** service — if the *host* runs out of memory
  mid-backup, the kernel kills the backup (which retries next cycle) rather than
  the bot or sshd. The in-cgroup limits (`mem_limit: 320m`) are unchanged.
- `mem_limit: 192m` on the **bot** service — a leak guard, not a working-set
  budget: the bot needs well under 100 MiB, so a runaway process restarts inside
  its own cgroup instead of dragging the whole host down.

Then:

```bash
docker compose up -d
```

## Step 6 — Verify

```bash
# No new OOM kills accumulating (give it a few hours / a day)
sudo dmesg -T | grep -i 'killed process' | tail

# Memory now has headroom and swap absorbs spikes
free -h

# Database roughly halved, WAL small
ls -lh data/exchange_rates.db*

# Next scheduled backup: snapshot time and uploaded size should drop ~50%
cat backup-work/last_backup.json
```

## Rollback

Every step is reversible:

- Swap: `sudo swapoff /swapfile && sudo rm /swapfile`, remove the `/etc/fstab` line.
- Services: `sudo systemctl unmask fwupd.service fwupd-refresh.timer`,
  `sudo apt-get install appstream update-notifier-common`.
- Indexes: recreate any of them at the cost of one full table scan, e.g.
  `CREATE INDEX idx_rates_timestamp ON exchange_rates(timestamp);` — the schema
  in [DATABASE_USAGE.md](DATABASE_USAGE.md) lists the original five definitions.
- Compose: revert the two added lines.
