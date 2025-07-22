# main.py

import os
import time
import json
import websocket
import requests
from datetime import datetime

TELEGRAM_BOT_TOKEN = 'YOUR_BOT_TOKEN'
TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID'

def send_telegram_message(message: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def store_historical_candles(symbol, candles):
    os.makedirs('historical', exist_ok=True)
    path = f"historical/{symbol.replace(' ', '_')}_candles.json"
    with open(path, "w") as f:
        json.dump(candles, f, indent=2)
    print(f"✅ Saved: {path}")
    send_telegram_message(f"✅ Saved {len(candles)} candles for {symbol}")

def fetch_historical_candles(symbol, years=2):
    start_time = int(time.time()) - years * 365 * 24 * 60 * 60
    end_time = int(time.time())
    all_candles = []

    def on_message(ws, message):
        nonlocal all_candles
        data = json.loads(message)
        candles = data.get("candles", [])
        if candles:
            all_candles.extend(candles)
        ws.close()

    def on_error(ws, error):
        print("WebSocket error:", error)
        send_telegram_message("❌ WebSocket error fetching candles")

    while start_time < end_time:
        chunk_end = min(start_time + 5000 * 60, end_time)
        ws = websocket.WebSocketApp(
            "wss://ws.derivws.com/websockets/v3",
            on_message=on_message,
            on_error=on_error
        )

        payload = {
            "ticks_history": symbol,
            "style": "candles",
            "granularity": 60,
            "start": start_time,
            "end": chunk_end,
            "subscribe": 0
        }

        ws.on_open = lambda ws: ws.send(json.dumps(payload))
        ws.run_forever()
        if all_candles:
            start_time = all_candles[-1]["epoch"] + 60
        else:
            break
        time.sleep(1)

    print(f"✅ Downloaded {len(all_candles)} candles")
    store_historical_candles(symbol, all_candles)

def fetch_live_candle(symbol):
    live_candle = {}

    def on_message(ws, message):
        nonlocal live_candle
        data = json.loads(message)
        candle = data.get("ohlc")
        if candle:
            live_candle.update({
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
                "epoch": int(candle["epoch"])
            })
        ws.close()

    def on_error(ws, error):
        print(f"Live feed error: {error}")
        send_telegram_message("❌ Live candle fetch error")

    ws = websocket.WebSocketApp(
        "wss://ws.derivws.com/websockets/v3",
        on_message=on_message,
        on_error=on_error
    )
    payload = {
        "ticks_history": symbol,
        "style": "candles",
        "granularity": 60,
        "end": "latest",
        "count": 1,
        "subscribe": 1
    }
    ws.on_open = lambda ws: ws.send(json.dumps(payload))
    ws.run_forever()

    return live_candle

def main():
    symbols = ["R_75", "R_75_1S"]  # Volatility 75 and Volatility 75 1s
    for symbol in symbols:
        try:
            print(f"\n📊 Fetching historical data for {symbol}...")
            send_telegram_message(f"📊 Starting historical data fetch for {symbol}")
            fetch_historical_candles(symbol)

            print(f"\n🔍 Fetching live candle for {symbol}...")
            live = fetch_live_candle(symbol)
            print("Live candle:", live)
            send_telegram_message(f"🔴 Live candle for {symbol}:\n{live}")

        except Exception as e:
            error_msg = f"❌ Error for {symbol}: {e}"
            print(error_msg)
            send_telegram_message(error_msg)

if __name__ == "__main__":
    main()
