FROM python:3.14-slim

ARG BUILD_DATE
ARG GIT_COMMIT
ARG VERSION

# OCI Image Format Specification labels
LABEL org.opencontainers.image.title="Exchange Rate Bot - Database Backup" \
      org.opencontainers.image.description="Sidecar container for backing up SQLite database to S3-compatible storage" \
      org.opencontainers.image.authors="Yuriy Novostavskiy" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.url="https://github.com/yurnov/exchange-rate-telegram-bot" \
      org.opencontainers.image.source="https://github.com/yurnov/exchange-rate-telegram-bot.git" \
      org.opencontainers.image.version="${VERSION:-latest}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${GIT_COMMIT}"

RUN --mount=type=bind,source=./backup/requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /bot

COPY bot/backup.py ./

ENTRYPOINT [ "python", "backup.py" ]
