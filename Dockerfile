FROM python:3.12-slim

LABEL org.opencontainers.image.authors="Yuriy Novostavskiy" \
      org.opencontainers.image.source="https://github.com/yurnov/exchange-rate-telegram-bot.git" \
      org.opencontainers.image.license="MIT" \
      org.opencontainers.image.description="A simple bot that sends the current exchange rate of the USD, EUR, and PLN to UAH from Monobank to a Telegram chat"

RUN python -m pip install requests~=2.31.0 python-telegram-bot~=20.7 python-dotenv~=1.0.1 schedule~=1.2.1

WORKDIR /bot

COPY bot/* ./

ENTRYPOINT [ "python", "main.py" ]
