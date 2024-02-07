#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import requests
import os
from dotenv import load_dotenv

from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

MONOBANK_API_URL = "https://api.monobank.ua/bank/currency"

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# pylint: disable=unused-argument
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}, I'm a exchange rate bot, use /rate to gat a rate!",
        reply_markup=ForceReply(selective=True),
    )

# pylint: disable=unused-argument
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("use /rate to get a rate! Data is fetched from Monobank API and upadted once per 5 minutes.")

# pylint: disable=unused-argument
async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    logger.info(f'User {update.effective_user.id} requested exchange rates.')
    logger.info("Fetching exchange rates from Monobank API")
    
    # pylint: disable=broad-except
    try:
        # Fetching exchange rates from Monobank API
        response = requests.get(MONOBANK_API_URL, timeout=10)
        data = response.json()

    except Exception as e:
        await update.message.reply_text(f'Error fetching exchange rates: {str(e)}')
        logger.error(f'Error fetching exchange rates: {str(e)}')

    usd_rate = 0
    usd_rate_sell = 0
    eur_rate = 0
    eur_rate_sell = 0
    pln_rate = 0
    
    # pylint: disable=broad-except
    try:
        # Extracting exchange rates from the JSON response
        usd_rate = next(item for item in data if item['currencyCodeA'] == 840 and item['currencyCodeB'] == 980)['rateBuy']
        usd_rate_sell = next(item for item in data if item['currencyCodeA'] == 840 and item['currencyCodeB'] == 980)['rateSell']
        eur_rate = next(item for item in data if item['currencyCodeA'] == 978 and item['currencyCodeB'] == 980)['rateBuy']
        eur_rate_sell = next(item for item in data if item['currencyCodeA'] == 978 and item['currencyCodeB'] == 980)['rateSell']
        pln_rate = next(item for item in data if item['currencyCodeA'] == 985 and item['currencyCodeB'] == 980)['rateCross']

        # Sending the exchange rates to the user
        await update.message.reply_text(f'Buy rates:\nUSD Exchange Rate: {usd_rate}\nEUR Exchange Rate: {eur_rate}\n\nSell rates:\nUSD Exchange Rate: {usd_rate_sell}\nEUR Exchange Rate: {eur_rate_sell}\n\nPLN Exchange Rate: {pln_rate}')    

    except Exception:
        await update.message.reply_text('Error parsing exchange rates from Monobank API response')
        logger.error('Error parsing exchange rates from Monobank API response')

def main() -> None:
    # Load environment variables
    load_dotenv()
    TOKEN = os.getenv("BOT_TOKEN")

    # Ensure the token is set
    if TOKEN is None:
        logger.error("BOT_TOKEN is required")
        return
    
    logger.info("BOT_TOKEN is provided. Starting bot...")
    
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rate", rate))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, help_command))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()