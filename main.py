import logging
import yfinance as yf
import pandas_ta as ta
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import os
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_ID = "google/gemma-3n-e2b-it:free"

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! Send a stock symbol like TCS.NS or INFY.NS to get AI stock analysis.")

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = update.message.text.upper()
    stock = yf.Ticker(symbol)
    info = stock.info
    hist = stock.history(period="3mo")

    if hist.empty:
        await update.message.reply_text(f"No data for {symbol}")
        return

    hist["RSI"] = ta.rsi(hist["Close"])
    macd = ta.macd(hist["Close"])
    if macd is not None:
        hist = hist.join(macd)

    rsi = round(hist["RSI"].dropna().iloc[-1], 2) if "RSI" in hist else "N/A"
    macd_val = round(hist["MACD_12_26_9"].dropna().iloc[-1], 2) if "MACD_12_26_9" in hist else "N/A"

    prompt = f"""
You're an AI stock analyst. Give a Buy/Sell/Hold for:

Name: {info.get('shortName', 'N/A')}
Symbol: {symbol}
PE Ratio: {info.get('trailingPE')}
Profit Margin: {info.get('profitMargins')}
Revenue: {info.get('totalRevenue')}
RSI: {rsi}
MACD: {macd_val}

Explain in simple words.
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": prompt}]
    }

    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)

    if response.status_code == 200:
        result = response.json()
        msg = result["choices"][0]["message"]["content"]
        await update.message.reply_text(f"📈 {symbol}:\n\n{msg}")
    else:
        await update.message.reply_text("❌ Failed to get analysis.")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler(None, analyze))  # catch-all

app.run_polling()
