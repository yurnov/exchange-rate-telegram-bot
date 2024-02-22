#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import requests
import os
import schedule
import time
import threading
from dotenv import load_dotenv

from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

MONOBANK_API_URL = "https://api.monobank.ua/bank/currency"

# Initialize exchange rates
usd_rate = 0
usd_rate_sell = 0
eur_rate = 0
eur_rate_sell = 0
pln_rate = 0
LOG_RATE = False

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def get_exchange_rates():
    logger.info("Fetching exchange rates from Monobank API")
    
    # pylint: disable=global-statement
    global usd_rate, usd_rate_sell, eur_rate, eur_rate_sell, pln_rate
    # pylint: disable=broad-except
    try:
        # Fetching exchange rates from Monobank API
        response = requests.get(MONOBANK_API_URL, timeout=10)
        data = response.json()
        usd_rate = next(item for item in data if item['currencyCodeA'] == 840 and item['currencyCodeB'] == 980)['rateBuy']
        usd_rate_sell = next(item for item in data if item['currencyCodeA'] == 840 and item['currencyCodeB'] == 980)['rateSell']
        eur_rate = next(item for item in data if item['currencyCodeA'] == 978 and item['currencyCodeB'] == 980)['rateBuy']
        eur_rate_sell = next(item for item in data if item['currencyCodeA'] == 978 and item['currencyCodeB'] == 980)['rateSell']
        pln_rate = next(item for item in data if item['currencyCodeA'] == 985 and item['currencyCodeB'] == 980)['rateCross']

        logger.info(f'USD Buy Rate: {usd_rate}. Sell Rate: {usd_rate_sell}. EUR Buy Rate: {eur_rate}. Sell Rate: {eur_rate_sell}. PLN Exchange Rate: {pln_rate}')
        
    except Exception as e:
        logger.error(f'Error fetching exchange rates: {str(e)}')
    
    # Log exchange rates to CSV file
    # format of CSV file: Date, Time, USD Buy Rate, USD Sell Rate, EUR Buy Rate, EUR Sell Rate, PLN Exchange Rate
    if LOG_RATE:
        try: 
            with open('exchange_rates.csv', 'a') as file:
                file.write(f'{time.strftime("%Y-%m-%d")},{time.strftime("%H:%M:%S")},{usd_rate},{usd_rate_sell},{eur_rate},{eur_rate_sell},{pln_rate}\n')
            logger.info('Exchange rates written to exchange_rates.csv')
        except Exception as e:
            logger.error(f'Error writing to exchange_rates.csv: {str(e)}')

# pylint: disable=unused-argument
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}, "
        "I'm a exchange rate bot, I will help to to know actual exchange rate of USD, EUR and PLN in UAH. "
        "Please use /rate to get information!",
        reply_markup=ForceReply(selective=True),
    )

# pylint: disable=unused-argument
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Use /rate to get a rate!\n Base currency is 🇺🇦 Ukrainian Hryvnia (UAH ₴)\n\nPowered by Monobank API.")

# pylint: disable=unused-argument
async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    logger.info(f'User {update.effective_user.id} requested exchange rates.')
    
    try:
        await update.message.reply_text(f'🇺🇸$ USD Buy Rate: {usd_rate}. Sell Rate: {usd_rate_sell}\n🇪🇺€ EUR Buy Rate: {eur_rate}. Sell Rate: {eur_rate_sell}\n🇵🇱zł PLN Exchange Rate: {pln_rate}')
        logger.info(f'Exchange rates sent to user {update.effective_user.id}')

    # pylint: disable=broad-except    
    except Exception as e:
        await update.message.reply_text('Error heppened, please try again later.')
        logger.error(f'Error fetching exchange rates: {str(e)}')

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

def main() -> None:

    global LOG_RATE

    # Load environment variables
    load_dotenv()
    TOKEN = os.getenv("BOT_TOKEN")
    PULL_INTERVAL = os.getenv("PULL_INTERVAL")
    LOG_RATE = os.getenv("LOG_RATE")

    if PULL_INTERVAL is None:
        logger.info("PULL_INTERVAL is not defined, using default value 300")
        PULL_INTERVAL = 300
    
    try:
        PULL_INTERVAL = int(PULL_INTERVAL)
    except ValueError:
        logger.error("PULL_INTERVAL must be an integer")
        logger.error("Using default value 300")
        PULL_INTERVAL = 300
    
    if not 15 <= PULL_INTERVAL <= 3600:
        logger.error("PULL_INTERVAL must be an integer between 15 and 3600")
        logger.error("Using default value 300")
        PULL_INTERVAL = 300

    # Ensure the token is set
    if TOKEN is None:
        logger.error("BOT_TOKEN is required")
        return

    logger.info(f"PULL_INTERVAL is set to {PULL_INTERVAL}")
    logger.info("BOT_TOKEN is provided. Starting bot...")

    # Check if logging exchange rates to CSV is enabled
    if LOG_RATE is None or LOG_RATE.lower() not in ['true', '1', 'yes']:
        LOG_RATE = False
        logging.info('LOG_RATE is False or not defined, CSV logging is disabled.')
    else:
        LOG_RATE = True
        logger.info(f'LOG_RATE is set to {LOG_RATE}')
        logger.info("Format of CSV file: Date, Time, USD Buy Rate, USD Sell Rate, EUR Buy Rate, EUR Sell Rate, PLN Exchange Rate")

    # Get rate once and schedule the job to fetch exchange rates every 1 minute
    logger.info(f'Scheduling exchange rates fetching every {PULL_INTERVAL} seconds.')
    schedule.every(PULL_INTERVAL).seconds.do(get_exchange_rates)
    schedule.run_all()
    thread = threading.Thread(target=run_schedule)
    thread.start()

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rate", rate))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, help_command))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()