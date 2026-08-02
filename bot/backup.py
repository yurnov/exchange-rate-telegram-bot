#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
S3 backup module for SQLite database.

This script creates safe backups of the SQLite database and uploads them to
S3-compatible object storage. It can run in two modes:
- Scheduled mode (default): Runs continuously, creating backups at a configurable interval
- One-shot mode: Creates a single backup and exits (for cron jobs / Kubernetes Jobs)

The implementation is tuned for small hosts (512 MiB RAM, one shared vCPU) where
disk throughput is the binding constraint: the snapshot is read exactly once and
gzipped straight into the upload, it is staged on a real filesystem instead of the
container layer, the page cache is released as the data is processed so the kernel
never has to flush hundreds of megabytes of dirty pages at once, the upload uses a
single transfer thread with bounded buffers, and the process runs at a reduced CPU
and I/O priority so it yields to the bot (and to sshd) on the same box.

Usage:
    python backup.py                  # Scheduled mode (default)
    BACKUP_MODE=once python backup.py # One-shot mode

Required environment variables (if backup enabled):
    S3_BUCKET      - Target S3 bucket name
    S3_ACCESS_KEY  - S3 access key ID
    S3_SECRET_KEY  - S3 secret access key

Optional environment variables:
    BACKUP_ENABLED     - Enable backup sidecar container (default: false)
    S3_ENDPOINT_URL    - S3-compatible endpoint URL (default: None, uses AWS)
    S3_PREFIX          - Key prefix for backup files (default: backups/)
    S3_REGION          - AWS region (default: us-east-1)
    S3_STORAGE_CLASS   - Storage class for uploaded objects (default: provider default)
    BACKUP_INTERVAL    - Seconds between backups in scheduled mode (default: 86400)
    BACKUP_RETENTION   - Number of backup copies to retain, 0 disables cleanup (default: 7)
    DB_PATH            - Path to SQLite database (default: data/exchange_rates.db)
    BACKUP_MODE        - "scheduled" (default) or "once"
    LOG_LEVEL          - Logging level (default: INFO)

Resource-tuning environment variables:
    BACKUP_TMPDIR         - Directory for staging the snapshot (default: system temp)
    BACKUP_METHOD         - "auto" (default), "vacuum" or "copy"
    BACKUP_COMPRESS       - Gzip the snapshot before upload (default: true)
    BACKUP_COMPRESS_LEVEL - Gzip level 1-9, low is cheap on CPU (default: 1)
    BACKUP_NICE           - Niceness increment for this process, 0-19 (default: 10)
    BACKUP_IONICE         - Request the lowest best-effort I/O priority (default: true)
    BACKUP_DROP_CACHE     - Drop page cache for files read/written (default: true)
    BACKUP_TIMEOUT        - Abort a backup cycle after N seconds, 0 disables (default: 3600)
    BACKUP_UPLOAD_CONCURRENCY   - Concurrent multipart upload threads (default: 1)
    BACKUP_MULTIPART_THRESHOLD  - Multipart upload threshold in MiB (default: 64)
    BACKUP_MULTIPART_CHUNKSIZE  - Multipart chunk size in MiB (default: 16)
    BACKUP_STATUS_FILE    - Write a JSON status document here after every cycle
    BACKUP_LOG_FILE       - Mirror logs to this file (survives an unreachable host)
"""

import ctypes
import json
import logging
import os
import platform
import shutil
import signal
import sqlite3
import sys
import tempfile
import time
import zlib
from datetime import datetime, timezone

try:
    import boto3
    from botocore.config import Config as BotocoreConfig
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    boto3 = None

from dotenv import load_dotenv

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Copy in 4 MiB slices: large enough to keep syscall overhead irrelevant, small
# enough that the amount of dirty page cache in flight stays bounded on a 512 MiB host.
COPY_CHUNK_SIZE = 4 * 1024 * 1024

# Flush and drop the page cache after every 64 MiB written. Without this the kernel
# accumulates the whole snapshot as dirty pages and then stalls every process on the
# host (including sshd) while it writes them back.
FLUSH_INTERVAL = 64 * 1024 * 1024

MIB = 1024 * 1024

# ioprio_set(2) syscall numbers, per architecture. Used to put the backup at the
# lowest best-effort I/O priority. The idle class is deliberately not used: it only
# runs when the disk is otherwise idle, which on a busy host means never.
IOPRIO_SET_SYSCALL = {'x86_64': 251, 'aarch64': 30, 'armv7l': 314, 'i686': 289}
IOPRIO_WHO_PROCESS = 1
IOPRIO_CLASS_BEST_EFFORT = 2
IOPRIO_CLASS_SHIFT = 13
IOPRIO_LOWEST_BEST_EFFORT = 7


class BackupTimeout(Exception):
    """Raised when a backup cycle exceeds BACKUP_TIMEOUT."""


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ['true', '1', 'yes', 'on', 'enabled']


def _env_int(name: str, default: int, minimum: int = None, maximum: int = None) -> int:
    """Read an integer environment variable, falling back to the default when invalid."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == '':
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(f"Invalid value for {name}: {raw!r}, using default {default}")
        return default
    if minimum is not None and value < minimum:
        logger.warning(f"{name}={value} is below minimum {minimum}, using {minimum}")
        return minimum
    if maximum is not None and value > maximum:
        logger.warning(f"{name}={value} is above maximum {maximum}, using {maximum}")
        return maximum
    return value


def _human(size: int) -> str:
    """Format a byte count for logging."""
    value = float(size)
    for unit in ['B', 'KiB', 'MiB', 'GiB']:
        if value < 1024 or unit == 'GiB':
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def _peak_rss() -> str:
    """Return the peak resident set size of this process, if the kernel exposes it."""
    try:
        with open('/proc/self/status', 'r', encoding='utf-8') as status:
            for line in status:
                if line.startswith('VmHWM:'):
                    return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return 'unknown'


def lower_process_priority(nice_increment: int, use_ionice: bool) -> None:
    """
    Lower CPU and I/O priority of this process.

    On a single shared vCPU this is what keeps the bot responsive (and the host
    reachable over ssh) while a multi-hundred-megabyte snapshot is being copied.

    Note that both are a balance, not a maximum: niceness 19 weights the process at
    15 against 1024 for a normal-priority one, so it loses roughly 70x on a contended
    CPU and a backup that should take seconds takes minutes. The default of 10 yields
    to the bot while still making steady progress.

    Args:
        nice_increment: Niceness to add, 0-19. Higher means lower priority.
        use_ionice: Whether to request the lowest best-effort I/O priority.
    """
    if nice_increment > 0:
        try:
            logger.debug(f"Process niceness set to {os.nice(nice_increment)}")
        except OSError as e:
            logger.warning(f"Could not lower CPU priority: {str(e)}")

    if not use_ionice:
        return

    syscall_number = IOPRIO_SET_SYSCALL.get(platform.machine())
    if syscall_number is None:
        logger.debug(f"No ioprio_set syscall number known for {platform.machine()}, skipping ionice")
        return

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        priority = (IOPRIO_CLASS_BEST_EFFORT << IOPRIO_CLASS_SHIFT) | IOPRIO_LOWEST_BEST_EFFORT
        if libc.syscall(syscall_number, IOPRIO_WHO_PROCESS, 0, priority) != 0:
            logger.debug(f"ioprio_set failed with errno {ctypes.get_errno()}, keeping default I/O priority")
        else:
            logger.debug("I/O priority set to the lowest best-effort level")
    except (OSError, AttributeError) as e:
        logger.debug(f"Could not set I/O priority: {str(e)}")


def _drop_cache(fd: int, drop_cache: bool) -> None:
    """Tell the kernel the pages of this file descriptor are no longer needed."""
    if not drop_cache:
        return
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    except (AttributeError, OSError):
        pass


def _flush_and_drop(fd: int, drop_cache: bool) -> None:
    """Flush written data to disk and release its page cache."""
    try:
        os.fsync(fd)
    except OSError as e:
        logger.debug(f"fsync failed: {str(e)}")
    _drop_cache(fd, drop_cache)


def create_snapshot(db_path: str, snapshot_path: str, method: str, drop_cache: bool) -> bool:
    """
    Create a consistent snapshot of the SQLite database.

    Two strategies are available:
    - "vacuum": VACUUM INTO, which reads the database in a single read transaction
      and writes a defragmented copy. It is not restarted when the bot writes to the
      source, and the output is smaller because free pages are not copied.
    - "copy": the online backup API. Kept as a fallback for old SQLite builds. Note
      that this API restarts the copy from scratch whenever the source is modified
      mid-flight, which on a slow host can prevent it from ever finishing.

    Both handle WAL mode correctly and are safe while the bot is writing.

    Args:
        db_path: Path to the source SQLite database
        snapshot_path: Path for the snapshot file (must not exist for "vacuum")
        method: "auto", "vacuum" or "copy"
        drop_cache: Whether to release the page cache after writing

    Returns:
        True if the snapshot was created, False otherwise
    """
    if not os.path.exists(db_path):
        logger.error(f"Source database not found: {db_path}")
        return False

    # Use a longer timeout than the main bot's busy_timeout (5s) because the
    # snapshot reads the entire database and may need to wait for ongoing writes.
    source_conn = None
    try:
        source_conn = sqlite3.connect(db_path, timeout=30)

        if method in ('auto', 'vacuum'):
            try:
                source_conn.execute("VACUUM INTO ?", (snapshot_path,))
                logger.debug("Snapshot created with VACUUM INTO")
                _post_write_flush(snapshot_path, drop_cache)
                return True
            except sqlite3.Error as e:
                if method == 'vacuum':
                    logger.error(f"VACUUM INTO failed: {str(e)}")
                    return False
                logger.warning(f"VACUUM INTO unavailable ({str(e)}), falling back to the online backup API")
                # A failed VACUUM INTO may leave a partial file behind.
                if os.path.exists(snapshot_path):
                    os.unlink(snapshot_path)

        backup_conn = sqlite3.connect(snapshot_path)
        try:
            # The destination is a throwaway file that is uploaded and deleted, so
            # there is no reason to pay for journalling or per-page fsyncs on it.
            backup_conn.execute("PRAGMA journal_mode=OFF")
            backup_conn.execute("PRAGMA synchronous=OFF")
            source_conn.backup(backup_conn)
        finally:
            backup_conn.close()
        _post_write_flush(snapshot_path, drop_cache)
        return True

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error creating database snapshot: {str(e)}")
        if 'readonly' in str(e).lower():
            # Reading a WAL database needs the -shm file, which SQLite cannot create
            # on a read-only mount. It exists as long as the bot holds the database
            # open, so this normally only happens when the bot is not running.
            logger.error(
                f"The database is on a read-only mount and no shared-memory file "
                f"({os.path.basename(db_path)}-shm) is available. Start the bot container first, or mount "
                f"the data volume read-write for the backup container."
            )
        return False
    finally:
        if source_conn is not None:
            source_conn.close()
        # The source pages were read once and will not be read again; handing them
        # back keeps the bot's working set in a page cache this small.
        _drop_source_cache(db_path, drop_cache)


def _post_write_flush(path: str, drop_cache: bool) -> None:
    """Flush a file written by SQLite and drop its page cache."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        _flush_and_drop(fd, drop_cache)
    finally:
        os.close(fd)


def _drop_source_cache(db_path: str, drop_cache: bool) -> None:
    """Release the page cache held for the source database."""
    if not drop_cache:
        return
    try:
        fd = os.open(db_path, os.O_RDONLY)
    except OSError:
        return
    try:
        _drop_cache(fd, drop_cache)
    finally:
        os.close(fd)


class GzipReader:
    """
    A read-only file object that gzips another file as it is read.

    This exists so the snapshot is compressed *during* the upload rather than in a
    separate pass. Writing a compressed copy to disk and reading it back again costs
    two extra passes over the data, which on a slow disk dominates the whole backup:
    at 20 MB/s a 0.5 GB database spends minutes on I/O that buys nothing.

    Only read() is implemented, which is all boto3 needs for a non-seekable upload.
    Level 1 is deliberate: SQLite pages compress well even at the cheapest setting,
    and on a shared vCPU the CPU saved is worth more than the extra few percent of
    ratio. Compressing also shortens the upload, which is itself CPU work (TLS).
    """

    def __init__(self, source_path: str, level: int, drop_cache: bool):
        self._file = open(source_path, 'rb')  # pylint: disable=consider-using-with
        self._compressor = zlib.compressobj(level, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
        self._buffer = b''
        self._finished = False
        self._drop_cache = drop_cache
        self._read_since_drop = 0
        self.bytes_in = 0
        self.bytes_out = 0

    def read(self, size: int = -1) -> bytes:
        """Return up to `size` compressed bytes, compressing more of the source as needed."""
        while not self._finished and (size < 0 or len(self._buffer) < size):
            chunk = self._file.read(COPY_CHUNK_SIZE)
            if chunk:
                self.bytes_in += len(chunk)
                self._read_since_drop += len(chunk)
                self._buffer += self._compressor.compress(chunk)
                # Hand back the page cache for data already compressed. No fsync is
                # involved: nothing is written to disk on this path at all.
                if self._read_since_drop >= FLUSH_INTERVAL:
                    _drop_cache(self._file.fileno(), self._drop_cache)
                    self._read_since_drop = 0
            else:
                self._buffer += self._compressor.flush()
                self._finished = True

        if size < 0 or size >= len(self._buffer):
            data, self._buffer = self._buffer, b''
        else:
            data, self._buffer = self._buffer[:size], self._buffer[size:]
        self.bytes_out += len(data)
        return data

    def close(self) -> None:
        """Close the underlying file and release its page cache."""
        _drop_cache(self._file.fileno(), self._drop_cache)
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def upload_to_s3(file_path: str, bucket: str, key: str, s3_client, transfer_config, config: dict) -> int:
    """
    Upload a file to S3-compatible storage, gzipping it on the fly when enabled.

    Args:
        file_path: Local path to the file to upload
        bucket: S3 bucket name
        key: S3 object key
        s3_client: Configured boto3 S3 client
        transfer_config: boto3 TransferConfig bounding threads and buffer sizes
        config: Resolved configuration dictionary

    Returns:
        Number of bytes uploaded, or -1 on failure
    """
    try:
        if not config['compress']:
            s3_client.upload_file(file_path, bucket, key, ExtraArgs=config['extra_args'], Config=transfer_config)
            uploaded = os.path.getsize(file_path)
        else:
            with GzipReader(file_path, config['compress_level'], config['drop_cache']) as stream:
                s3_client.upload_fileobj(stream, bucket, key, ExtraArgs=config['extra_args'], Config=transfer_config)
                uploaded = stream.bytes_out
        logger.info(f"Uploaded backup to s3://{bucket}/{key}")
        return uploaded
    except ClientError as e:
        logger.error(f"S3 upload error: {str(e)}")
        return -1
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Unexpected error uploading to S3: {str(e)}")
        return -1


def cleanup_old_backups(bucket: str, prefix: str, retention: int, s3_client) -> None:
    """
    Remove old backups from S3, keeping only the most recent ones.

    Objects are deleted in batches of up to 1000 keys instead of one request per
    object. Set BACKUP_RETENTION=0 to skip this entirely and let an S3 lifecycle
    rule expire old backups server-side, which costs the host nothing at all.

    Args:
        bucket: S3 bucket name
        prefix: S3 key prefix for backups
        retention: Number of recent backups to keep
        s3_client: Configured boto3 S3 client
    """
    if retention <= 0:
        logger.info("Retention disabled (BACKUP_RETENTION=0), leaving cleanup to the bucket lifecycle policy")
        return

    try:
        objects = []
        paginator = s3_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects.extend(page.get('Contents', []))

        if len(objects) <= retention:
            logger.info(f"Backup count ({len(objects)}) within retention limit ({retention}), no cleanup needed")
            return

        # Sort by LastModified, oldest first
        objects.sort(key=lambda x: x['LastModified'])
        to_delete = [{'Key': obj['Key']} for obj in objects[: len(objects) - retention]]

        for batch_start in range(0, len(to_delete), 1000):
            batch = to_delete[batch_start : batch_start + 1000]
            response = s3_client.delete_objects(Bucket=bucket, Delete={'Objects': batch, 'Quiet': True})
            for error in response.get('Errors', []):
                logger.error(f"Failed to delete {error.get('Key')}: {error.get('Message')}")

        logger.info(f"Cleanup complete: removed {len(to_delete)} old backup(s)")

    except ClientError as e:
        logger.error(f"Error during backup cleanup: {str(e)}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Unexpected error during backup cleanup: {str(e)}")


def create_s3_client(endpoint_url: str, access_key: str, secret_key: str, region: str, max_concurrency: int):
    """
    Create a boto3 S3 client with the given configuration.

    Args:
        endpoint_url: S3-compatible endpoint URL (None for AWS)
        access_key: Access key ID
        secret_key: Secret access key
        region: AWS region
        max_concurrency: Upload concurrency, used to size the connection pool

    Returns:
        Configured boto3 S3 client
    """
    client_kwargs = {
        'aws_access_key_id': access_key,
        'aws_secret_access_key': secret_key,
        'region_name': region,
        # Explicit timeouts turn a silently stalled upload into a retried (and
        # eventually logged) failure instead of a container that hangs forever.
        'config': BotocoreConfig(
            connect_timeout=15,
            read_timeout=120,
            retries={'mode': 'adaptive', 'max_attempts': 5},
            max_pool_connections=max(max_concurrency, 2),
            tcp_keepalive=True,
        ),
    }
    if endpoint_url:
        client_kwargs['endpoint_url'] = endpoint_url

    return boto3.client('s3', **client_kwargs)


def create_transfer_config(max_concurrency: int, threshold_mib: int, chunksize_mib: int):
    """
    Build a TransferConfig that bounds upload memory and CPU.

    boto3 defaults to 10 concurrent 8 MiB parts, so an upload can hold ~80 MiB of
    buffers and run TLS encryption on ten threads at once. On a 512 MiB host with one
    shared vCPU that is enough to trigger the OOM killer, which kills the process
    before it can log anything.

    Args:
        max_concurrency: Number of concurrent part uploads
        threshold_mib: Size above which multipart upload kicks in
        chunksize_mib: Size of each multipart chunk

    Returns:
        Configured boto3 TransferConfig
    """
    # Imported lazily so the module can still be imported without boto3 installed.
    from boto3.s3.transfer import TransferConfig  # pylint: disable=import-outside-toplevel

    return TransferConfig(
        multipart_threshold=threshold_mib * MIB,
        multipart_chunksize=chunksize_mib * MIB,
        max_concurrency=max_concurrency,
        use_threads=max_concurrency > 1,
        max_io_queue=max(max_concurrency * 2, 2),
    )


def write_status(status_file: str, payload: dict) -> None:
    """
    Write a JSON status document describing the last backup cycle.

    Placed on a mounted volume this is the only artefact that survives an OOM kill,
    so it is often the only way to find out what happened on a host that was too
    loaded to accept an ssh connection.

    Args:
        status_file: Destination path (no-op when empty)
        payload: Status fields to serialise
    """
    if not status_file:
        return
    try:
        os.makedirs(os.path.dirname(status_file) or '.', exist_ok=True)
        tmp_path = f"{status_file}.tmp"
        with open(tmp_path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        os.replace(tmp_path, status_file)
    except OSError as e:
        logger.warning(f"Could not write status file {status_file}: {str(e)}")


def _has_room_to_stage(db_path: str, work_dir: str, status: dict) -> bool:
    """
    Check that the staging directory can hold a snapshot of the database.

    The snapshot is never larger than the source, so the source size plus a small
    margin for the compressed copy is a safe estimate.

    Args:
        db_path: Path to the source SQLite database
        work_dir: Directory the snapshot will be staged in
        status: Status dictionary to annotate on failure

    Returns:
        True if there is enough free space, False otherwise
    """
    try:
        needed = int(os.path.getsize(db_path) * 1.2)
        free = shutil.disk_usage(work_dir).free
    except OSError as e:
        logger.debug(f"Could not check free space in {work_dir}: {str(e)}")
        return True

    if free < needed:
        message = f"Not enough space in {work_dir}: {_human(free)} free, {_human(needed)} needed"
        logger.error(message)
        status['error'] = message
        return False
    return True


def run_backup(config: dict, s3_client, transfer_config) -> bool:
    """
    Execute a single backup cycle: snapshot, optional compression, upload, cleanup.

    Each phase is timed and logged separately so a run that dies part-way through
    can be attributed to a specific phase after the fact.

    Args:
        config: Resolved configuration dictionary
        s3_client: Configured boto3 S3 client
        transfer_config: boto3 TransferConfig for the upload

    Returns:
        True if backup was successful, False otherwise
    """
    started_at = datetime.now(timezone.utc)
    timestamp = started_at.strftime('%Y%m%d_%H%M%S')
    suffix = '.db.gz' if config['compress'] else '.db'
    backup_key = f"{config['s3_prefix']}exchange_rates_{timestamp}{suffix}"

    status = {
        'started_at': started_at.isoformat(),
        'key': backup_key,
        'success': False,
        'phase': 'starting',
    }

    # VACUUM INTO refuses to write to an existing file, so stage inside a private
    # directory rather than using a pre-created NamedTemporaryFile.
    work_dir = tempfile.mkdtemp(prefix='xratebot-backup-', dir=config['tmpdir'] or None)
    snapshot_path = os.path.join(work_dir, 'snapshot.db')

    if config['timeout'] > 0:
        signal.alarm(config['timeout'])

    try:
        # Refuse to start rather than fill the disk the bot's own database lives on.
        if not _has_room_to_stage(config['db_path'], work_dir, status):
            return False

        phase_start = time.monotonic()
        status['phase'] = 'snapshot'
        if not create_snapshot(config['db_path'], snapshot_path, config['method'], config['drop_cache']):
            return False
        snapshot_size = os.path.getsize(snapshot_path)
        logger.info(
            f"Snapshot created: {_human(snapshot_size)} in {time.monotonic() - phase_start:.1f}s "
            f"({config['method']} method)"
        )
        status['snapshot_bytes'] = snapshot_size
        status['snapshot_seconds'] = round(time.monotonic() - phase_start, 1)

        # Compression happens inside the upload, so the snapshot is read exactly once
        # and no compressed copy is ever written to disk.
        phase_start = time.monotonic()
        status['phase'] = 'upload'
        upload_size = upload_to_s3(snapshot_path, config['s3_bucket'], backup_key, s3_client, transfer_config, config)
        if upload_size < 0:
            return False
        elapsed = max(time.monotonic() - phase_start, 0.001)
        ratio = f", {snapshot_size / upload_size:.1f}x smaller" if config['compress'] and upload_size else ""
        logger.info(
            f"Upload finished: {_human(upload_size)} in {elapsed:.1f}s "
            f"({_human(int(upload_size / elapsed))}/s{ratio})"
        )
        status['uploaded_bytes'] = upload_size
        status['upload_seconds'] = round(elapsed, 1)

        status['phase'] = 'cleanup'
        cleanup_old_backups(config['s3_bucket'], config['s3_prefix'], config['retention'], s3_client)

        status['phase'] = 'done'
        status['success'] = True
        logger.info(f"Backup cycle completed successfully: {backup_key} (peak RSS {_peak_rss()})")
        return True

    except BackupTimeout:
        logger.error(f"Backup timed out after {config['timeout']}s during phase '{status['phase']}'")
        status['error'] = f"timeout after {config['timeout']}s"
        return False
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Backup cycle failed during phase '{status['phase']}': {str(e)}")
        status['error'] = str(e)
        return False
    finally:
        if config['timeout'] > 0:
            signal.alarm(0)
        shutil.rmtree(work_dir, ignore_errors=True)
        status['finished_at'] = datetime.now(timezone.utc).isoformat()
        status['peak_rss'] = _peak_rss()
        write_status(config['status_file'], status)


def _handle_timeout(signum, frame):  # pylint: disable=unused-argument
    """Convert SIGALRM into an exception so the cycle can clean up after itself."""
    raise BackupTimeout()


def _handle_termination(signum, frame):  # pylint: disable=unused-argument
    """Exit cleanly on SIGTERM/SIGINT so `docker stop` does not look like a crash."""
    logger.info(f"Received signal {signum}, shutting down")
    sys.exit(0)


def load_config() -> dict:
    """
    Resolve configuration from the environment.

    Returns:
        Dictionary with all resolved settings
    """
    s3_prefix = os.getenv('S3_PREFIX', 'backups/')
    if s3_prefix and not s3_prefix.endswith('/'):
        s3_prefix += '/'

    config = {
        'db_path': os.getenv('DB_PATH', 'data/exchange_rates.db'),
        's3_endpoint_url': os.getenv('S3_ENDPOINT_URL'),
        's3_bucket': os.getenv('S3_BUCKET'),
        's3_prefix': s3_prefix,
        's3_access_key': os.getenv('S3_ACCESS_KEY'),
        's3_secret_key': os.getenv('S3_SECRET_KEY'),
        's3_region': os.getenv('S3_REGION', 'us-east-1'),
        's3_storage_class': os.getenv('S3_STORAGE_CLASS'),
        'interval': _env_int('BACKUP_INTERVAL', 86400, minimum=60),
        'retention': _env_int('BACKUP_RETENTION', 7, minimum=0),
        'mode': os.getenv('BACKUP_MODE', 'scheduled'),
        'tmpdir': os.getenv('BACKUP_TMPDIR', ''),
        'method': os.getenv('BACKUP_METHOD', 'auto').strip().lower(),
        'compress': _env_bool('BACKUP_COMPRESS', True),
        'compress_level': _env_int('BACKUP_COMPRESS_LEVEL', 1, minimum=1, maximum=9),
        'nice': _env_int('BACKUP_NICE', 10, minimum=0, maximum=19),
        'ionice': _env_bool('BACKUP_IONICE', True),
        'drop_cache': _env_bool('BACKUP_DROP_CACHE', True),
        'timeout': _env_int('BACKUP_TIMEOUT', 3600, minimum=0),
        'upload_concurrency': _env_int('BACKUP_UPLOAD_CONCURRENCY', 1, minimum=1, maximum=10),
        'multipart_threshold': _env_int('BACKUP_MULTIPART_THRESHOLD', 64, minimum=5),
        'multipart_chunksize': _env_int('BACKUP_MULTIPART_CHUNKSIZE', 16, minimum=5),
        'status_file': os.getenv('BACKUP_STATUS_FILE', ''),
        'log_file': os.getenv('BACKUP_LOG_FILE', ''),
    }

    if config['method'] not in ('auto', 'vacuum', 'copy'):
        logger.warning(f"Unknown BACKUP_METHOD={config['method']!r}, falling back to 'auto'")
        config['method'] = 'auto'

    extra_args = {}
    if config['s3_storage_class']:
        extra_args['StorageClass'] = config['s3_storage_class']
    if config['compress']:
        extra_args['ContentType'] = 'application/gzip'
    config['extra_args'] = extra_args or None

    return config


def main():
    """Main entry point for the backup script."""
    load_dotenv()

    # Validate boto3 is available
    if boto3 is None:
        logger.error("boto3 is not installed. Install it with: pip install boto3")
        sys.exit(1)

    config = load_config()

    # Set logging level
    logger.setLevel(os.getenv('LOG_LEVEL', 'INFO').upper())

    # Mirror logs to a file on a mounted volume: when the host is loaded enough that
    # ssh will not connect, this file is what explains the failure afterwards.
    if config['log_file']:
        try:
            os.makedirs(os.path.dirname(config['log_file']) or '.', exist_ok=True)
            file_handler = logging.FileHandler(config['log_file'])
            file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            logger.addHandler(file_handler)
        except OSError as e:
            logger.warning(f"Could not open log file {config['log_file']}: {str(e)}")

    # Check if backup is enabled
    if not _env_bool('BACKUP_ENABLED', False):
        logger.info("Backup is disabled. Set BACKUP_ENABLED=true to enable.")
        sys.exit(0)

    # Validate required configuration
    if not config['s3_bucket']:
        logger.error("S3_BUCKET is required")
        sys.exit(1)
    if not config['s3_access_key']:
        logger.error("S3_ACCESS_KEY is required")
        sys.exit(1)
    if not config['s3_secret_key']:
        logger.error("S3_SECRET_KEY is required")
        sys.exit(1)
    if config['tmpdir']:
        try:
            os.makedirs(config['tmpdir'], exist_ok=True)
        except OSError as e:
            logger.error(f"BACKUP_TMPDIR {config['tmpdir']} is not usable: {str(e)}")
            sys.exit(1)

    signal.signal(signal.SIGTERM, _handle_termination)
    signal.signal(signal.SIGINT, _handle_termination)
    if config['timeout'] > 0:
        signal.signal(signal.SIGALRM, _handle_timeout)

    logger.info(
        f"Backup configuration: db_path={config['db_path']}, bucket={config['s3_bucket']}, prefix={config['s3_prefix']}"
    )
    logger.info(f"Mode: {config['mode']}, interval: {config['interval']}s, retention: {config['retention']}")
    logger.info(
        f"Resources: staging={config['tmpdir'] or tempfile.gettempdir()}, method={config['method']}, "
        f"compress={config['compress']}/level {config['compress_level']}, "
        f"upload threads={config['upload_concurrency']}, chunk={config['multipart_chunksize']} MiB, "
        f"nice={config['nice']}, ionice={config['ionice']}, timeout={config['timeout']}s"
    )

    try:
        s3_client = create_s3_client(
            config['s3_endpoint_url'],
            config['s3_access_key'],
            config['s3_secret_key'],
            config['s3_region'],
            config['upload_concurrency'],
        )
        transfer_config = create_transfer_config(
            config['upload_concurrency'],
            config['multipart_threshold'],
            config['multipart_chunksize'],
        )
    except NoCredentialsError:
        logger.error("Invalid S3 credentials")
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error creating S3 client: {str(e)}")
        sys.exit(1)

    # Lower priority only once startup is done. Building the S3 client parses several
    # megabytes of bundled JSON models: a fixed ~1s of CPU that has no bearing on host
    # load, but which takes minutes if it runs at the lowest priority on a busy vCPU.
    lower_process_priority(config['nice'], config['ionice'])

    if config['mode'] == 'once':
        # One-shot mode: run single backup and exit
        logger.info("Starting one-shot backup")
        success = run_backup(config, s3_client, transfer_config)
        sys.exit(0 if success else 1)
    else:
        # Scheduled mode: run continuously
        logger.info(f"Starting scheduled backup every {config['interval']} seconds")
        while True:
            cycle_start = time.monotonic()
            success = run_backup(config, s3_client, transfer_config)
            # Subtract the time the cycle took so the schedule does not drift by the
            # duration of every backup.
            sleep_for = max(config['interval'] - (time.monotonic() - cycle_start), 60)
            if not success:
                logger.error(f"Backup failed. Retrying in {sleep_for:.0f} seconds...")
            else:
                logger.info(f"Backup completed, next backup in {sleep_for:.0f} seconds")
            time.sleep(sleep_for)


if __name__ == "__main__":
    main()
