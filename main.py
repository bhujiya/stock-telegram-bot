import logging
import yfinance as yf
import requests
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import os
import pandas as pd
import numpy as np
from flask import Flask, request
import asyncio
import openai
import threading
from concurrent.futures import ThreadPoolExecutor

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_ID = "gpt-3.5-turbo"

openai.api_key = OPENAI_API_KEY

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

def calculate_rsi(prices, period=14):
    """Calculate RSI with better error handling"""
    try:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        logging.error(f"RSI calculation error: {e}")
        return pd.Series([np.nan] * len(prices))

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calculate MACD with better error handling"""
    try:
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal).mean()
        return macd, signal_line
    except Exception as e:
        logging.error(f"MACD calculation error: {e}")
        return pd.Series([np.nan] * len(prices)), pd.Series([np.nan] * len(prices))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! Send a stock symbol like TCS.NS or INFY.NS to get AI stock analysis.")

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        symbol = update.message.text.upper().strip()
        
        if not symbol or len(symbol) < 2:
            await update.message.reply_text("Please provide a valid stock symbol (e.g., TCS.NS, INFY.NS)")
            return
        
        await update.message.reply_text(f"🔍 Analyzing {symbol}... Please wait.")
        
        # Create a fresh ticker object for each request
        stock = yf.Ticker(symbol)
        
        try:
            # Get stock info and historical data
            info = stock.info
            hist = stock.history(period="3mo")
        except Exception as e:
            logging.error(f"Error fetching data for {symbol}: {e}")
            await update.message.reply_text(f"❌ Error fetching data for {symbol}. Please check the symbol and try again.")
            return

        if hist.empty:
            await update.message.reply_text(f"❌ No data found for {symbol}. Please check the symbol and try again.")
            return

        # Calculate technical indicators
        rsi_values = calculate_rsi(hist["Close"])
        macd_values, signal_values = calculate_macd(hist["Close"])

        # Extract latest values safely
        rsi = "N/A"
        macd_val = "N/A"
        
        try:
            if not rsi_values.dropna().empty:
                rsi = round(rsi_values.dropna().iloc[-1], 2)
            if not macd_values.dropna().empty:
                macd_val = round(macd_values.dropna().iloc[-1], 4)
        except Exception as e:
            logging.error(f"Error extracting indicator values: {e}")

        # Prepare prompt for OpenAI
        prompt = f"""
You're an AI stock analyst. Give a Buy/Sell/Hold recommendation for:

Name: {info.get('shortName', 'N/A')}
Symbol: {symbol}
PE Ratio: {info.get('trailingPE', 'N/A')}
Profit Margin: {info.get('profitMargins', 'N/A')}
Revenue: {info.get('totalRevenue', 'N/A')}
RSI: {rsi}
MACD: {macd_val}

Provide a brief analysis in simple words with your recommendation.
"""

        try:
            response = openai.chat.completions.create(
                model=MODEL_ID,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7
            )
            msg = response.choices[0].message.content
            await update.message.reply_text(f"📈 {symbol}:\n\n{msg}")

        except Exception as e:
            logging.error(f"OpenAI API error: {e}")
            await update.message.reply_text("❌ Failed to get analysis from AI service. Please try again.")
            
    except Exception as e:
        logging.error(f"Unexpected error in analyze: {e}")
        await update.message.reply_text("❌ An unexpected error occurred. Please try again.")

# Initialize Telegram app once
telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze))

# Initialize the app at startup
async def initialize_app():
    await telegram_app.initialize()

# Run initialization in a separate thread
def run_initialization():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(initialize_app())
    loop.close()

# Initialize at startup
init_thread = threading.Thread(target=run_initialization)
init_thread.start()
init_thread.join()

# Thread pool for handling webhook requests
executor = ThreadPoolExecutor(max_workers=5)

def process_update_sync(json_data):
    """Process update in a separate thread with its own event loop"""
    def run_async():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            update = Update.de_json(json_data, telegram_app.bot)
            loop.run_until_complete(telegram_app.process_update(update))
        except Exception as e:
            logging.error(f"Error processing update: {e}")
        finally:
            loop.close()
    
    return run_async()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_data = request.get_json(force=True)
        
        # Process the update in a separate thread
        future = executor.submit(process_update_sync, json_data)
        # Don't wait for completion to avoid blocking
        
        return 'OK'
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return 'ERROR', 500

@app.route('/health')
def health():
    return 'Bot is running'

@app.route('/')
def index():
    return 'Stock Analysis Telegram Bot is running!'

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
