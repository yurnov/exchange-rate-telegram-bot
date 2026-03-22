#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
S3 backup module for SQLite database.

This script creates safe backups of the SQLite database using the online backup API
and uploads them to S3-compatible object storage. It can run in two modes:
- Scheduled mode (default): Runs continuously, creating backups at a configurable interval
- One-shot mode: Creates a single backup and exits (for cron jobs / Kubernetes Jobs)

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
    BACKUP_INTERVAL    - Seconds between backups in scheduled mode (default: 86400)
    BACKUP_RETENTION   - Number of backup copies to retain (default: 7)
    DB_PATH            - Path to SQLite database (default: data/exchange_rates.db)
    BACKUP_MODE        - "scheduled" (default) or "once"
    LOG_LEVEL          - Logging level (default: INFO)
"""

import logging
import os
import sqlite3
import sys
import time
import tempfile
from datetime import datetime, timezone

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    boto3 = None

from dotenv import load_dotenv

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


def create_backup(db_path: str, backup_path: str) -> bool:
    """
    Create a safe SQLite backup using the online backup API.

    This handles WAL mode correctly and produces a consistent backup file
    even while the database is being written to by another process.

    Args:
        db_path: Path to the source SQLite database
        backup_path: Path for the backup file

    Returns:
        True if backup was successful, False otherwise
    """
    if not os.path.exists(db_path):
        logger.error(f"Source database not found: {db_path}")
        return False

    try:
        # Use longer timeout than the main bot's busy_timeout (5s) because
        # backup reads the entire database and may need to wait for ongoing writes
        source_conn = sqlite3.connect(db_path, timeout=30)
        backup_conn = sqlite3.connect(backup_path)
        source_conn.backup(backup_conn)
        backup_conn.close()
        source_conn.close()
        logger.info(f"Database backup created: {backup_path}")
        return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error creating database backup: {str(e)}")
        return False


def upload_to_s3(file_path: str, bucket: str, key: str, s3_client) -> bool:
    """
    Upload a file to S3-compatible storage.

    Args:
        file_path: Local path to the file to upload
        bucket: S3 bucket name
        key: S3 object key
        s3_client: Configured boto3 S3 client

    Returns:
        True if upload was successful, False otherwise
    """
    try:
        s3_client.upload_file(file_path, bucket, key)
        logger.info(f"Uploaded backup to s3://{bucket}/{key}")
        return True
    except ClientError as e:
        logger.error(f"S3 upload error: {str(e)}")
        return False
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Unexpected error uploading to S3: {str(e)}")
        return False


def cleanup_old_backups(bucket: str, prefix: str, retention: int, s3_client) -> None:
    """
    Remove old backups from S3, keeping only the most recent ones.

    Args:
        bucket: S3 bucket name
        prefix: S3 key prefix for backups
        retention: Number of recent backups to keep
        s3_client: Configured boto3 S3 client
    """
    try:
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        objects = response.get('Contents', [])

        if len(objects) <= retention:
            logger.info(f"Backup count ({len(objects)}) within retention limit ({retention}), no cleanup needed")
            return

        # Sort by LastModified, oldest first
        objects.sort(key=lambda x: x['LastModified'])
        to_delete = objects[: len(objects) - retention]

        for obj in to_delete:
            s3_client.delete_object(Bucket=bucket, Key=obj['Key'])
            logger.info(f"Deleted old backup: s3://{bucket}/{obj['Key']}")

        logger.info(f"Cleanup complete: removed {len(to_delete)} old backup(s)")

    except ClientError as e:
        logger.error(f"Error during backup cleanup: {str(e)}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Unexpected error during backup cleanup: {str(e)}")


def create_s3_client(endpoint_url: str, access_key: str, secret_key: str, region: str):
    """
    Create a boto3 S3 client with the given configuration.

    Args:
        endpoint_url: S3-compatible endpoint URL (None for AWS)
        access_key: Access key ID
        secret_key: Secret access key
        region: AWS region

    Returns:
        Configured boto3 S3 client
    """
    client_kwargs = {
        'aws_access_key_id': access_key,
        'aws_secret_access_key': secret_key,
        'region_name': region,
    }
    if endpoint_url:
        client_kwargs['endpoint_url'] = endpoint_url

    return boto3.client('s3', **client_kwargs)


def run_backup(db_path: str, s3_client, bucket: str, prefix: str, retention: int) -> bool:
    """
    Execute a single backup cycle: create backup, upload to S3, cleanup old backups.

    Args:
        db_path: Path to the SQLite database
        s3_client: Configured boto3 S3 client
        bucket: S3 bucket name
        prefix: S3 key prefix
        retention: Number of backups to retain

    Returns:
        True if backup was successful, False otherwise
    """
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    backup_key = f"{prefix}exchange_rates_{timestamp}.db"

    # Create backup in a temporary file
    with tempfile.NamedTemporaryFile(suffix='.db', delete=True) as tmp_file:
        backup_path = tmp_file.name

        # Create safe backup using SQLite's online backup API
        if not create_backup(db_path, backup_path):
            return False

        # Upload to S3
        if not upload_to_s3(backup_path, bucket, backup_key, s3_client):
            return False

    # Cleanup old backups
    cleanup_old_backups(bucket, prefix, retention, s3_client)

    logger.info(f"Backup cycle completed successfully: {backup_key}")
    return True


def main():
    """Main entry point for the backup script."""
    load_dotenv()

    # Validate boto3 is available
    if boto3 is None:
        logger.error("boto3 is not installed. Install it with: pip install boto3")
        sys.exit(1)

    # Load configuration from environment
    db_path = os.getenv('DB_PATH', 'data/exchange_rates.db')
    s3_endpoint_url = os.getenv('S3_ENDPOINT_URL')
    s3_bucket = os.getenv('S3_BUCKET')
    s3_prefix = os.getenv('S3_PREFIX', 'backups/')
    s3_access_key = os.getenv('S3_ACCESS_KEY')
    s3_secret_key = os.getenv('S3_SECRET_KEY')
    s3_region = os.getenv('S3_REGION', 'us-east-1')
    backup_interval = int(os.getenv('BACKUP_INTERVAL', '86400'))
    backup_retention = int(os.getenv('BACKUP_RETENTION', '7'))
    backup_mode = os.getenv('BACKUP_MODE', 'scheduled')
    log_level = os.getenv('LOG_LEVEL', 'INFO')

    # Set logging level
    logger.setLevel(log_level.upper())

    # Check if backup is enabled
    if not os.getenv('BACKUP_ENABLED', 'false').lower() in ['true', '1', 'yes', 'on', 'enabled']:
        logger.info("Backup is disabled. Set BACKUP_ENABLED=true to enable.")
        sys.exit(0)

    # Ensure S3 prefix ends with /
    if s3_prefix and not s3_prefix.endswith('/'):
        s3_prefix += '/'

    # Validate required configuration
    if not s3_bucket:
        logger.error("S3_BUCKET is required")
        sys.exit(1)
    if not s3_access_key:
        logger.error("S3_ACCESS_KEY is required")
        sys.exit(1)
    if not s3_secret_key:
        logger.error("S3_SECRET_KEY is required")
        sys.exit(1)

    logger.info(f"Backup configuration: db_path={db_path}, bucket={s3_bucket}, prefix={s3_prefix}")
    logger.info(f"Mode: {backup_mode}, interval: {backup_interval}s, retention: {backup_retention}")

    try:
        s3_client = create_s3_client(s3_endpoint_url, s3_access_key, s3_secret_key, s3_region)
    except NoCredentialsError:
        logger.error("Invalid S3 credentials")
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error creating S3 client: {str(e)}")
        sys.exit(1)

    if backup_mode == 'once':
        # One-shot mode: run single backup and exit
        logger.info("Starting one-shot backup")
        success = run_backup(db_path, s3_client, s3_bucket, s3_prefix, backup_retention)
        sys.exit(0 if success else 1)
    else:
        # Scheduled mode: run continuously
        logger.info(f"Starting scheduled backup every {backup_interval} seconds")
        while True:
            success = run_backup(db_path, s3_client, s3_bucket, s3_prefix, backup_retention)
            if not success:
                logger.error("Backup failed. Retrying in %d seconds...", backup_interval)
            else:
                logger.info(f"Backup compleated, next backup in {backup_interval} seconds")
            time.sleep(backup_interval)


if __name__ == "__main__":
    main()
