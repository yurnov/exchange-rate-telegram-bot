#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
One-shot migration: drop the unused exchange_rates indexes and compact the database.

The exchange_rates table is write-only in production (the bot answers users from the
live API and the chart builder reads the CSV), yet five secondary indexes were being
maintained on it. Measured with dbstat, they held roughly two thirds of the file:
every insert updated seven B-trees to serve queries that never ran, and every backup
snapshotted and uploaded hundreds of megabytes of index pages.

This script:
1. Drops the five unused indexes (the UNIQUE constraint's implicit index, which
   INSERT OR IGNORE deduplication relies on, is untouched).
2. Runs VACUUM to rewrite the file without the freed pages. This is also what makes
   the PRAGMA auto_vacuum=FULL setting take effect: on a database created before
   that pragma was introduced it is a silent no-op until the next full VACUUM.
3. Truncates the WAL so the shrunken state is in the main file.

Stop the bot before running: VACUUM takes an exclusive lock and would stall or fail
concurrent inserts. Expect the runtime of a full read+write of the database file
(minutes on a small droplet). Free disk space of at least the current database size
is required, which is checked before anything is dropped.

Usage:
    python drop_unused_indexes.py [path/to/exchange_rates.db]

The script is intentionally standalone (standard library only), so it can run on the
droplet's system python3 against the bind-mounted ./data directory, without starting
any container.
"""

import ctypes
import logging
import os
import platform
import shutil
import sqlite3
import sys
import time

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "data/exchange_rates.db"

UNUSED_INDEXES = [
    "idx_rates_timestamp",
    "idx_rates_api_timestamp",
    "idx_rates_currency_pair",
    "idx_rates_source",
    "idx_rates_currency_a",
]

# ioprio_set(2) syscall numbers, as in bot/backup.py. The script is standalone so it
# can run on the host's python3, hence the small duplication instead of an import.
IOPRIO_SET_SYSCALL = {'x86_64': 251, 'aarch64': 30, 'armv7l': 314, 'i686': 289}
IOPRIO_WHO_PROCESS = 1
IOPRIO_CLASS_BEST_EFFORT = 2
IOPRIO_CLASS_SHIFT = 13
IOPRIO_LOWEST_BEST_EFFORT = 7


def lower_process_priority():
    """Run at reduced CPU and I/O priority so the host stays responsive."""
    try:
        os.nice(10)
    except OSError as e:
        logger.warning(f"Could not lower CPU priority: {str(e)}")

    syscall_number = IOPRIO_SET_SYSCALL.get(platform.machine())
    if syscall_number is None:
        return
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        priority = (IOPRIO_CLASS_BEST_EFFORT << IOPRIO_CLASS_SHIFT) | IOPRIO_LOWEST_BEST_EFFORT
        libc.syscall(syscall_number, IOPRIO_WHO_PROCESS, 0, priority)
    except (OSError, AttributeError):
        pass


def file_size(path: str) -> int:
    """Return the size of a file, or 0 if it does not exist."""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def human(size: int) -> str:
    """Format a byte count for logging."""
    value = float(size)
    for unit in ['B', 'KiB', 'MiB', 'GiB']:
        if value < 1024 or unit == 'GiB':
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def main() -> int:
    """Drop unused indexes, VACUUM, and report the space reclaimed."""
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    if not os.path.exists(db_path):
        logger.error(f"Database not found: {db_path}")
        return 1

    before_db = file_size(db_path)
    before_wal = file_size(f"{db_path}-wal")

    # VACUUM rewrites the database into a temporary copy in the same directory, so
    # it needs free space for a second (smaller) database plus some journal margin.
    free = shutil.disk_usage(os.path.dirname(os.path.abspath(db_path))).free
    if free < before_db:
        logger.error(f"Not enough free disk space for VACUUM: {human(free)} free, {human(before_db)} needed")
        return 1

    lower_process_priority()

    logger.info(f"Database: {db_path} ({human(before_db)} + {human(before_wal)} WAL)")

    conn = sqlite3.connect(db_path, timeout=30)
    try:
        # Refuse to run while the bot holds the database, instead of stalling its
        # inserts for the whole VACUUM.
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")

        existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        for index in UNUSED_INDEXES:
            if index in existing:
                started = time.monotonic()
                conn.execute(f"DROP INDEX {index}")
                logger.info(f"Dropped {index} in {time.monotonic() - started:.1f}s")
            else:
                logger.info(f"Index {index} not present, skipping")
        conn.commit()

        # A no-op on databases already in FULL mode; on older files it is recorded
        # here and materialised by the VACUUM below.
        conn.execute("PRAGMA auto_vacuum=FULL")

        logger.info("Running VACUUM (full rewrite of the database, this is the slow part)...")
        started = time.monotonic()
        conn.execute("VACUUM")
        logger.info(f"VACUUM finished in {time.monotonic() - started:.1f}s")

        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        auto_vacuum = conn.execute("PRAGMA auto_vacuum").fetchone()[0]
        remaining = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")]
    except sqlite3.OperationalError as e:
        logger.error(f"Migration failed: {str(e)} (is the bot still running?)")
        return 1
    finally:
        conn.close()

    after_db = file_size(db_path)
    after_wal = file_size(f"{db_path}-wal")
    logger.info(f"Size before: {human(before_db)} (+{human(before_wal)} WAL)")
    logger.info(f"Size after:  {human(after_db)} (+{human(after_wal)} WAL)")
    logger.info(f"Reclaimed:   {human(max(before_db + before_wal - after_db - after_wal, 0))}")
    logger.info(f"auto_vacuum={auto_vacuum} (1 means FULL is now active), remaining indexes: {remaining}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
