import logging import yfinance as yf import requests from telegram import Update from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters import os import pandas as pd import numpy as np from flask import Flask, request import asyncio

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") MODEL_ID = "google/gemma-3n-e2b-it:free"

logging.basicConfig(level=logging.INFO)

flask_app = Flask(name)

Telegram bot app

telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

def calculate_rsi(prices, period=14): delta = prices.diff() gain = delta.where(delta > 0, 0).rolling(window=period).mean() loss = -delta.where(delta < 0, 0).rolling(window=period).mean() rs = gain / loss rsi = 100 - (100 / (1 + rs)) return rsi

def calculate_macd(prices, fast=12, slow=26, signal=9): ema_fast = prices.ewm(span=fast).mean() ema_slow = prices.ewm(span=slow).mean() macd = ema_fast - ema_slow signal_line = macd.ewm(span=signal).mean() return macd, signal_line

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("Hi! Send a stock symbol like TCS.NS or INFY.NS to get AI stock analysis.")

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE): symbol = update.message.text.upper().strip() if not symbol or len(symbol) < 2: await update.message.reply_text("Please provide a valid stock symbol (e.g., TCS.NS, INFY.NS)") return

await update.message.reply_text(f"🔍 Analyzing {symbol}... Please wait.")
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

try:
    rsi_values = calculate_rsi(hist["Close"])
    macd_values, signal_values = calculate_macd(hist["Close"])
except Exception as e:
    logging.error(f"Error calculating indicators: {e}")
    rsi_values = pd.Series([np.nan] * len(hist))
    macd_values = pd.Series([np.nan] * len(hist))

rsi = "N/A"
macd_val = "N/A"

try:
    if not rsi_values.dropna().empty:
        rsi = round(rsi_values.dropna().iloc[-1], 2)
    if not macd_values.dropna().empty:
        macd_val = round(macd_values.dropna().iloc[-1], 4)
except Exception as e:
    logging.error(f"Error extracting indicator values: {e}")

prompt = f"""

You're an AI stock analyst. Give a Buy/Sell/Hold recommendation for:

Name: {info.get('shortName', 'N/A')} Symbol: {symbol} PE Ratio: {info.get('trailingPE', 'N/A')} Profit Margin: {info.get('profitMargins', 'N/A')} Revenue: {info.get('totalRevenue', 'N/A')} RSI: {rsi} MACD: {macd_val}

Provide a brief analysis in simple words with your recommendation. """

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

telegram_app.add_handler(CommandHandler("start", start)) telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze))

@flask_app.route("/webhook", methods=["POST"]) def webhook(): update = Update.de_json(request.get_json(force=True), telegram_app.bot) asyncio.run(telegram_app.process_update(update)) return "ok"

@flask_app.route("/") def root(): return "Stock Analysis Telegram Bot is running!"

if name == "main": port = int(os.environ.get("PORT", 10000)) flask_app.run(host="0.0.0.0", port=port)

