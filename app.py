#!/usr/bin/env python3
"""
COMPLETE Diamond 1HZ75V System with Full Date/Time Verification
Prevents stale signals and includes full timestamps in Telegram
"""

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

# ===== ENHANCED DIAMOND DETECTOR WITH STALE DATA PROTECTION =====
class DiamondDetector:
    def __init__(self):
        self.tick_buffer = []
        self.candle_buffer = []
        self.max_ticks = 1000
        self.max_candles = 200
        self.last_signal_time = None
        self.system_start_time = datetime.utcnow()
        
    def add_tick(self, tick):
        """Add tick with freshness verification"""
        tick_time = datetime.utcfromtimestamp(tick["epoch"])
        current_time = datetime.utcnow()
        
        # REJECT ticks older than 10 seconds
        age = (current_time - tick_time).total_seconds()
        if age > 10:
            logger.warning(f"🚫 Rejecting stale tick: {age:.1f}s old")
            return False
        
        # REJECT ticks from before system start (historical data)
        if tick_time < self.system_start_time:
            logger.warning(f"🚫 Rejecting historical tick from {tick_time}")
            return False
        
        self.tick_buffer.append(tick)
        if len(self.tick_buffer) > self.max_ticks:
            self.tick_buffer.pop(0)
        return True
    
    def add_candle(self, candle):
        """Add candle with freshness verification"""
        candle_time = datetime.utcfromtimestamp(candle["epoch"])
        current_time = datetime.utcnow()
        
        # REJECT candles older than 5 minutes
        age = (current_time - candle_time).total_seconds()
        if age > 300:
            logger.warning(f"🚫 Rejecting stale candle: {age:.1f}s old")
            return False
        
        self.candle_buffer.append(candle)
        if len(self.candle_buffer) > self.max_candles:
            self.candle_buffer.pop(0)
        return True
    
    def detect_spread_manipulation(self):
        """Detect artificial spread spikes"""
        if len(self.tick_buffer) < 60:
            return {"detected": False, "score": 0}
        
        recent_ticks = self.tick_buffer[-60:]
        spreads = []
        
        for tick in recent_ticks:
            if 'bid' in tick and 'ask' in tick:
                spread = tick['ask'] - tick['bid']
                spreads.append(spread)
        
        if not spreads:
            return {"detected": False, "score": 0}
        
        avg_spread = sum(spreads) / len(spreads)
        max_spread = max(spreads)
        
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
        if len(self.candle_buffer) < 20:  # Reduced for faster response
            return {"detected": False, "score": 0}
        
        recent_candles = self.candle_buffer[-20:]  # Last 20 minutes only
        manipulation_score = 0
        patterns = []
        
        # Detect fake breakouts
        fake_breakouts = 0
        for i in range(2, len(recent_candles) - 2):
            current = recent_candles[i]
            prev = recent_candles[i-1]
            next_candle = recent_candles[i+1]
            
            if (current['high'] > prev['high'] * 1.005 and 
                next_candle['close'] < current['open']):
                fake_breakouts += 1
            
            if (current['low'] < prev['low'] * 0.995 and
                next_candle['close'] > current['open']):
                fake_breakouts += 1
        
        if fake_breakouts > len(recent_candles) * 0.1:
            manipulation_score += 0.4
            patterns.append("FAKE_BREAKOUTS")
        
        # Detect price clustering
        closes = [c['close'] for c in recent_candles]
        rounded = [round(c, -1) for c in closes]
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
            "patterns": patterns
        }
    
    def generate_diamond_signal(self):
        """Generate signals with strict freshness verification"""
        spread_analysis = self.detect_spread_manipulation()
        price_analysis = self.detect_price_manipulation()
        
        if not self.tick_buffer:
            return None
        
        # Get current price from most recent tick
        latest_tick = self.tick_buffer[-1]
        current_price = latest_tick["quote"]
        
        # Verify latest tick is fresh
        tick_time = datetime.utcfromtimestamp(latest_tick["epoch"])
        now = datetime.utcnow()
        tick_age = (now - tick_time).total_seconds()
        
        if tick_age > 30:  # Don't generate signals from stale data
            logger.warning(f"🚫 Signal generation blocked - latest tick is {tick_age:.1f}s old")
            return None
        
        # Calculate total manipulation
        total_manipulation = (spread_analysis["score"] + price_analysis["score"]) / 2
        
        if total_manipulation > 0.7:  # 70%+ manipulation confidence
            # Prevent duplicate signals
            if self.last_signal_time and (now - self.last_signal_time).total_seconds() < 120:
                return None
            
            # Determine trend
            recent_trend = self._calculate_trend()
            
            signal = {
                "type": "DIAMOND_COUNTER_MANIPULATION",
                "symbol": symbol,
                "direction": "SELL" if recent_trend > 0 else "BUY", 
                "strength": int(total_manipulation * 95),
                "price": current_price,
                "spread_manipulation": spread_analysis["score"],
                "price_manipulation": price_analysis["score"],
                "reason": f"Manipulation patterns: {price_analysis.get('patterns', [])}",
                "timestamp": now.isoformat() + "Z",
                "signal_date": now.strftime('%Y-%m-%d'),
                "signal_time": now.strftime('%H:%M:%S'),
                "unix_timestamp": int(now.timestamp()),
                "stop_loss": current_price * (1.015 if recent_trend > 0 else 0.985),
                "take_profit": current_price * (0.975 if recent_trend > 0 else 1.025),
                "freshness_verified": True,
                "latest_tick_age": tick_age
            }
            
            self.last_signal_time = now
            return signal
        
        return None
    
    def _calculate_trend(self):
        """Calculate recent price trend"""
        if len(self.tick_buffer) < 30:
            return 0
        
        recent_prices = [t["quote"] for t in self.tick_buffer[-30:]]
        return (recent_prices[-1] - recent_prices[0]) / recent_prices[0]

# Initialize Diamond Detector
diamond = DiamondDetector()

# ===== TELEGRAM WITH FULL DATE/TIME VERIFICATION =====
async def send_telegram_message(message: str):
    if telegram_chat_id == "YOUR_ACTUAL_CHAT_ID":
        logger.warning("⚠️ Telegram not configured")
        logger.info(f"Would send: {message[:100]}...")
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
                    logger.info("✅ Telegram sent")
                else:
                    logger.error(f"❌ Telegram failed: {response.status}")
    except Exception as e:
        logger.error(f"Telegram error: {e}")

async def send_diamond_alert(signal):
    """Send alert with FULL date/time verification"""
    direction_emoji = "🟢" if signal["direction"] == "BUY" else "🔴"
    
    # Get current time for verification
    right_now = datetime.utcnow()
    current_date = right_now.strftime('%Y-%m-%d')
    current_time = right_now.strftime('%H:%M:%S')
    
    # Calculate signal age
    signal_timestamp = datetime.fromisoformat(signal['timestamp'].replace('Z', '+00:00'))
    age_seconds = (right_now - signal_timestamp).total_seconds()
    
    # REJECT signals older than 60 seconds
    if age_seconds > 60:
        logger.error(f"🚫 SIGNAL REJECTED - TOO OLD: {age_seconds:.1f} seconds")
        return
    
    message = f"""
💎 **DIAMOND 1HZ75V ALERT**

{direction_emoji} **{signal['type'].replace('_', ' ')}**
📊 **Symbol:** {signal['symbol']}
📈 **Direction:** {signal['direction']}
💪 **Strength:** {signal['strength']}%
💰 **Price:** {signal['price']}

🔍 **Manipulation Detected:**
• Spread Score: {signal.get('spread_manipulation', 0):.1%}
• Price Score: {signal.get('price_manipulation', 0):.1%}

🎯 **Trade Setup:**
🛑 Stop Loss: {signal['stop_loss']:.2f}
🎯 Take Profit: {signal['take_profit']:.2f}

⏰ **FULL TIMESTAMP VERIFICATION:**
📅 **TODAY'S DATE:** {current_date}
📅 **SIGNAL DATE:** {signal['signal_date']}
🕒 **SIGNAL TIME:** {signal['signal_time']} UTC
🕒 **SENT TIME:** {current_time} UTC
⚡ **SIGNAL AGE:** {age_seconds:.1f} seconds old

🔴 **FRESHNESS:** {"✅ FRESH" if age_seconds < 30 else "⚠️ DELAYED"}

💡 **Reason:** {signal['reason']}

⚠️ *Educational signals - Trade responsibly*
    """
    
    await send_telegram_message(message)

async def send_health_check():
    """Send system health check"""
    now = datetime.utcnow()
    
    health_msg = f"""
🔴 **SYSTEM HEALTH CHECK**

📅 **Current Date:** {now.strftime('%Y-%m-%d')}
🕒 **Current Time:** {now.strftime('%H:%M:%S')} UTC
🌍 **Timezone:** UTC

✅ **System Status:** Online & Monitoring
🎯 **Target Symbol:** {symbol}
📡 **Data Source:** Live WebSocket Only
🔍 **Quality Control:** Fresh data (<10s old)

🚫 **Stale Data Protection:** Active
💎 **Diamond Detection:** Ready

🆔 **Check ID:** {now.strftime('%Y%m%d_%H%M%S')}
    """
    
    await send_telegram_message(health_msg)

# ===== DATA STORAGE WITH TIMESTAMPS =====
def save_tick(tick: dict):
    """Save tick with storage timestamp"""
    tick['storage_timestamp'] = datetime.utcnow().isoformat()
    with open(tick_log, "a") as f:
        f.write(json.dumps(tick) + "\n")

def save_signal(signal: dict):
    """Save signal with storage timestamp"""
    signal['storage_timestamp'] = datetime.utcnow().isoformat()
    with open(signals_log, "a") as f:
        f.write(json.dumps(signal) + "\n")

# ===== LIVE TICK STREAM WITH STRICT VERIFICATION =====
async def fetch_live_ticks():
    """Stream live 1-second ticks with STRICT timestamp verification"""
    uri = f"wss://ws.binaryws.com/websockets/v3?app_id={app_id}"

    logger.info(f"🔴 Starting VERIFIED live tick stream for {symbol}...")
    
    # Log system start time
    system_start = datetime.utcnow()
    logger.info(f"🕒 System started at: {system_start.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    diamond.system_start_time = system_start

    try:
        async with websockets.connect(uri) as ws:
            # Subscribe to live ticks
            payload = {
                "ticks": symbol,
                "subscribe": 1
            }
            await ws.send(json.dumps(payload))
            logger.info("📡 Live tick subscription sent...")

            tick_count = 0
            last_tick_time = None
            
            async for message in ws:
                try:
                    data = json.loads(message)
                    
                    if "error" in data:
                        logger.error(f"WebSocket error: {data['error']}")
                        continue

                    if "tick" in data:
                        tick = data["tick"]
                        
                        # CRITICAL: Verify tick freshness
                        tick_timestamp = datetime.utcfromtimestamp(tick["epoch"])
                        current_time = datetime.utcnow()
                        tick_age = (current_time - tick_timestamp).total_seconds()
                        
                        # REJECT ticks older than 5 seconds
                        if tick_age > 5:
                            logger.warning(f"🚫 TICK REJECTED - TOO OLD: {tick_age:.1f} seconds")
                            continue
                        
                        # REJECT ticks from before system started
                        if tick_timestamp < system_start:
                            logger.warning(f"🚫 TICK REJECTED - HISTORICAL: {tick_timestamp}")
                            continue
                        
                        # Verify tick progression
                        if last_tick_time and tick_timestamp <= last_tick_time:
                            logger.warning(f"🚫 TICK REJECTED - OUT OF ORDER")
                            continue
                        
                        last_tick_time = tick_timestamp
                        tick_count += 1
                        
                        # Save verified fresh tick
                        if diamond.add_tick(tick):
                            save_tick(tick)
                            
                            # Log with full verification
                            price = tick["quote"]
                            logger.info(f"✅ FRESH TICK #{tick_count} | {tick_timestamp.strftime('%Y-%m-%d %H:%M:%S')} | Price: {price} | Age: {tick_age:.1f}s")
                            
                            # Check for signals every 60 FRESH ticks
                            if tick_count % 60 == 0:
                                logger.info(f"🔍 Analyzing {tick_count} fresh ticks...")
                                signal = diamond.generate_diamond_signal()
                                if signal:
                                    save_signal(signal)
                                    logger.warning(f"🔥 FRESH SIGNAL: {signal['type']} @ {signal['price']}")
                                    await send_diamond_alert(signal)
                                else:
                                    logger.info("✅ Analysis complete - no patterns detected")

                except Exception as e:
                    logger.error(f"Tick processing error: {e}")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await asyncio.sleep(5)
        await fetch_live_ticks()

# ===== PERIODIC HEALTH CHECKS =====
async def periodic_health_checks():
    """Send health checks every 30 minutes"""
    while True:
        await asyncio.sleep(1800)  # 30 minutes
        try:
            await send_health_check()
        except Exception as e:
            logger.error(f"Health check error: {e}")

# ===== MAIN FUNCTION =====
async def main():
    logger.info("🚀 Diamond System Starting with FULL TIMESTAMP VERIFICATION...")
    current_time = datetime.utcnow()
    logger.info(f"🕒 System startup: {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    # Send immediate health check
    if telegram_chat_id != "YOUR_ACTUAL_CHAT_ID":
        await send_health_check()
    else:
        logger.warning("⚠️ Telegram not configured - get chat ID from @userinfobot")
    
    # Start all tasks
    tasks = [
        fetch_live_ticks(),
        periodic_health_checks()
    ]
    
    logger.info("📡 Starting LIVE-ONLY monitoring (no historical data)...")
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        logger.info("=" * 60)
        logger.info("💎 DIAMOND SYSTEM - LIVE VERIFICATION MODE")
        logger.info("=" * 60)
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 System shutdown")
    except Exception as e:
        logger.error(f"System error: {e}")
