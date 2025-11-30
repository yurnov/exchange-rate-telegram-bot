FROM python:3.14-slim

LABEL org.opencontainers.image.authors="Yuriy Novostavskiy" \
      org.opencontainers.image.source="https://github.com/yurnov/exchange-rate-telegram-bot.git" \
      org.opencontainers.image.license="MIT" \
      org.opencontainers.image.description="A simple bot that sends the current exchange rate of the USD, EUR, and PLN to UAH from Monobank to a Telegram chat"

RUN --mount=type=bind,source=./requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /bot

COPY bot/* ./

ENTRYPOINT [ "python", "main.py" ]
