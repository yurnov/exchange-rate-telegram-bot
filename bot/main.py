#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import requests
import os
import re
import schedule
import time
import threading
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from database import ExchangeRateDatabase

MONOBANK_API_URL = "https://api.monobank.ua/bank/currency"
NATIONAL_BANK_API_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"

# Initialize exchange rates
usd_rate = 0
usd_rate_sell = 0
eur_rate = 0
eur_rate_sell = 0
pln_rate = 0
usd_rate_nbu = 0
eur_rate_nbu = 0
pln_rate_nbu = 0
# EUR to USD conversion rates
eur_usd_rate = 0
eur_usd_rate_sell = 0
LOG_RATE = False
DB_ENABLED = False
db = None

# Enable initial logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def get_exchange_rates():
    logger.info("Fetching exchange rates from Monobank API")

    # pylint: disable=global-statement
    global usd_rate, usd_rate_sell, eur_rate, eur_rate_sell, pln_rate, usd_rate_nbu, eur_rate_nbu, pln_rate_nbu, eur_usd_rate, eur_usd_rate_sell, db
    # pylint: disable=broad-except
    
    monobank_data = []
    nbu_data = []
    timestamp = datetime.now()
    
    try:
        # Fetching exchange rates from Monobank API
        response = requests.get(MONOBANK_API_URL, timeout=10)
        monobank_data = response.json()
        
        usd_rate = next(item for item in monobank_data if item["currencyCodeA"] == 840 and item["currencyCodeB"] == 980)[
            "rateBuy"
        ]
        usd_rate_sell = next(item for item in monobank_data if item["currencyCodeA"] == 840 and item["currencyCodeB"] == 980)[
            "rateSell"
        ]
        eur_rate = next(item for item in monobank_data if item["currencyCodeA"] == 978 and item["currencyCodeB"] == 980)[
            "rateBuy"
        ]
        eur_rate_sell = next(item for item in monobank_data if item["currencyCodeA"] == 978 and item["currencyCodeB"] == 980)[
            "rateSell"
        ]
        pln_rate = next(item for item in monobank_data if item["currencyCodeA"] == 985 and item["currencyCodeB"] == 980)[
            "rateCross"
        ]
        # EUR to USD rate (currencyCodeA: 978 is EUR, currencyCodeB: 840 is USD)
        eur_usd_item = next(item for item in monobank_data if item["currencyCodeA"] == 978 and item["currencyCodeB"] == 840)
        eur_usd_rate = eur_usd_item["rateBuy"]
        eur_usd_rate_sell = eur_usd_item["rateSell"]

        logger.info(
            f"USD Buy Rate: {usd_rate}. Sell Rate: {usd_rate_sell}. EUR Buy Rate: {eur_rate}. Sell Rate: {eur_rate_sell}. PLN Exchange Rate: {pln_rate}. EUR/USD Buy Rate: {eur_usd_rate}. Sell Rate: {eur_usd_rate_sell}"
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error fetching exchange rates: {str(e)}")

    # Log exchange rates to CSV file
    # format of CSV file: Date Time, USD Buy Rate, USD Sell Rate, EUR Buy Rate, EUR Sell Rate, PLN Exchange Rate
    if LOG_RATE:
        if usd_rate != 0 or usd_rate_sell != 0 or eur_rate != 0 or eur_rate_sell != 0 or pln_rate != 0:
            try:
                with open("exchange_rates.csv", "a", encoding="utf-8") as file:
                    file.write(
                        f'{time.strftime("%Y-%m-%d %H:%M:%S")},{usd_rate},{usd_rate_sell},{eur_rate},{eur_rate_sell},{pln_rate}\n'
                    )
                logger.info("Exchange rates written to exchange_rates.csv")
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Error writing to exchange_rates.csv: {str(e)}")
        else:
            logger.error("Exchange rates are not fetched, not writing to exchange_rates.csv")

    try:
        # Fetching exchange rates from National Bank of Ukraine API
        response = requests.get(NATIONAL_BANK_API_URL, timeout=10)
        nbu_data = response.json()
        usd_rate_nbu = next(item for item in nbu_data if item["cc"] == "USD")["rate"]
        eur_rate_nbu = next(item for item in nbu_data if item["cc"] == "EUR")["rate"]
        pln_rate_nbu = next(item for item in nbu_data if item["cc"] == "PLN")["rate"]

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error fetching exchange rates from NBU: {str(e)}")
    
    # Store ALL exchange rates in database if enabled
    if DB_ENABLED and db:
        try:
            if monobank_data:
                logger.info(f"Storing {len(monobank_data)} Monobank rates to database")
                db.insert_exchange_rates(monobank_data, 'monobank', timestamp)
            
            if nbu_data:
                logger.info(f"Storing {len(nbu_data)} NBU rates to database")
                db.insert_exchange_rates(nbu_data, 'nbu', timestamp)
                
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Error storing rates to database: {str(e)}")


# pylint: disable=unused-argument
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}, "
        "I'm an exchange rate bot. I can help you check the current exchange rates for USD, EUR, and PLN in UAH. "
        "Use /mono to get Monobank exchange rates or /nbu to get NBU exchange rates. "
        "You can also use /help to see all available commands."
    )


# pylint: disable=unused-argument
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Hi, I'm the Exchange Rate Bot!\n\n"
        "Here are the commands you can use:\n"
        "/rate - Get the latest exchange rates.\n"
        "/mono - Get exchange rates from Monobank.\n"
        "/nbu - Get exchange rates from the National Bank of Ukraine (NBU).\n"
        "/usd - Get USD exchange rates.\n"
        "/eur - Get EUR exchange rates.\n"
        "/pln - Get PLN exchange rates.\n"
        "/calc - Convert currencies (e.g., /calc 100 USD to UAH, /calc 100 EUR to USD).\n\n"
        "All rates are based on 🇺🇦 Ukrainian Hryvnia (UAH ₴).\n"
        "EUR ↔ USD conversion is also supported.\n\n"
        "Powered by Monobank API."
    )


# pylint: disable=unused-argument
async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.effective_user.id} requested exchange rates.")
    try:
        await update.message.reply_text(
            f"🇺🇸 USD:\n  Buy Rate: {usd_rate}\n  Sell Rate: {usd_rate_sell}\n  NBU Rate: {usd_rate_nbu}\n\n"
            f"🇪🇺 EUR:\n  Buy Rate: {eur_rate}\n  Sell Rate: {eur_rate_sell}\n  NBU Rate: {eur_rate_nbu}\n\n"
            f"🇵🇱 PLN:\n  Exchange Rate: {pln_rate}\n  NBU Rate: {pln_rate_nbu}"
        )
        logger.info(f"Exchange rates sent to user {update.effective_user.id}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        await update.message.reply_text("An error occurred. Please try again later.")
        logger.error(f"Error fetching exchange rates: {str(e)}")


# pylint: disable=unused-argument
async def mono_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.effective_user.id} requested Monobank rates.")
    try:
        await update.message.reply_text(
            f"🇺🇸 USD:\n  Buy Rate: {usd_rate}\n  Sell Rate: {usd_rate_sell}\n\n"
            f"🇪🇺 EUR:\n  Buy Rate: {eur_rate}\n  Sell Rate: {eur_rate_sell}\n\n"
            f"🇵🇱 PLN:\n  Exchange Rate: {pln_rate}"
        )
        logger.info(f"Monobank rates sent to user {update.effective_user.id}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        await update.message.reply_text("An error occurred. Please try again later.")
        logger.error(f"Error fetching Monobank rates: {str(e)}")


async def nbu_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.effective_user.id} requested NBU rates.")
    try:
        await update.message.reply_text(
            f"NBU Rates:\n🇺🇸 USD: {usd_rate_nbu}\n🇪🇺 EUR: {eur_rate_nbu}\n🇵🇱 PLN: {pln_rate_nbu}"
        )
        logger.info(f"NBU rates sent to user {update.effective_user.id}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        await update.message.reply_text("An error occurred. Please try again later.")
        logger.error(f"Error fetching NBU rates: {str(e)}")


# pylint: disable=unused-argument
async def usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.effective_user.id} requested exchange rates.")
    try:
        await update.message.reply_text(
            f"🇺🇸 USD:\n  Buy Rate: {usd_rate}\n  Sell Rate: {usd_rate_sell}\n  NBU Rate: {usd_rate_nbu}\n\n"
        )
        logger.info(f"Exchange rates sent to user {update.effective_user.id}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        await update.message.reply_text("An error occurred. Please try again later.")
        logger.error(f"Error fetching exchange rates: {str(e)}")


async def eur(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.effective_user.id} requested exchange rates.")
    try:
        await update.message.reply_text(
            f"🇪🇺 EUR:\n  Buy Rate: {eur_rate}\n  Sell Rate: {eur_rate_sell}\n  NBU Rate: {eur_rate_nbu}\n\n"
        )
        logger.info(f"Exchange rates sent to user {update.effective_user.id}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        await update.message.reply_text("An error occurred. Please try again later.")
        logger.error(f"Error fetching exchange rates: {str(e)}")


async def pln(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"User {update.effective_user.id} requested exchange rates.")
    try:
        await update.message.reply_text(f"🇵🇱 PLN:\n  Exchange Rate: {pln_rate}\n  NBU Rate: {pln_rate_nbu}")
        logger.info(f"Exchange rates sent to user {update.effective_user.id}")
    except Exception as e:  # pylint: disable=broad-exception-caught
        await update.message.reply_text("An error occurred. Please try again later.")
        logger.error(f"Error fetching exchange rates: {str(e)}")


def convert_currency(amount: float, from_currency: str, to_currency: str) -> tuple[float | None, None]:
    """
    Convert currency using Monobank rates.
    For USD and EUR: uses sell rate when converting TO UAH, buy rate when converting FROM UAH
    For PLN: uses single cross rate
    For EUR <-> USD: uses direct EUR/USD rates from Monobank

    Returns: (result, None) tuple where result is the converted amount or None if conversion fails
    """
    from_curr = from_currency.upper()
    to_curr = to_currency.upper()

    # UAH -> USD (use buy rate)
    if from_curr == "UAH" and to_curr == "USD":
        if usd_rate == 0:
            return None, None
        return amount / usd_rate, None

    # USD -> UAH (use sell rate)
    if from_curr == "USD" and to_curr == "UAH":
        if usd_rate_sell == 0:
            return None, None
        return amount * usd_rate_sell, None

    # UAH -> EUR (use buy rate)
    if from_curr == "UAH" and to_curr == "EUR":
        if eur_rate == 0:
            return None, None
        return amount / eur_rate, None

    # EUR -> UAH (use sell rate)
    if from_curr == "EUR" and to_curr == "UAH":
        if eur_rate_sell == 0:
            return None, None
        return amount * eur_rate_sell, None

    # UAH -> PLN (single rate)
    if from_curr == "UAH" and to_curr == "PLN":
        if pln_rate == 0:
            return None, None
        return amount / pln_rate, None

    # PLN -> UAH (single rate)
    if from_curr == "PLN" and to_curr == "UAH":
        if pln_rate == 0:
            return None, None
        return amount * pln_rate, None

    # EUR -> USD (use sell rate)
    if from_curr == "EUR" and to_curr == "USD":
        if eur_usd_rate_sell == 0:
            return None, None
        return amount * eur_usd_rate_sell, None

    # USD -> EUR (use buy rate)
    if from_curr == "USD" and to_curr == "EUR":
        if eur_usd_rate == 0:
            return None, None
        return amount / eur_usd_rate, None

    return None, None


async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle currency conversion command."""
    logger.info(f"User {update.effective_user.id} requested currency conversion.")

    # Get the text after /calc command
    if context.args:
        text = ' '.join(context.args)
    else:
        await update.message.reply_text(
            "Please provide a conversion request.\n"
            "Usage: /calc <amount> <FROM> to <TO>\n"
            "Examples:\n"
            "  /calc 100 USD to UAH\n"
            "  /calc 1000 UAH to EUR\n"
            "  /calc 500 PLN to UAH\n"
            "  /calc 100 EUR to USD\n\n"
            "Supported currencies: USD, EUR, PLN, UAH"
        )
        return

    # Parse the conversion request
    # Pattern: <amount> <currency> to <currency>
    pattern = r'(\d+(?:\.\d+)?)\s*(USD|EUR|PLN|UAH)\s+to\s+(USD|EUR|PLN|UAH)'
    match = re.match(pattern, text, re.IGNORECASE)

    if not match:
        await update.message.reply_text(
            "Invalid format. Please use: /calc <amount> <FROM> to <TO>\n"
            "Examples:\n"
            "  /calc 100 USD to UAH\n"
            "  /calc 1000 UAH to EUR\n"
            "  /calc 500 PLN to UAH\n"
            "  /calc 100 EUR to USD"
        )
        return

    amount = float(match.group(1))
    from_currency = match.group(2).upper()
    to_currency = match.group(3).upper()

    # Check if this is a valid conversion pair
    # Allow: any currency <-> UAH, and EUR <-> USD
    is_eur_usd = (from_currency == "EUR" and to_currency == "USD") or (from_currency == "USD" and to_currency == "EUR")
    is_uah_conversion = from_currency == "UAH" or to_currency == "UAH"

    if not is_eur_usd and not is_uah_conversion:
        await update.message.reply_text(
            "❌ Conversions must be to or from UAH, or between EUR and USD.\n"
            "Please convert to UAH first, then to the desired currency."
        )
        return

    if from_currency == to_currency:
        await update.message.reply_text(f"🔄 {amount:.2f} {from_currency} = {amount:.2f} {to_currency}")
        return

    result, _ = convert_currency(amount, from_currency, to_currency)

    if result is None:
        await update.message.reply_text("❌ Exchange rates are not available. Please try again later.")
        return

    # Currency flags
    flags = {"USD": "🇺🇸", "EUR": "🇪🇺", "PLN": "🇵🇱", "UAH": "🇺🇦"}

    from_flag = flags.get(from_currency, "")
    to_flag = flags.get(to_currency, "")

    # Determine which rate was used for the message
    if from_currency == "EUR" and to_currency == "USD":
        rate_info = f"(EUR/USD sell rate: {eur_usd_rate_sell})"
    elif from_currency == "USD" and to_currency == "EUR":
        rate_info = f"(EUR/USD buy rate: {eur_usd_rate})"
    elif from_currency in ["USD", "EUR"] or to_currency in ["USD", "EUR"]:
        if from_currency == "USD":
            rate_info = f"(sell rate: {usd_rate_sell})"
        elif to_currency == "USD":
            rate_info = f"(buy rate: {usd_rate})"
        elif from_currency == "EUR":
            rate_info = f"(sell rate: {eur_rate_sell})"
        else:  # to_currency == "EUR"
            rate_info = f"(buy rate: {eur_rate})"
    else:
        rate_info = f"(rate: {pln_rate})"

    await update.message.reply_text(
        f"{from_flag} {amount:.2f} {from_currency} = {to_flag} {result:.2f} {to_currency}\n{rate_info}"
    )
    logger.info(f"Conversion result sent to user {update.effective_user.id}")


def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)


def main() -> None:

    # pylint: disable=global-statement
    global LOG_RATE, DB_ENABLED, db

    # Load environment variables
    load_dotenv()
    TOKEN = os.getenv("BOT_TOKEN")
    PULL_INTERVAL = os.getenv("PULL_INTERVAL")
    LOG_RATE = os.getenv("LOG_RATE")
    LOG_LEVEL = os.getenv("LOG_LEVEL")
    DB_ENABLED = os.getenv("DB_ENABLED")
    DB_PATH = os.getenv("DB_PATH")

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
    if LOG_RATE is None or LOG_RATE.lower() not in ["true", "1", "yes"]:
        LOG_RATE = False
        logging.info("LOG_RATE is False or not defined, CSV logging is disabled.")
    else:
        LOG_RATE = True
        logger.info(f"LOG_RATE is set to {LOG_RATE}")
        logger.info(
            "Format of CSV file: Date Time, USD Buy Rate, USD Sell Rate, EUR Buy Rate, EUR Sell Rate, "
            + "PLN Exchange Rate"
        )
    
    # Check if database logging is enabled
    if DB_ENABLED is None or DB_ENABLED.lower() not in ["true", "1", "yes"]:
        DB_ENABLED = False
        logger.info("DB_ENABLED is False or not defined, database logging is disabled.")
    else:
        DB_ENABLED = True
        logger.info(f"DB_ENABLED is set to {DB_ENABLED}")
        
        # Initialize database
        if DB_PATH is None or DB_PATH == "":
            DB_PATH = "data/exchange_rates.db"
            logger.info(f"DB_PATH not defined, using default: {DB_PATH}")
        else:
            logger.info(f"DB_PATH is set to {DB_PATH}")
        
        try:
            db = ExchangeRateDatabase(DB_PATH)
            db.connect()
            logger.info("Database initialized successfully")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Error initializing database: {e}")
            logger.error("Continuing without database logging")
            DB_ENABLED = False

    # Get rate once and schedule the job to fetch exchange rates every 1 minute
    logger.info(f"Scheduling exchange rates fetching every {PULL_INTERVAL} seconds.")
    schedule.every(PULL_INTERVAL).seconds.do(get_exchange_rates)
    schedule.run_all()
    thread = threading.Thread(target=run_schedule)
    thread.start()

    if LOG_LEVEL is None or LOG_LEVEL.lower() not in [
        "debug",
        "info",
        "warning",
        "error",
        "critical",
    ]:
        LOG_LEVEL = "info"
        logger.info("LOG_LEVEL is not defined or invalid, using default value info")

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # Set runtime logging level
    if LOG_LEVEL.lower() != "info":
        logger.info(f"Switching LOG_LEVEL to user-defined value {LOG_LEVEL.upper()}")
    logger.setLevel(LOG_LEVEL.upper())

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rate", rate))
    application.add_handler(CommandHandler("mono", mono_rate))
    application.add_handler(CommandHandler("nbu", nbu_rate))
    application.add_handler(CommandHandler("usd", usd))
    application.add_handler(CommandHandler("eur", eur))
    application.add_handler(CommandHandler("pln", pln))
    application.add_handler(CommandHandler("calc", calc))
    # Catch-all handlers for unrecognized input - must be added AFTER all specific CommandHandlers
    # Handle non-command text messages (e.g., "calc" without slash)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, help_command))
    # Handle unrecognized commands (e.g., "/hepl" typo) - catches any /command not matched above
    application.add_handler(MessageHandler(filters.COMMAND, help_command))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
