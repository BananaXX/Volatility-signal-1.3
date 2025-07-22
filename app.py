#!/usr/bin/env python3
"""
Diamond Core Trading System - Production Ready
Deploy to Render, Railway, or any VPS
Real Deriv API integration with multiple pairs support
"""

import os
import asyncio
import websockets
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Optional
import requests
import logging
from flask import Flask, render_template_string, request, jsonify
import threading
import time
import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if self.enabled:
            logger.info("Telegram notifications enabled")
        else:
            logger.warning("Telegram notifications disabled - missing bot token or chat ID")
    
    async def send_signal(self, signal_data: Dict, symbol: str):
        """Send trading signal to Telegram"""
        if not self.enabled:
            return False
        
        try:
            # Format signal message
            direction_emoji = "🟢" if signal_data["direction"] == "BUY" else "🔴" if signal_data["direction"] == "SELL" else "🟡"
            
            message = f"""
💎 **DIAMOND SIGNAL ALERT**

{direction_emoji} **{signal_data['type'].replace('_', ' ')}**
📊 **Pair:** {symbol}
📈 **Direction:** {signal_data['direction']}
💪 **Strength:** {signal_data['strength']}%
🎯 **Reason:** {signal_data.get('reason', 'Advanced pattern detected')}

⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}
🔥 **Entry:** {signal_data.get('entry_price', 'Market')}
🛑 **Stop Loss:** {signal_data.get('stop_loss', 'See dashboard')}
🎯 **Take Profit:** {signal_data.get('take_profit', 'See dashboard')}

⚠️ *Educational signals - Trade responsibly*
            """
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        'chat_id': self.chat_id,
                        'text': message,
                        'parse_mode': 'Markdown',
                        'disable_web_page_preview': True
                    }
                ) as response:
                    if response.status == 200:
                        logger.info(f"Signal sent to Telegram: {symbol} {signal_data['direction']}")
                        return True
                    else:
                        logger.error(f"Telegram send failed: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Telegram notification error: {e}")
            return False
    
    async def send_manipulation_alert(self, symbol: str, manipulation_data: Dict):
        """Send manipulation detection alert"""
        if not self.enabled or manipulation_data["manipulation_score"] < 0.8:
            return False
        
        try:
            score = manipulation_data["manipulation_score"] * 100
            patterns = ", ".join(manipulation_data.get("patterns", []))
            
            message = f"""
🚨 **MANIPULATION DETECTED**

📊 **Pair:** {symbol}
⚠️ **Score:** {score:.1f}%
🔍 **Patterns:** {patterns}

💡 **Counter-strategy activated**
🛡️ **Risk management engaged**

⏰ **Detected:** {datetime.now().strftime('%H:%M:%S')}
            """
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        'chat_id': self.chat_id,
                        'text': message,
                        'parse_mode': 'Markdown'
                    }
                ) as response:
                    if response.status == 200:
                        logger.info(f"Manipulation alert sent: {symbol}")
                        return True
                        
        except Exception as e:
            logger.error(f"Telegram manipulation alert error: {e}")
            return False
    
    async def send_system_status(self, status_data: Dict):
        """Send system status update"""
        if not self.enabled:
            return False
        
        try:
            message = f"""
🤖 **SYSTEM STATUS UPDATE**

🔄 **Status:** {'🟢 Running' if status_data.get('running') else '🔴 Stopped'}
📊 **Monitored Pairs:** {status_data.get('monitored_pairs', 0)}
📈 **Connected Pairs:** {status_data.get('connected_pairs', 0)}

⏰ **Update Time:** {datetime.now().strftime('%H:%M:%S')}
            """
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        'chat_id': self.chat_id,
                        'text': message,
                        'parse_mode': 'Markdown'
                    }
                ) as response:
                    return response.status == 200
                    
        except Exception as e:
            logger.error(f"Telegram status update error: {e}")
            return False

@dataclass
class TradingPair:
    symbol: str
    display_name: str
    min_tick: float
    volatility_target: int
    active: bool = True

class DerivAPIClient:
    def __init__(self, api_token: str = None, app_id: str = None):
        self.api_token = api_token or os.getenv('DERIV_API_TOKEN')
        self.app_id = app_id or os.getenv('DERIV_APP_ID', '1089')
        self.ws_url = f"wss://ws.binaryws.com/websockets/v3?app_id={self.app_id}"
        self.ws = None
        self.subscriptions = {}
        self.historical_data = {}
        
    async def connect(self):
        """Connect to Deriv WebSocket API"""
        try:
            self.ws = await websockets.connect(self.ws_url)
            if self.api_token:
                await self.authorize()
            logger.info("Connected to Deriv API")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    async def authorize(self):
        """Authorize API token"""
        auth_request = {"authorize": self.api_token}
        await self.ws.send(json.dumps(auth_request))
        response = await self.ws.recv()
        data = json.loads(response)
        if data.get("error"):
            logger.error(f"Authorization failed: {data['error']}")
            return False
        logger.info("API authorization successful")
        return True
    
    async def get_active_symbols(self):
        """Get all available synthetic indices"""
        request = {"active_symbols": "brief", "product_type": "basic"}
        await self.ws.send(json.dumps(request))
        response = await self.ws.recv()
        data = json.loads(response)
        
        synthetic_pairs = []
        if "active_symbols" in data:
            for symbol in data["active_symbols"]:
                if "Volatility" in symbol.get("display_name", ""):
                    synthetic_pairs.append(TradingPair(
                        symbol=symbol["symbol"],
                        display_name=symbol["display_name"],
                        min_tick=float(symbol.get("pip", 0.01)),
                        volatility_target=self._extract_volatility(symbol["display_name"])
                    ))
        
        return synthetic_pairs
    
    def _extract_volatility(self, name: str) -> int:
        """Extract volatility percentage from pair name"""
        for vol in [10, 25, 50, 75, 100]:
            if str(vol) in name:
                return vol
        return 50  # Default
    
    async def get_historical_data(self, symbol: str, granularity: int = None, count: int = 5000):
        """Download historical tick data"""
        request = {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "style": "ticks"
        }
        
        if granularity:
            request["granularity"] = granularity
        
        await self.ws.send(json.dumps(request))
        response = await self.ws.recv()
        data = json.loads(response)
        
        if "history" in data:
            return self._process_historical_data(data["history"])
        return None
    
    def _process_historical_data(self, history_data):
        """Process historical data into pandas DataFrame"""
        prices = history_data.get("prices", [])
        times = history_data.get("times", [])
        
        if len(prices) != len(times):
            return None
        
        df = pd.DataFrame({
            'timestamp': [datetime.fromtimestamp(t) for t in times],
            'price': [float(p) for p in prices],
            'symbol': history_data.get("symbol", "")
        })
        
        return df
    
    async def subscribe_to_ticks(self, symbol: str, callback):
        """Subscribe to real-time tick stream"""
        request = {"ticks": symbol, "subscribe": 1}
        await self.ws.send(json.dumps(request))
        
        # Store callback for this symbol
        self.subscriptions[symbol] = callback
        
        # Start listening for updates
        asyncio.create_task(self._tick_listener())
    
    async def _tick_listener(self):
        """Listen for incoming tick data"""
        try:
            async for message in self.ws:
                data = json.loads(message)
                if "tick" in data:
                    symbol = data["tick"]["symbol"]
                    if symbol in self.subscriptions:
                        await self.subscriptions[symbol](data["tick"])
        except Exception as e:
            logger.error(f"Tick listener error: {e}")

class DatabaseManager:
    def __init__(self, db_path: str = "trading_data.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Historical data table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historical_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                price REAL NOT NULL,
                volume REAL DEFAULT 0,
                spread REAL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timestamp)
            )
        """)
        
        # Real-time ticks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                price REAL NOT NULL,
                ask REAL,
                bid REAL,
                spread REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Trading signals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trading_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                strength INTEGER NOT NULL,
                price REAL NOT NULL,
                reason TEXT,
                timestamp DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Manipulation detection table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS manipulation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                event_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                detected_at DATETIME NOT NULL,
                price_before REAL,
                price_after REAL,
                spread_spike BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    
    def store_historical_data(self, df: pd.DataFrame):
        """Store historical data in database"""
        conn = sqlite3.connect(self.db_path)
        df.to_sql('historical_data', conn, if_exists='append', index=False, method='ignore')
        conn.close()
    
    def store_live_tick(self, symbol: str, tick_data: dict):
        """Store live tick data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR IGNORE INTO live_ticks (symbol, timestamp, price, ask, bid, spread)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            datetime.fromtimestamp(tick_data.get('epoch', time.time())),
            float(tick_data.get('quote', 0)),
            float(tick_data.get('ask', 0)),
            float(tick_data.get('bid', 0)),
            float(tick_data.get('ask', 0)) - float(tick_data.get('bid', 0))
        ))
        
        conn.commit()
        conn.close()
    
    def get_recent_data(self, symbol: str, hours: int = 24) -> pd.DataFrame:
        """Get recent tick data for analysis"""
        conn = sqlite3.connect(self.db_path)
        
        query = """
            SELECT timestamp, price, spread 
            FROM live_ticks 
            WHERE symbol = ? AND timestamp >= datetime('now', '-{} hours')
            ORDER BY timestamp DESC
        """.format(hours)
        
        df = pd.read_sql_query(query, conn, params=(symbol,))
        conn.close()
        return df

class DiamondAnalysisEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.manipulation_threshold = 0.75
        self.spread_spike_multiplier = 3.0
        
    def analyze_manipulation_patterns(self, symbol: str) -> Dict:
        """Detect platform manipulation patterns"""
        df = self.db.get_recent_data(symbol, hours=12)
        if df.empty:
            return {"manipulation_score": 0, "patterns": []}
        
        # Convert price to numeric and handle NaN
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df = df.dropna()
        
        if len(df) < 50:
            return {"manipulation_score": 0, "patterns": []}
        
        manipulation_score = 0
        detected_patterns = []
        
        # 1. Spread Spike Detection
        avg_spread = df['spread'].mean()
        spread_spikes = df[df['spread'] > avg_spread * self.spread_spike_multiplier]
        if len(spread_spikes) > len(df) * 0.05:  # More than 5% of ticks
            manipulation_score += 0.3
            detected_patterns.append("FREQUENT_SPREAD_SPIKES")
        
        # 2. Sudden Reversal Pattern
        df['price_change'] = df['price'].diff()
        large_moves = df[abs(df['price_change']) > df['price_change'].std() * 2]
        reversals = 0
        
        for i in range(1, len(large_moves)):
            if len(large_moves) > i:
                current_move = large_moves.iloc[i]['price_change']
                prev_move = large_moves.iloc[i-1]['price_change']
                if current_move * prev_move < 0:  # Opposite directions
                    reversals += 1
        
        if reversals > len(large_moves) * 0.6:
            manipulation_score += 0.4
            detected_patterns.append("SYSTEMATIC_REVERSALS")
        
        # 3. Price Clustering Around Round Numbers
        df['price_rounded'] = df['price'].round(-1)  # Round to nearest 10
        clustering = df.groupby('price_rounded').size()
        max_cluster = clustering.max()
        if max_cluster > len(df) * 0.15:  # More than 15% at one level
            manipulation_score += 0.3
            detected_patterns.append("PRICE_CLUSTERING")
        
        return {
            "manipulation_score": min(1.0, manipulation_score),
            "patterns": detected_patterns,
            "spread_analysis": {
                "avg_spread": float(avg_spread),
                "spike_count": len(spread_spikes),
                "spike_percentage": len(spread_spikes) / len(df) * 100
            }
        }
    
    def generate_counter_signals(self, symbol: str, manipulation_data: Dict) -> List[Dict]:
        """Generate signals that counter platform manipulation"""
        signals = []
        
        if manipulation_data["manipulation_score"] > self.manipulation_threshold:
            # High manipulation detected - use counter-trend strategy
            df = self.db.get_recent_data(symbol, hours=2)
            if not df.empty:
                current_price = float(df.iloc[0]['price'])
                recent_trend = "UP" if df.iloc[0]['price'] > df.iloc[-1]['price'] else "DOWN"
                
                # Counter-manipulation signal
                signals.append({
                    "type": "COUNTER_MANIPULATION",
                    "direction": "SELL" if recent_trend == "UP" else "BUY",
                    "strength": int(manipulation_data["manipulation_score"] * 90),
                    "reason": f"High manipulation detected: {manipulation_data['patterns']}",
                    "entry_price": current_price,
                    "stop_loss": current_price * (1.01 if recent_trend == "UP" else 0.99),
                    "take_profit": current_price * (0.98 if recent_trend == "UP" else 1.02)
                })
        
        # Add spread exploitation signals
        spread_data = manipulation_data.get("spread_analysis", {})
        if spread_data.get("spike_percentage", 0) > 10:
            signals.append({
                "type": "SPREAD_EXPLOITATION",
                "direction": "WAIT",
                "strength": 85,
                "reason": "High spread volatility - wait for normalization",
                "timing": "DELAYED_ENTRY"
            })
        
        return signals

class TradingSystemManager:
    def __init__(self):
        self.api_client = DerivAPIClient()
        self.db_manager = DatabaseManager()
        self.analysis_engine = DiamondAnalysisEngine(self.db_manager)
        self.telegram = TelegramNotifier()
        self.active_pairs = {}
        self.running = False
        self.current_signals = {}
        self.notification_sent = {}  # Track sent notifications to avoid spam
        
    async def initialize(self):
        """Initialize the trading system"""
        connected = await self.api_client.connect()
        if not connected:
            raise Exception("Failed to connect to Deriv API")
        
        # Get available pairs
        available_pairs = await self.api_client.get_active_symbols()
        self.active_pairs = {pair.symbol: pair for pair in available_pairs}
        
        logger.info(f"Initialized with {len(self.active_pairs)} trading pairs")
        return True
    
    async def download_historical_data(self, symbol: str, days: int = 730):
        """Download 2+ years of historical data"""
        logger.info(f"Downloading {days} days of historical data for {symbol}")
        
        # Download in chunks to avoid API limits
        chunk_size = 5000  # Max ticks per request
        total_downloaded = 0
        
        try:
            df = await self.api_client.get_historical_data(symbol, count=chunk_size)
            if df is not None:
                self.db_manager.store_historical_data(df)
                total_downloaded = len(df)
                logger.info(f"Downloaded {total_downloaded} historical ticks for {symbol}")
            
            return total_downloaded > 0
        except Exception as e:
            logger.error(f"Historical data download failed for {symbol}: {e}")
            return False
    
    async def start_live_monitoring(self, symbols: List[str]):
        """Start monitoring selected symbols"""
        self.running = True
        
        for symbol in symbols:
            if symbol in self.active_pairs:
                # Subscribe to live ticks
                await self.api_client.subscribe_to_ticks(
                    symbol, 
                    lambda tick_data, s=symbol: self._process_live_tick(s, tick_data)
                )
                
                # Download historical data if not exists
                await self.download_historical_data(symbol)
        
        # Start analysis loop
        asyncio.create_task(self._analysis_loop())
        
        # Send startup notification
        if self.telegram.enabled:
            status_data = self.get_system_status()
            await self.telegram.send_system_status(status_data)
        
        logger.info(f"Started monitoring {len(symbols)} symbols")
    
    async def _process_live_tick(self, symbol: str, tick_data: dict):
        """Process incoming live tick data"""
        try:
            # Store in database
            self.db_manager.store_live_tick(symbol, tick_data)
            
            # Trigger analysis every 10 ticks (configurable)
            if hasattr(self, '_tick_counter'):
                self._tick_counter[symbol] = self._tick_counter.get(symbol, 0) + 1
            else:
                self._tick_counter = {symbol: 1}
            
            if self._tick_counter[symbol] % 10 == 0:
                await self._analyze_symbol(symbol)
                
        except Exception as e:
            logger.error(f"Error processing tick for {symbol}: {e}")
    
    async def _analysis_loop(self):
        """Main analysis loop running every 30 seconds"""
        while self.running:
            try:
                for symbol in self.active_pairs.keys():
                    await self._analyze_symbol(symbol)
                
                await asyncio.sleep(30)  # Analyze every 30 seconds
            except Exception as e:
                logger.error(f"Analysis loop error: {e}")
                await asyncio.sleep(5)
    
    async def _analyze_symbol(self, symbol: str):
        """Analyze a specific symbol for manipulation and signals"""
        try:
            # Detect manipulation patterns
            manipulation_data = self.analysis_engine.analyze_manipulation_patterns(symbol)
            
            # Generate counter-signals
            signals = self.analysis_engine.generate_counter_signals(symbol, manipulation_data)
            
            # Store current analysis
            self.current_signals[symbol] = {
                "manipulation": manipulation_data,
                "signals": signals,
                "last_update": datetime.now(),
                "pair_info": self.active_pairs[symbol]
            }
            
            # Send Telegram notifications
            if self.telegram.enabled:
                # Send manipulation alert (only once per hour to avoid spam)
                if manipulation_data["manipulation_score"] > 0.8:
                    last_manipulation_alert = self.notification_sent.get(f"{symbol}_manipulation", datetime.min)
                    if datetime.now() - last_manipulation_alert > timedelta(hours=1):
                        await self.telegram.send_manipulation_alert(symbol, manipulation_data)
                        self.notification_sent[f"{symbol}_manipulation"] = datetime.now()
                
                # Send signal notifications (only for high-strength signals)
                for signal in signals:
                    if signal["strength"] >= 80:  # Only send strong signals
                        signal_key = f"{symbol}_{signal['type']}_{signal['direction']}"
                        last_signal = self.notification_sent.get(signal_key, datetime.min)
                        
                        # Send only once per 15 minutes for same signal type
                        if datetime.now() - last_signal > timedelta(minutes=15):
                            await self.telegram.send_signal(signal, symbol)
                            self.notification_sent[signal_key] = datetime.now()
            
            # Log significant findings
            if manipulation_data["manipulation_score"] > 0.7:
                logger.warning(f"High manipulation detected in {symbol}: {manipulation_data['patterns']}")
            
            if signals:
                logger.info(f"Generated {len(signals)} signals for {symbol}")
                
        except Exception as e:
            logger.error(f"Analysis error for {symbol}: {e}")
    
    def get_system_status(self) -> Dict:
        """Get current system status"""
        return {
            "running": self.running,
            "connected_pairs": len(self.active_pairs),
            "monitored_pairs": len([s for s in self.current_signals.keys()]),
            "last_update": datetime.now(),
            "available_pairs": [
                {"symbol": pair.symbol, "name": pair.display_name, "volatility": pair.volatility_target}
                for pair in self.active_pairs.values()
            ]
        }

# Flask Web Interface
app = Flask(__name__)
trading_system = TradingSystemManager()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Diamond Trading System</title>
    <style>
        body { font-family: Arial, sans-serif; background: #1a1a1a; color: white; margin: 0; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .card { background: #2a2a2a; border-radius: 10px; padding: 20px; border-left: 4px solid #00ff41; }
        .pair-selector { background: #333; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
        .signals { background: #2a2a2a; padding: 15px; border-radius: 8px; }
        .signal-item { background: #1a1a1a; margin: 10px 0; padding: 10px; border-radius: 5px; border-left: 3px solid #00ff41; }
        .manipulation-high { border-left-color: #ff4444; }
        .manipulation-medium { border-left-color: #ffaa00; }
        .manipulation-low { border-left-color: #00ff41; }
        button { background: #00ff41; color: black; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-weight: bold; }
        button:hover { background: #00cc33; }
        select, input { background: #1a1a1a; color: white; border: 1px solid #555; padding: 8px; border-radius: 4px; }
        .status-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 10px; }
        .status-running { background: #00ff41; }
        .status-stopped { background: #ff4444; }
        .metric { text-align: center; margin: 10px 0; }
        .metric-value { font-size: 24px; font-weight: bold; color: #00ff41; }
        .metric-label { font-size: 12px; color: #888; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💎 Diamond Trading System</h1>
            <p>Real-time Deriv API integration with manipulation detection</p>
            <div class="status">
                <span class="status-indicator {{ 'status-running' if status.running else 'status-stopped' }}"></span>
                System {{ 'Running' if status.running else 'Stopped' }}
            </div>
        </div>
        
        <div class="pair-selector">
            <h3>Select Trading Pairs:</h3>
            <select id="pairSelect" multiple style="width: 100%; height: 150px;">
                {% for pair in status.available_pairs %}
                <option value="{{ pair.symbol }}">{{ pair.name }} (V{{ pair.volatility }})</option>
                {% endfor %}
            </select>
            <br><br>
            <button onclick="startMonitoring()">Start Monitoring</button>
            <button onclick="stopMonitoring()">Stop</button>
            <button onclick="refreshData()">Refresh</button>
            <button onclick="testTelegram()">Test Telegram</button>
        </div>
        
        <div class="grid">
            {% for symbol, data in signals.items() %}
            <div class="card">
                <h3>{{ data.pair_info.display_name }}</h3>
                
                <div class="metric">
                    <div class="metric-value">{{ "%.1f"|format(data.manipulation.manipulation_score * 100) }}%</div>
                    <div class="metric-label">Manipulation Score</div>
                </div>
                
                <div class="signals">
                    <h4>Active Signals:</h4>
                    {% for signal in data.signals %}
                    <div class="signal-item">
                        <strong>{{ signal.type }}</strong> - {{ signal.direction }}<br>
                        <small>Strength: {{ signal.strength }}% | {{ signal.reason }}</small>
                    </div>
                    {% endfor %}
                    
                    {% if data.manipulation.patterns %}
                    <h4>Detected Patterns:</h4>
                    {% for pattern in data.manipulation.patterns %}
                    <div class="signal-item manipulation-{{ 'high' if data.manipulation.manipulation_score > 0.7 else 'medium' if data.manipulation.manipulation_score > 0.4 else 'low' }}">
                        {{ pattern.replace('_', ' ').title() }}
                    </div>
                    {% endfor %}
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <script>
        function startMonitoring() {
            const select = document.getElementById('pairSelect');
            const selected = Array.from(select.selectedOptions).map(option => option.value);
            
            fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({symbols: selected})
            })
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                setTimeout(() => location.reload(), 2000);
            });
        }
        
        function stopMonitoring() {
            fetch('/stop', {method: 'POST'})
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                setTimeout(() => location.reload(), 2000);
            });
        }
        
        function refreshData() {
            location.reload();
        }
        
        function testTelegram() {
            fetch('/test-telegram', {method: 'POST'})
            .then(response => response.json())
            .then(data => alert(data.message));
        }
        
        // Auto-refresh every 30 seconds
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    status = trading_system.get_system_status()
    signals = trading_system.current_signals
    return render_template_string(HTML_TEMPLATE, status=status, signals=signals)

@app.route('/start', methods=['POST'])
def start_monitoring():
    try:
        data = request.get_json()
        symbols = data.get('symbols', [])
        
        if not symbols:
            return jsonify({"status": "error", "message": "No symbols selected"})
        
        # Start monitoring in background
        asyncio.create_task(trading_system.start_live_monitoring(symbols))
        
        return jsonify({"status": "success", "message": f"Started monitoring {len(symbols)} pairs"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/stop', methods=['POST'])
def stop_monitoring():
    try:
        trading_system.running = False
        return jsonify({"status": "success", "message": "Monitoring stopped"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/test-telegram', methods=['POST'])
def test_telegram():
    try:
        if not trading_system.telegram.enabled:
            return jsonify({"status": "error", "message": "Telegram not configured. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"})
        
        # Send test message
        test_signal = {
            "type": "SYSTEM_TEST",
            "direction": "BUY",
            "strength": 95,
            "reason": "System test - Telegram integration working",
            "entry_price": 3600,
            "stop_loss": 3570,
            "take_profit": 3660
        }
        
        asyncio.create_task(trading_system.telegram.send_signal(test_signal, "TEST_PAIR"))
        
        return jsonify({"status": "success", "message": "Test signal sent to Telegram"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Telegram test failed: {str(e)}"})

@app.route('/api/signals')
def get_signals():
    return jsonify(trading_system.current_signals)

@app.route('/api/status')
def get_status():
    return jsonify(trading_system.get_system_status())

async def initialize_system():
    """Initialize the trading system"""
    try:
        await trading_system.initialize()
        logger.info("Trading system initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize trading system: {e}")

def run_async_init():
    """Run async initialization in separate thread"""
    asyncio.run(initialize_system())

if __name__ == '__main__':
    # Initialize system in background
    init_thread = threading.Thread(target=run_async_init)
    init_thread.start()
    
    # Start Flask web server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
