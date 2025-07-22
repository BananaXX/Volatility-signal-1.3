# realtime_analytics.py

import sqlite3
import websocket
import json
import threading
import time
import datetime
import requests

# === SETTINGS ===
symbol = "Volatility 75"
is_one_s = "(1s)" in symbol
granularity = 60  # 1-minute candles
history_days = 730  # ~2 years
store_db = "trading_data.db"

# === SYMBOL ID MAP ===
def get_symbol_id(symbol_name):
    if "(1s)" in symbol_name:
        symbol_name = symbol_name.replace(" (1s)", ".1s")
    return symbol_name.replace(" ", "_").lower()

# === DB SETUP ===
def init_db():
    conn = sqlite3.connect(store_db)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            timestamp INTEGER,
            open REAL,
            high REAL,
            low REAL,
            close REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            timestamp INTEGER,
            price REAL
        )
    """)
    conn.commit()
    conn.close()

# === STORE CANDLES ===
def store_candles_to_db(symbol, candles):
    conn = sqlite3.connect(store_db)
    cursor = conn.cursor()
    for candle in candles:
        cursor.execute("""
            INSERT OR REPLACE INTO candles (symbol, timestamp, open, high, low, close)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            candle["epoch"],
            candle["open"],
            candle["high"],
            candle["low"],
            candle["close"]
        ))
    conn.commit()
    conn.close()

# === FETCH HISTORICAL CANDLES ===
def fetch_historical_candles(symbol, days=history_days, granularity=granularity):
    print(f"[+] Fetching historical candles for {symbol} ({days} days)...")
    candles = []
    end_time = int(time.time())
    start_time = end_time - (days * 86400)
    symbol_id = get_symbol_id(symbol)

    while start_time < end_time:
        chunk_end = min(start_time + (1000 * granularity), end_time)
        url = f"https://api.binary.com/v3/price_history?symbol={symbol_id}&granularity={granularity}&start={start_time}&end={chunk_end}"
        try:
            r = requests.get(url)
            data = r.json()
            if "candles" in data:
                candles.extend(data["candles"])
            else:
                print("[!] No candles returned.")
        except Exception as e:
            print(f"[X] Error fetching candles: {e}")
        start_time = chunk_end
        time.sleep(1.5)

    store_candles_to_db(symbol, candles)
    print(f"[✓] Stored {len(candles)} candles to DB.")

# === TICK HANDLER ===
def process_tick(symbol, tick_data):
    conn = sqlite3.connect(store_db)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ticks (symbol, timestamp, price)
        VALUES (?, ?, ?)
    """, (symbol, tick_data["epoch"], tick_data["quote"]))
    conn.commit()
    conn.close()

# === WEBSOCKET CALLBACKS ===
def on_message(ws, message):
    msg = json.loads(message)
    if "tick" in msg:
        process_tick(symbol, msg["tick"])

def on_open(ws):
    print("[✓] WebSocket connected.")
    ws.send(json.dumps({
        "ticks": get_symbol_id(symbol),
        "subscribe": 1
    }))

def on_error(ws, error):
    print("[X] WebSocket error:", error)

def on_close(ws, close_status_code, close_msg):
    print("[X] WebSocket closed.")

# === START TICK STREAM ===
def run():
    websocket.enableTrace(False)
    ws = websocket.WebSocketApp(
        "wss://ws.binaryws.com/websockets/v3?app_id=1089",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()

# === MAIN ===
def main():
    init_db()
    fetch_historical_candles(symbol)
    run()
    while True:
        time.sleep(10)

if __name__ == "__main__":
    main()
