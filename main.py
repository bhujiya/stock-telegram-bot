import logging
import yfinance as yf
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import os
import pandas as pd
import numpy as np

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_ID = "google/gemma-3n-e2b-it:free"

logging.basicConfig(level=logging.INFO)

def calculate_rsi(prices, period=14):
    """Calculate RSI manually"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calculate MACD manually"""
    ema_fast = prices.ewm(span=fast).mean()
    ema_slow = prices.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    return macd, signal_line

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! Send a stock symbol like TCS.NS or INFY.NS to get AI stock analysis.")

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        symbol = update.message.text.upper().strip()
        
        # Basic validation
        if not symbol or len(symbol) < 2:
            await update.message.reply_text("Please provide a valid stock symbol (e.g., TCS.NS, INFY.NS)")
            return
        
        await update.message.reply_text(f"🔍 Analyzing {symbol}... Please wait.")
        
        # Fetch stock data
        stock = yf.Ticker(symbol)
        
        try:
            info = stock.info
            hist = stock.history(period="3mo")
        except Exception as e:
            logging.error(f"Error fetching data for {symbol}: {e}")
            await update.message.reply_text(f"❌ Error fetching data for {symbol}. Please check the symbol.")
            return

        if hist.empty:
            await update.message.reply_text(f"❌ No data found for {symbol}. Please check the symbol.")
            return

        # Calculate technical indicators
        try:
            rsi_values = calculate_rsi(hist["Close"])
            macd_values, signal_values = calculate_macd(hist["Close"])
        except Exception as e:
            logging.error(f"Error calculating indicators: {e}")
            rsi_values = pd.Series([np.nan] * len(hist))
            macd_values = pd.Series([np.nan] * len(hist))

        # Extract values safely
        rsi = "N/A"
        macd_val = "N/A"
        
        try:
            if not rsi_values.dropna().empty:
                rsi = round(rsi_values.dropna().iloc[-1], 2)
            if not macd_values.dropna().empty:
                macd_val = round(macd_values.dropna().iloc[-1], 4)
        except Exception as e:
            logging.error(f"Error extracting indicator values: {e}")

        # Create prompt
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

        # Call OpenRouter API
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions", 
                headers=headers, 
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                msg = result["choices"][0]["message"]["content"]
                await update.message.reply_text(f"📈 {symbol}:\n\n{msg}")
            else:
                logging.error(f"API Error: {response.status_code} - {response.text}")
                await update.message.reply_text("❌ Failed to get analysis from AI service.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error: {e}")
            await update.message.reply_text("❌ Network error. Please try again.")
            
    except Exception as e:
        logging.error(f"Unexpected error in analyze: {e}")
        await update.message.reply_text("❌ An unexpected error occurred. Please try again.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by Updates."""
    logging.error(f"Update {update} caused error {context.error}")

def main():
    if not TELEGRAM_TOKEN:
        logging.error("TELEGRAM_TOKEN not found in environment variables")
        return
    
    if not OPENROUTER_API_KEY:
        logging.error("OPENROUTER_API_KEY not found in environment variables")
        return
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze))
    
    # Add error handler
    app.add_error_handler(error_handler)
    
    # Start the bot
    logging.info("Starting bot...")
    app.run_polling()

if __name__ == "__main__":
    main()
