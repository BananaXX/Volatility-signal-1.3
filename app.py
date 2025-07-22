import asyncio
import websockets
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import aiohttp
import logging

# ===== CONFIGURATION =====
symbol = "1HZ75V"  # ✅ CORRECT: 1-second Volatility 75 Index
granularity = 60  # 1-minute candles
telegram_token = "6442914504:AAH3dU5zHrs******"  # Your bot token
telegram_chat_id = "YOUR_ACTUAL_CHAT_ID"  # ⚠️ FIX THIS - Get from @userinfobot
whatsapp_group_name = "BAYNEX Signals"
app_id = "1089"

# ===== ENHANCED LOGGING =====
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

Path("./data").mkdir(parents=True, exist_ok=True)
Path("./logs").mkdir(parents=True, exist_ok=True)

candle_log = f"./data/{symbol}_candles.jsonl"
tick_log = f"./data/{symbol}_ticks.jsonl"
signals_log = f"./logs/{symbol}_signals.jsonl"

# ===== DIAMOND MANIPULATION DETECTOR =====
class DiamondDetector:
    def __init__(self):
        self.tick_buffer = []
        self.candle_buffer = []
        self.max_ticks = 1000  # Keep last 1000 ticks
        self.max_candles = 200  # Keep last 200 candles
        
    def add_tick(self, tick):
        """Add 1-second tick for micro-analysis"""
        self.tick_buffer.append(tick)
        if len(self.tick_buffer) > self.max_ticks:
            self.tick_buffer.pop(0)
    
    def add_candle(self, candle):
        """Add candle for macro-analysis"""
        self.candle_buffer.append(candle)
        if len(self.candle_buffer) > self.max_candles:
            self.candle_buffer.pop(0)
    
    def detect_spread_manipulation(self):
        """Detect artificial spread spikes (1HZ75V specialty)"""
        if len(self.tick_buffer) < 60:  # Need at least 1 minute of ticks
            return {"detected": False, "score": 0}
        
        recent_ticks = self.tick_buffer[-60:]  # Last 60 seconds
        spreads = []
        
        for tick in recent_ticks:
            if 'bid' in tick and 'ask' in tick:
                spread = tick['ask'] - tick['bid']
                spreads.append(spread)
        
        if not spreads:
            return {"detected": False, "score": 0}
        
        avg_spread = sum(spreads) / len(spreads)
        max_spread = max(spreads)
        
        # Detect spike (3x+ normal spread)
        if max_spread > avg_spread * 3:
            spike_count = sum(1 for s in spreads if s > avg_spread * 2)
            manipulation_score = min(1.0, spike_count / len(spreads) * 5)
            
            return {
                "detected": True,
                "score": manipulation_score,
                "avg_spread": avg_spread,
                "max_spread": max_spread,
                "spike_count": spike_count
            }
        
        return {"detected": False, "score": 0}
    
    def detect_price_manipulation(self):
        """Detect systematic price manipulation"""
        if len(self.candle_buffer) < 50:
            return {"detected": False, "score": 0}
        
        recent_candles = self.candle_buffer[-50:]
        manipulation_score = 0
        patterns = []
        
        # 1. Detect fake breakouts (price spikes then immediate reversals)
        fake_breakouts = 0
        for i in range(2, len(recent_candles) - 2):
            current = recent_candles[i]
            prev = recent_candles[i-1]
            next_candle = recent_candles[i+1]
            
            # High spike then immediate drop
            if (current['high'] > prev['high'] * 1.005 and 
                next_candle['close'] < current['open']):
                fake_breakouts += 1
            
            # Low spike then immediate rise  
            if (current['low'] < prev['low'] * 0.995 and
                next_candle['close'] > current['open']):
                fake_breakouts += 1
        
        if fake_breakouts > len(recent_candles) * 0.1:  # More than 10%
            manipulation_score += 0.4
            patterns.append("FAKE_BREAKOUTS")
        
        # 2. Detect round number clustering
        closes = [c['close'] for c in recent_candles]
        rounded = [round(c, -1) for c in closes]  # Round to nearest 10
        clustering = {}
        for price in rounded:
            clustering[price] = clustering.get(price, 0) + 1
        
        max_cluster = max(clustering.values()) if clustering else 0
        if max_cluster > len(recent_candles) * 0.15:
            manipulation_score += 0.3
            patterns.append("PRICE_CLUSTERING")
        
        return {
            "detected": manipulation_score > 0.5,
            "score": min(1.0, manipulation_score),
            "patterns": patterns,
            "fake_breakouts": fake_breakouts
        }
    
    def generate_diamond_signal(self):
        """Generate counter-manipulation signals"""
        spread_analysis = self.detect_spread_manipulation()
        price_analysis = self.detect_price_manipulation()
        
        if not self.candle_buffer:
            return None
        
        current_price = self.candle_buffer[-1]['close']
        
        # High manipulation detected
        total_manipulation = (spread_analysis["score"] + price_analysis["score"]) / 2
        
        if total_manipulation > 0.7:  # 70%+ manipulation confidence
            # Determine trend for counter-trade
            if len(self.candle_buffer) >= 10:
                recent_trend = self._calculate_trend()
                
                signal = {
                    "type": "DIAMOND_COUNTER_MANIPULATION",
                    "symbol": symbol,
                    "direction": "SELL" if recent_trend > 0 else "BUY", 
                    "strength": int(total_manipulation * 95),
                    "price": current_price,
                    "spread_manipulation": spread_analysis["score"],
                    "price_manipulation": price_analysis["score"],
                    "reason": f"High manipulation detected: {price_analysis.get('patterns', [])}",
                    "timestamp": datetime.utcnow().isoformat(),
                    "stop_loss": current_price * (1.015 if recent_trend > 0 else 0.985),
                    "take_profit": current_price * (0.975 if recent_trend > 0 else 1.025)
                }
                
                return signal
        
        return None
    
    def _calculate_trend(self):
        """Calculate recent price trend"""
        if len(self.candle_buffer) < 10:
            return 0
        
        closes = [c['close'] for c in self.candle_buffer[-10:]]
        return (closes[-1] - closes[0]) / closes[0]

# Initialize Diamond Detector
diamond = DiamondDetector()

# ===== TELEGRAM ALERT FUNCTION =====
async def send_telegram_message(message: str):
    if telegram_chat_id == "YOUR_ACTUAL_CHAT_ID":
        logger.warning("⚠️ Telegram not configured - message not sent")
        return
    
    try:
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        data = {
            "chat_id": telegram_chat_id, 
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                if response.status == 200:
                    logger.info("✅ Telegram message sent")
                else:
                    logger.error(f"❌ Telegram failed: {response.status}")
    except Exception as e:
        logger.error(f"Telegram error: {e}")

async def send_diamond_alert(signal):
    """Send Diamond signal alert"""
    direction_emoji = "🟢" if signal["direction"] == "BUY" else "🔴"
    
    message = f"""
💎 **DIAMOND 1HZ75V ALERT**

{direction_emoji} **{signal['type'].replace('_', ' ')}**
📊 **Symbol:** {signal['symbol']}
📈 **Direction:** {signal['direction']}
💪 **Strength:** {signal['strength']}%
💰 **Price:** {signal['price']}

🔍 **Manipulation Detected:**
• Spread Score: {signal['spread_manipulation']:.1%}
• Price Score: {signal['price_manipulation']:.1%}

🎯 **Trade Setup:**
🛑 Stop Loss: {signal['stop_loss']:.2f}
🎯 Take Profit: {signal['take_profit']:.2f}

💡 **Reason:** {signal['reason']}

⏰ **Time:** {datetime.utcnow().strftime('%H:%M:%S')} UTC

⚠️ *Educational signals - Not financial advice*
    """
    
    await send_telegram_message(message)

# ===== WHATSAPP PLACEHOLDER =====
async def send_whatsapp_message(message: str):
    logger.info(f"[WhatsApp] {message} -> {whatsapp_group_name}")

# ===== DATA STORAGE =====
def save_candle(candle: dict):
    with open(candle_log, "a") as f:
        f.write(json.dumps(candle) + "\n")

def save_tick(tick: dict):
    """Save individual tick data"""
    with open(tick_log, "a") as f:
        f.write(json.dumps(tick) + "\n")

def save_signal(signal: dict):
    """Save Diamond signals"""
    with open(signals_log, "a") as f:
        f.write(json.dumps(signal) + "\n")

# ======= HISTORICAL FETCHER =========
async def fetch_historical_candles():
    uri = f"wss://ws.binaryws.com/websockets/v3?app_id={app_id}"
    # Reduced to 90 days to avoid massive downloads
    start_time = int((datetime.utcnow() - timedelta(days=90)).timestamp())
    end_time = int(datetime.utcnow().timestamp())
    chunk_size = 1000  # Smaller chunks
    current = start_time
    total_candles = 0

    logger.info(f"📡 Downloading 90 days of {symbol} historical data...")

    try:
        async with websockets.connect(uri) as ws:
            while current < end_time:
                chunk_end = min(current + chunk_size * granularity, end_time)
                request = {
                    "ticks_history": symbol,
                    "style": "candles",
                    "granularity": granularity,
                    "start": current,
                    "end": chunk_end
                }
                await ws.send(json.dumps(request))
                response = await ws.recv()
                data = json.loads(response)

                if "error" in data:
                    logger.error(f"API Error: {data['error']}")
                    break

                if "candles" in data:
                    for candle in data["candles"]:
                        save_candle(candle)
                        diamond.add_candle(candle)
                        total_candles += 1
                    
                    logger.info(f"Downloaded {len(data['candles'])} candles, total: {total_candles}")

                current = chunk_end
                await asyncio.sleep(1)  # Rate limiting

        logger.info(f"✅ Historical download complete: {total_candles} candles")
    except Exception as e:
        logger.error(f"Historical fetch error: {e}")

# ======= LIVE TICK STREAM (1-SECOND) =========
async def fetch_live_ticks():
    """Stream live 1-second ticks from 1HZ75V"""
    uri = f"wss://ws.binaryws.com/websockets/v3?app_id={app_id}"

    logger.info(f"🔴 Starting live 1-second tick stream for {symbol}...")

    try:
        async with websockets.connect(uri) as ws:
            # Subscribe to live ticks (1-second)
            payload = {
                "ticks": symbol,
                "subscribe": 1
            }
            await ws.send(json.dumps(payload))

            async for message in ws:
                try:
                    data = json.loads(message)
                    
                    if "error" in data:
                        logger.error(f"WebSocket error: {data['error']}")
                        continue

                    if "tick" in data:
                        tick = data["tick"]
                        
                        # Save tick
                        save_tick(tick)
                        diamond.add_tick(tick)
                        
                        # Log tick
                        price = tick["quote"]
                        timestamp = datetime.utcfromtimestamp(tick["epoch"]).strftime('%H:%M:%S')
                        logger.info(f"[{symbol}] {timestamp} | Tick: {price}")
                        
                        # Check for Diamond signals every 60 ticks (1 minute)
                        if len(diamond.tick_buffer) % 60 == 0:
                            signal = diamond.generate_diamond_signal()
                            if signal:
                                save_signal(signal)
                                logger.warning(f"🔥 DIAMOND SIGNAL: {signal['type']} {signal['direction']} @ {signal['price']}")
                                await send_diamond_alert(signal)

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                except Exception as e:
                    logger.error(f"Tick processing error: {e}")

    except Exception as e:
        logger.error(f"Live tick stream error: {e}")
        await asyncio.sleep(5)
        logger.info("🔄 Retrying tick stream...")
        await fetch_live_ticks()

# ======= LIVE CANDLE UPDATER =========
async def fetch_live_candles():
    """Stream live candle updates"""
    uri = f"wss://ws.binaryws.com/websockets/v3?app_id={app_id}"

    logger.info(f"📊 Starting live candle stream for {symbol}...")

    try:
        async with websockets.connect(uri) as ws:
            payload = {
                "ticks_history": symbol,
                "style": "candles",
                "granularity": granularity,
                "end": "latest",
                "count": 1,
                "subscribe": 1
            }
            await ws.send(json.dumps(payload))

            async for message in ws:
                try:
                    data = json.loads(message)
                    
                    if "error" in data:
                        logger.error(f"Candle stream error: {data['error']}")
                        continue

                    if "candles" in data:
                        candle = data["candles"][0]
                        save_candle(candle)
                        diamond.add_candle(candle)
                        
                        timestamp = datetime.utcfromtimestamp(candle["epoch"]).strftime('%Y-%m-%d %H:%M:%S')
                        price = candle["close"]
                        
                        # Basic candle alert (less frequent than ticks)
                        msg = f"[{symbol}] Candle Close: {price} @ {timestamp}"
                        logger.info(msg)
                        
                        # Send to WhatsApp (less spam)
                        await send_whatsapp_message(msg)

                except Exception as e:
                    logger.error(f"Candle processing error: {e}")

    except Exception as e:
        logger.error(f"Live candle stream error: {e}")
        await asyncio.sleep(5)
        logger.info("🔄 Retrying candle stream...")
        await fetch_live_candles()

# ===== MAIN RUNNER =====
async def main():
    logger.info("🚀 Diamond 1HZ75V Analysis System Starting...")
    
    # Send startup alert
    if telegram_chat_id != "YOUR_ACTUAL_CHAT_ID":
        startup_msg = f"""
💎 **Diamond 1HZ75V System Online**

🎯 **Symbol:** {symbol} (1-second ticks)
⏰ **Analysis:** Real-time manipulation detection  
🔍 **Features:** Spread spikes, fake breakouts
📱 **Alerts:** Diamond counter-signals

🚀 **Status:** Active & Monitoring
        """
        await send_telegram_message(startup_msg)
    
    # Start all processes concurrently
    tasks = [
        fetch_historical_candles(),  # Download historical data first
        fetch_live_ticks(),         # 1-second tick stream  
        fetch_live_candles()        # 1-minute candle stream
    ]
    
    # Run historical first, then live streams
    await tasks[0]  # Historical data
    await asyncio.gather(*tasks[1:])  # Live streams

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 System shutdown by user")
    except Exception as e:
        logger.error(f"System error: {e}")
