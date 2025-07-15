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
import time
from queue import Queue

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

def get_stock_analysis(symbol):
    """Synchronous function to get stock analysis"""
    try:
        stock = yf.Ticker(symbol)
        
        # Get stock info and historical data
        info = stock.info
        hist = stock.history(period="3mo")
        
        if hist.empty:
            return None, "No data found"
        
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
            analysis = response.choices[0].message.content
            return analysis, None
        except Exception as e:
            logging.error(f"OpenAI API error: {e}")
            return None, "Failed to get AI analysis"
            
    except Exception as e:
        logging.error(f"Error in get_stock_analysis: {e}")
        return None, f"Error fetching data: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! Send a stock symbol like TCS.NS or INFY.NS to get AI stock analysis.")

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        symbol = update.message.text.upper().strip()
        
        if not symbol or len(symbol) < 2:
            await update.message.reply_text("Please provide a valid stock symbol (e.g., TCS.NS, INFY.NS)")
            return
        
        await update.message.reply_text(f"🔍 Analyzing {symbol}... Please wait.")
        
        # Run the synchronous analysis in a thread
        loop = asyncio.get_event_loop()
        analysis, error = await loop.run_in_executor(None, get_stock_analysis, symbol)
        
        if error:
            await update.message.reply_text(f"❌ {error}")
        else:
            await update.message.reply_text(f"📈 {symbol}:\n\n{analysis}")
            
    except Exception as e:
        logging.error(f"Unexpected error in analyze: {e}")
        await update.message.reply_text("❌ An unexpected error occurred. Please try again.")

# Create bot instance
bot = Bot(token=TELEGRAM_TOKEN)

# Message queue for processing updates
update_queue = Queue()

def process_updates():
    """Background thread to process updates"""
    while True:
        try:
            json_data = update_queue.get()
            if json_data is None:  # Shutdown signal
                break
            
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Build application
                application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
                application.add_handler(CommandHandler("start", start))
                application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze))
                
                # Process update
                async def process():
                    await application.initialize()
                    update = Update.de_json(json_data, application.bot)
                    await application.process_update(update)
                    await application.shutdown()
                
                loop.run_until_complete(process())
                
            except Exception as e:
                logging.error(f"Error processing update: {e}")
            finally:
                loop.close()
                
        except Exception as e:
            logging.error(f"Error in update processor: {e}")
        finally:
            update_queue.task_done()

# Start background thread
processor_thread = threading.Thread(target=process_updates, daemon=True)
processor_thread.start()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_data = request.get_json(force=True)
        
        # Add to queue for processing
        update_queue.put(json_data)
        
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
