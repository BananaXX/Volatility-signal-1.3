import time
import json
import os
import websocket
from datetime import datetime
from typing import List

CANDLE_DIR = "candles"

def store_historical_candles(symbol: str, candles: List[dict]):
    filename = os.path.join(CANDLE_DIR, f"{symbol.replace(' ', '_')}_candles.json")
    os.makedirs(CANDLE_DIR, exist_ok=True)
    with open(filename, "w") as f:
        json.dump(candles, f, indent=2)
    print(f"[📦] Stored {len(candles)} candles for {symbol} in {filename}")

def fetch_historical_candles(symbol, years=2):
    import websocket
    import json

    start_time = int(time.time()) - years * 365 * 24 * 60 * 60
    end_time = int(time.time())
    all_candles = []

    def on_message(ws, message):
        data = json.loads(message)
        candles = data.get('candles', [])
        if candles:
            all_candles.extend(candles)
        ws.close()

    def on_error(ws, error):
        print("❌ WebSocket error:", error)
        ws.close()

    while start_time < end_time:
        chunk_end = min(start_time + 5000 * 60, end_time)
        ws = websocket.WebSocketApp(
            "wss://ws.derivws.com/websockets/v3",
            on_message=on_message,
            on_error=on_error,
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
            start_time = all_candles[-1]['epoch'] + 60
        else:
            break

    print(f"✅ Downloaded {len(all_candles)} historical candles.")
    store_historical_candles(symbol, all_candles)

def load_historical_candles(symbol: str) -> List[dict]:
    filename = os.path.join(CANDLE_DIR, f"{symbol.replace(' ', '_')}_candles.json")
    if not os.path.exists(filename):
        print(f"📡 No cached data found for {symbol}, fetching...")
        fetch_historical_candles(symbol)
    else:
        print(f"[📁] Loading cached candles from {filename}")
    with open(filename, "r") as f:
        return json.load(f)

# Example usage (remove if called from elsewhere):
if __name__ == "__main__":
    symbol = "R_75_1s"  # For Volatility 75 1s index
    candles = load_historical_candles(symbol)
    print(f"[🔢] Total candles loaded: {len(candles)}")
