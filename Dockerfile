FROM python:3.14-slim

# OCI Image Format Specification labels
# https://github.com/opencontainers/image-spec/blob/main/annotations.md
LABEL org.opencontainers.image.title="Exchange Rate Telegram Bot" \
      org.opencontainers.image.description="A simple bot that sends the current exchange rate of the USD, EUR, and PLN to UAH from Monobank to a Telegram chat" \
      org.opencontainers.image.authors="Yuriy Novostavskiy" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.url="https://github.com/yurnov/exchange-rate-telegram-bot" \
      org.opencontainers.image.source="https://github.com/yurnov/exchange-rate-telegram-bot.git" \
      org.opencontainers.image.documentation="https://github.com/yurnov/exchange-rate-telegram-bot#readme" \
      org.opencontainers.image.version="${VERSION:-latest}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${GIT_COMMIT}"

RUN --mount=type=bind,source=./requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /bot

COPY bot/* ./

ENTRYPOINT [ "python", "main.py" ]
