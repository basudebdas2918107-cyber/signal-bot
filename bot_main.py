import os
import logging
import pandas as pd
import requests
import ta
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# === YOUR TELEGRAM BOT TOKEN ===
TOKEN = os.getenv("TOKEN") # 🔹 Replace this with your real token

# === LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Global Control for Auto Signals ===
auto_signal_running = False
auto_signal_task = None
chat_id_global = None

# === FETCH MARKET DATA (from Binance) ===
def fetch_market_data(symbol="EURUSDT", interval="1m", limit=100):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        data = response.json()

        df = pd.DataFrame(data, columns=[
            "Open time", "Open", "High", "Low", "Close", "Volume",
            "Close time", "Quote asset volume", "Number of trades",
            "Taker buy base asset volume", "Taker buy quote asset volume", "Ignore"
        ])

        df["Close"] = df["Close"].astype(float)
        df["Open"] = df["Open"].astype(float)
        df["High"] = df["High"].astype(float)
        df["Low"] = df["Low"].astype(float)
        return df
    except Exception as e:
        print(f"⚠️ Error fetching {symbol}: {e}")
        return pd.DataFrame()

# === STRATEGY LOGIC (EMA + Bollinger) ===
def generate_signal(df):
    if df.empty:
        return "⚠️ No data available"

    df["EMA50"] = ta.trend.ema_indicator(df["Close"], window=50)
    bb = ta.volatility.BollingerBands(close=df["Close"], window=20, window_dev=2)
    df["bb_bbm"] = bb.bollinger_mavg()
    df["bb_bbh"] = bb.bollinger_hband()
    df["bb_bbl"] = bb.bollinger_lband()

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    if latest["Close"] > latest["EMA50"] and previous["Close"] < previous["EMA50"]:
        return "📈 BUY (UP) — Price crossed above EMA50"
    elif latest["Close"] < latest["EMA50"] and previous["Close"] > previous["EMA50"]:
        return "📉 SELL (DOWN) — Price crossed below EMA50"
    elif latest["Close"] > latest["bb_bbm"] and latest["Close"] < latest["bb_bbh"]:
        return "📈 Weak BUY (Near upper band)"
    elif latest["Close"] < latest["bb_bbm"] and latest["Close"] > latest["bb_bbl"]:
        return "📉 Weak SELL (Near lower band)"
    else:
        return "⚠️ No clear signal"

# === ANALYZE ALL PAIRS ===
def analyze_all_pairs():
    pairs = {
        "EUR/USD": "EURUSDT",
        "GBP/USD": "GBPUSDT",
        "USD/JPY": "USDJPY",
        "USD/CHF": "USDCHF",
        "AUD/USD": "AUDUSDT",
        "NZD/USD": "NZDUSDT",
        "USD/CAD": "USDCAD"
    }

    results = []
    for name, symbol in pairs.items():
        df = fetch_market_data(symbol, "1m", 100)
        signal = generate_signal(df)
        results.append(f"{name}: {signal}")

    return "\n".join(results)

# === TELEGRAM COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_signal_running, chat_id_global, auto_signal_task

    chat_id_global = update.effective_chat.id
    if auto_signal_running:
        await update.message.reply_text("✅ Auto signal updates are already running!")
        return

    auto_signal_running = True
    await update.message.reply_text("🤖 Bot started! Auto signals every 5 minutes.\nUse /stop to turn it off.")

    auto_signal_task = asyncio.create_task(auto_signal_loop(context.bot, chat_id_global))

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_signal_running, auto_signal_task

    if auto_signal_running:
        auto_signal_running = False
        if auto_signal_task:
            auto_signal_task.cancel()
        await update.message.reply_text("🛑 Auto signal updates stopped.")
    else:
        await update.message.reply_text("⚠️ Auto updates are not running.")

async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Fetching live market data...")
    try:
        results = analyze_all_pairs()
        await update.message.reply_text(results)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

# === AUTO SIGNAL LOOP ===
async def auto_signal_loop(bot, chat_id):
    global auto_signal_running
    while auto_signal_running:
        try:
            results = analyze_all_pairs()
            await bot.send_message(chat_id=chat_id, text=f"📅 Auto Signal Update\n\n{results}")
            print("✅ Auto signals sent.")
        except Exception as e:
            print(f"⚠️ Auto signal error: {e}")
        await asyncio.sleep(300)  # every 5 minutes

# === MAIN FUNCTION ===
async def main():
    print("🚀 Starting Telegram Bot...")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("signal", signal))

    print("✅ Bot is running... Waiting for commands.")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    import asyncio

    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
