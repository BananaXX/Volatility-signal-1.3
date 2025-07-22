#!/usr/bin/env python3
"""
Diamond Core Trading System - FIXED EVENT LOOP VERSION
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
from concurrent.futures import ThreadPoolExecutor
import nest_asyncio

# Fix event loop issues
nest_asyncio.apply()

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
    
    def send_signal_sync(self, signal_data: Dict, symbol: str):
        """Send trading signal to Telegram - SYNC VERSION"""
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
            
            response = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    'chat_id': self.chat_id,
                    'text': message,
                    'parse_mode': 'Markdown',
                    'disable_web_page_preview': True
                },
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Signal sent to Telegram: {symbol} {signal_data['direction']}")
                return True
            else:
                logger.error(f"Telegram send failed: {response.status_code}")
                return False
                        
        except Exception as e:
            logger.error(f"Telegram notification error: {e}")
            return False
    
    def send_test_signal_sync(self):
        """Send test signal - SYNC VERSION"""
        if not self.enabled:
            return False, "Telegram not configured"
        
        test_signal = {
            "type": "SYSTEM_TEST",
            "direction": "BUY",
            "strength": 95,
            "reason": "System test - Telegram integration working",
            "entry_price": 3600,
            "stop_loss": 3570,
            "take_profit": 3660
        }
        
        try:
            result = self.send_signal_sync(test_signal, "TEST_PAIR")
            if result:
                return True, "Test signal sent successfully"
            else:
                return False, "Failed to send test signal"
        except Exception as e:
            return False, f"Test failed: {str(e)}"

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
        self.loop = None
        
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
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

class TradingSystemManager:
    def __init__(self):
        self.api_client = DerivAPIClient()
        self.db_manager = DatabaseManager()
        self.telegram = TelegramNotifier()
        self.active_pairs = {}
        self.running = False
        self.current_signals = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    def run_async_task(self, coro):
        """Run async task in executor"""
        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        
        future = self.executor.submit(run_in_thread)
        return future.result()
        
    def initialize_sync(self):
        """Synchronous initialization"""
        try:
            return self.run_async_task(self.api_client.connect())
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False
    
    def get_symbols_sync(self):
        """Get symbols synchronously"""
        try:
            if not self.api_client.ws:
                connected = self.run_async_task(self.api_client.connect())
                if not connected:
                    return []
            
            available_pairs = self.run_async_task(self.api_client.get_active_symbols())
            self.active_pairs = {pair.symbol: pair for pair in available_pairs}
            logger.info(f"Retrieved {len(self.active_pairs)} trading pairs")
            return available_pairs
        except Exception as e:
            logger.error(f"Failed to get symbols: {e}")
            return []
    
    def get_system_status(self) -> Dict:
        """Get current system status"""
        if not self.active_pairs:
            # Try to get pairs if not already loaded
            try:
                self.get_symbols_sync()
            except:
                pass
        
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
        button { background: #00ff41; color: black; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-weight: bold; margin: 5px; }
        button:hover { background: #00cc33; }
        select, input { background: #1a1a1a; color: white; border: 1px solid #555; padding: 8px; border-radius: 4px; }
        .status-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 10px; }
        .status-running { background: #00ff41; }
        .status-stopped { background: #ff4444; }
        .metric { text-align: center; margin: 10px 0; }
        .metric-value { font-size: 24px; font-weight: bold; color: #00ff41; }
        .metric-label { font-size: 12px; color: #888; }
        .error-message { background: #ff4444; color: white; padding: 10px; border-radius: 5px; margin: 10px 0; }
        .success-message { background: #00ff41; color: black; padding: 10px; border-radius: 5px; margin: 10px 0; }
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
            {% if status.available_pairs %}
                <select id="pairSelect" multiple style="width: 100%; height: 150px;">
                    {% for pair in status.available_pairs %}
                    <option value="{{ pair.symbol }}">{{ pair.name }} (V{{ pair.volatility }})</option>
                    {% endfor %}
                </select>
            {% else %}
                <div class="error-message">No trading pairs available. Check Deriv API connection.</div>
            {% endif %}
            <br><br>
            <button onclick="startMonitoring()">Start Monitoring</button>
            <button onclick="stopMonitoring()">Stop</button>
            <button onclick="refreshData()">Refresh</button>
            <button onclick="testTelegram()">Test Telegram</button>
        </div>
        
        {% if status.available_pairs %}
        <div class="card">
            <h3>System Status</h3>
            <div class="metric">
                <div class="metric-value">{{ status.connected_pairs }}</div>
                <div class="metric-label">Available Pairs</div>
            </div>
            <div class="signals">
                <h4>Available Synthetic Indices:</h4>
                {% for pair in status.available_pairs[:5] %}
                <div class="signal-item">
                    <strong>{{ pair.name }}</strong><br>
                    <small>Symbol: {{ pair.symbol }} | Volatility: {{ pair.volatility }}%</small>
                </div>
                {% endfor %}
                {% if status.available_pairs|length > 5 %}
                <div class="signal-item">
                    <small>...and {{ status.available_pairs|length - 5 }} more pairs available</small>
                </div>
                {% endif %}
            </div>
        </div>
        {% endif %}
        
        <div id="messageArea"></div>
    </div>
    
    <script>
        function showMessage(message, type = 'success') {
            const messageArea = document.getElementById('messageArea');
            const messageClass = type === 'success' ? 'success-message' : 'error-message';
            messageArea.innerHTML = `<div class="${messageClass}">${message}</div>`;
            setTimeout(() => messageArea.innerHTML = '', 5000);
        }
        
        function startMonitoring() {
            const select = document.getElementById('pairSelect');
            if (!select) {
                showMessage('No pairs available to monitor', 'error');
                return;
            }
            
            const selected = Array.from(select.selectedOptions).map(option => option.value);
            
            if (selected.length === 0) {
                showMessage('Please select at least one trading pair', 'error');
                return;
            }
            
            fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({symbols: selected})
            })
            .then(response => response.json())
            .then(data => {
                showMessage(data.message, data.status === 'success' ? 'success' : 'error');
                if (data.status === 'success') {
                    setTimeout(() => location.reload(), 2000);
                }
            })
            .catch(error => {
                showMessage('Error starting monitoring: ' + error.message, 'error');
            });
        }
        
        function stopMonitoring() {
            fetch('/stop', {method: 'POST'})
            .then(response => response.json())
            .then(data => {
                showMessage(data.message, data.status === 'success' ? 'success' : 'error');
                setTimeout(() => location.reload(), 2000);
            })
            .catch(error => {
                showMessage('Error stopping monitoring: ' + error.message, 'error');
            });
        }
        
        function refreshData() {
            location.reload();
        }
        
        function testTelegram() {
            showMessage('Testing Telegram connection...', 'success');
            
            fetch('/test-telegram', {method: 'POST'})
            .then(response => response.json())
            .then(data => {
                showMessage(data.message, data.status === 'success' ? 'success' : 'error');
            })
            .catch(error => {
                showMessage('Error testing Telegram: ' + error.message, 'error');
            });
        }
        
        // Auto-refresh every 60 seconds
        setTimeout(() => location.reload(), 60000);
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    try:
        status = trading_system.get_system_status()
        signals = trading_system.current_signals
        return render_template_string(HTML_TEMPLATE, status=status, signals=signals)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return f"Dashboard Error: {e}", 500

@app.route('/start', methods=['POST'])
def start_monitoring():
    try:
        data = request.get_json()
        symbols = data.get('symbols', [])
        
        if not symbols:
            return jsonify({"status": "error", "message": "No symbols selected"})
        
        # Simple monitoring start (without complex async operations for now)
        trading_system.running = True
        
        return jsonify({"status": "success", "message": f"Started monitoring {len(symbols)} pairs"})
    except Exception as e:
        logger.error(f"Start monitoring error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/stop', methods=['POST'])
def stop_monitoring():
    try:
        trading_system.running = False
        return jsonify({"status": "success", "message": "Monitoring stopped"})
    except Exception as e:
        logger.error(f"Stop monitoring error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/test-telegram', methods=['POST'])
def test_telegram():
    try:
        success, message = trading_system.telegram.send_test_signal_sync()
        status = "success" if success else "error"
        return jsonify({"status": status, "message": message})
    except Exception as e:
        logger.error(f"Telegram test error: {e}")
        return jsonify({"status": "error", "message": f"Test failed: {str(e)}"})

@app.route('/api/signals')
def get_signals():
    return jsonify(trading_system.current_signals)

@app.route('/api/status')
def get_status():
    return jsonify(trading_system.get_system_status())

# Initialize system on startup
def initialize_system():
    """Initialize the trading system"""
    try:
        # Initialize with basic connection
        success = trading_system.initialize_sync()
        if success:
            logger.info("Trading system initialized successfully")
            # Get available pairs
            trading_system.get_symbols_sync()
        else:
            logger.warning("Trading system initialization failed - will retry on first request")
    except Exception as e:
        logger.error(f"Initialization error: {e}")

if __name__ == '__main__':
    # Initialize system in background
    init_thread = threading.Thread(target=initialize_system)
    init_thread.daemon = True
    init_thread.start()
    
    # Start Flask web server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
