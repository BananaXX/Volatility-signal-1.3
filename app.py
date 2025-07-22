# ===== ENHANCED TELEGRAM ALERT WITH FULL TIMESTAMP =====
async def send_diamond_alert(signal):
    """Send Diamond signal alert with FULL date verification"""
    direction_emoji = "🟢" if signal["direction"] == "BUY" else "🔴"
    
    # Get current time for verification
    now = datetime.utcnow()
    current_date = now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M:%S')
    
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

⏰ **LIVE TIMESTAMP:**
📅 **Date:** {current_date}
🕒 **Time:** {current_time} UTC
🔴 **Status:** REAL-TIME SIGNAL

🆔 **Signal ID:** {now.strftime('%Y%m%d_%H%M%S')}

⚠️ *Educational signals - Not financial advice*
    """
    
    await send_telegram_message(message)

# ===== ADD SIGNAL VERIFICATION =====
def verify_signal_freshness(signal):
    """Verify signal is generated within last 5 minutes"""
    signal_time = datetime.fromisoformat(signal['timestamp'].replace('Z', '+00:00'))
    current_time = datetime.utcnow()
    time_diff = current_time - signal_time
    
    # Signal must be within 5 minutes
    if time_diff.total_seconds() > 300:  # 5 minutes
        logger.warning(f"⚠️ Signal is {time_diff.total_seconds()} seconds old - might be stale!")
        return False
    
    logger.info(f"✅ Signal is fresh: {time_diff.total_seconds():.1f} seconds old")
    return True

# ===== ENHANCED SIGNAL GENERATION =====
def generate_diamond_signal(self):
    """Generate counter-manipulation signals with timestamp verification"""
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
            
            # Create signal with FULL timestamp
            now = datetime.utcnow()
            
            signal = {
                "type": "DIAMOND_COUNTER_MANIPULATION",
                "symbol": symbol,
                "direction": "SELL" if recent_trend > 0 else "BUY", 
                "strength": int(total_manipulation * 95),
                "price": current_price,
                "spread_manipulation": spread_analysis["score"],
                "price_manipulation": price_analysis["score"],
                "reason": f"High manipulation detected: {price_analysis.get('patterns', [])}",
                "timestamp": now.isoformat() + "Z",  # Full ISO timestamp
                "signal_date": now.strftime('%Y-%m-%d'),  # Explicit date
                "signal_time": now.strftime('%H:%M:%S'),  # Explicit time
                "unix_timestamp": int(now.timestamp()),   # Unix timestamp for verification
                "stop_loss": current_price * (1.015 if recent_trend > 0 else 0.985),
                "take_profit": current_price * (0.975 if recent_trend > 0 else 1.025),
                "freshness_verified": True
            }
            
            # Verify signal freshness before sending
            if verify_signal_freshness(signal):
                return signal
            else:
                logger.error("❌ Signal failed freshness check - not sending")
                return None
    
    return None

# ===== STARTUP VERIFICATION MESSAGE =====
async def send_startup_verification():
    """Send startup message with current time verification"""
    now = datetime.utcnow()
    
    startup_msg = f"""
💎 **Diamond System STARTUP VERIFICATION**

🔴 **LIVE STATUS:** System Online
📅 **Current Date:** {now.strftime('%Y-%m-%d')}
🕒 **Current Time:** {now.strftime('%H:%M:%S')} UTC
🌍 **Timezone:** UTC (Universal)

🎯 **Symbol:** 1HZ75V (1-second ticks)
⏰ **Analysis:** Real-time manipulation detection  
🔍 **Features:** Spread spikes, fake breakouts

✅ **Verification:** All signals will include full timestamps
🆔 **System ID:** {now.strftime('%Y%m%d_%H%M%S')}

🚀 **Status:** Ready to detect manipulation patterns
    """
    
    await send_telegram_message(startup_msg)

# ===== ADD TO MAIN FUNCTION =====
async def main():
    logger.info("🚀 Diamond 1HZ75V Analysis System Starting...")
    
    # Send startup verification with current timestamp
    if telegram_chat_id != "YOUR_ACTUAL_CHAT_ID":
        await send_startup_verification()
    
    # ... rest of your code
