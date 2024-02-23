FROM python:3.12-slim

LABEL org.opencontainers.image.authors="Yuriy Novostavskiy" \
      org.opencontainers.image.source="https://github.com/yurnov/exchange-rate-telegram-bot.git" \
      org.opencontainers.image.license="MIT" \
      org.opencontainers.image.description="A simple chart image builder for exchange-rate-telegram-bot"

RUN python -m pip install matplotlib~=3.8.3

WORKDIR /image

COPY image/* ./

ENTRYPOINT [ "python", "chart.py" ]