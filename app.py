import asyncio
import websockets
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import aiohttp

# ===== CONFIGURATION =====
symbol = "R_75_1s"  # Change to "R_75" for normal Volatility 75
granularity = 60  # 1-minute candles
telegram_token = "6442914504:AAH3dU5zHrs******"  # your bot token
telegram_chat_id = "6442914504"
whatsapp_group_name = "BAYNEX Signals"
app_id = "1089"

# ===== SETUP LOGGING PATHS =====
Path("./logs").mkdir(parents=True, exist_ok=True)
log_file = f"./logs/{symbol}_candles.jsonl"

# ===== TELEGRAM ALERT FUNCTION =====
async def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {"chat_id": telegram_chat_id, "text": message}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as response:
            await response.text()

# ===== WHATSAPP PLACEHOLDER =====
async def send_whatsapp_message(message: str):
    print(f"[WhatsApp] {message} -> {whatsapp_group_name}")

# ===== WRITE CANDLE DATA TO DISK =====
def save_candle(candle: dict):
    with open(log_file, "a") as f:
        f.write(json.dumps(candle) + "\n")

# ======= HISTORICAL FETCHER =========
async def fetch_historical_candles():
    uri = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
    start_time = int((datetime.utcnow() - timedelta(days=730)).timestamp())  # 2 years back
    end_time = int(datetime.utcnow().timestamp())
    chunk_size = 5000
    current = start_time

    async with websockets.connect(uri) as ws:
        while current < end_time:
            chunk_end = min(current + chunk_size * granularity, end_time)
            request = {
                "ticks_history": symbol,
                "style": "candles",
                "granularity": granularity,
                "start": current,
                "end": chunk_end,
                "app_id": app_id
            }
            await ws.send(json.dumps(request))
            response = await ws.recv()
            data = json.loads(response)

            if "candles" in data:
                for candle in data["candles"]:
                    save_candle(candle)

            current = chunk_end
            await asyncio.sleep(1)

# ======= LIVE CANDLE UPDATER =========
async def fetch_live_candle():
    uri = "wss://ws.binaryws.com/websockets/v3?app_id=1089"

    async with websockets.connect(uri) as ws:
        payload = {
            "ticks_history": symbol,
            "style": "candles",
            "granularity": granularity,
            "end": "latest",
            "count": 1,
            "subscribe": 1,
            "app_id": app_id
        }
        await ws.send(json.dumps(payload))

        async for message in ws:
            data = json.loads(message)
            if "candles" in data:
                candle = data["candles"][0]
                save_candle(candle)
                timestamp = datetime.utcfromtimestamp(candle["epoch"]).strftime('%Y-%m-%d %H:%M:%S')
                price = candle["close"]
                msg = f"[{symbol}] Live Close: {price} @ {timestamp}"
                await send_telegram_message(msg)
                await send_whatsapp_message(msg)

# ===== MAIN RUNNER =====
async def main():
    print("📡 Starting Historical Download...")
    await fetch_historical_candles()
    print("✅ Historical Done. Now Listening Live...")
    await fetch_live_candle()

if __name__ == "__main__":
    asyncio.run(main())
