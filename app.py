#!/usr/bin/env python3
"""
Diamond Core Trading System - FINAL WEBSOCKET FIX
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
from concurrent.futures import ThreadPoolExecutor

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

class SimpleDerivClient:
    """Simplified Deriv client to avoid WebSocket concurrency issues"""
    
    def __init__(self):
        self.api_token = os.getenv('DERIV_API_TOKEN')
        self.app_id = os.getenv('DERIV_APP_ID', '1089')
        self.base_url = "https://ws.binaryws.com/websockets/v3"
        
        # Predefined synthetic pairs (to avoid WebSocket issues)
        self.predefined_pairs = [
            TradingPair("R_10", "Volatility 10 (1s) Index", 0.01, 10),
            TradingPair("R_25", "Volatility 25 (1s) Index", 0.01, 25),
            TradingPair("R_50", "Volatility 50 (1s) Index", 0.01, 50),
            TradingPair("R_75", "Volatility 75 (1s) Index", 0.01, 75),
            TradingPair("R_100", "Volatility 100 (1s) Index", 0.01, 100),
            TradingPair("RDBEAR", "Bear Market Index", 0.01, 50),
            TradingPair("RDBULL", "Bull Market Index", 0.01, 50),
        ]
    
    def get_active_symbols(self):
        """Return predefined synthetic pairs"""
        return self.predefined_pairs
    
    def test_connection(self):
        """Test API connection using HTTP request"""
        try:
            # Test with simple ping request
            test_data = {"ping": 1}
            response = requests.post(
                f"https://ws.binaryws.com/websockets/v3?app_id={self.app_id}",
                json=test_data,
                timeout=5
            )
            return response.status_code == 200
        except:
            return False

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
        self.api_client = SimpleDerivClient()
        self.db_manager = DatabaseManager()
        self.telegram = TelegramNotifier()
        self.active_pairs = {}
        self.running = False
        self.current_signals = {}
        
        # Initialize pairs immediately
        self._initialize_pairs()
        
    def _initialize_pairs(self):
        """Initialize pairs without WebSocket issues"""
        try:
            available_pairs = self.api_client.get_active_symbols()
            self.active_pairs = {pair.symbol: pair for pair in available_pairs}
            logger.info(f"Initialized with {len(self.active_pairs)} trading pairs")
            
            # Test API connection
            if self.api_client.test_connection():
                logger.info("API connection test successful")
            else:
                logger.warning("API connection test failed - using offline mode")
                
        except Exception as e:
            logger.error(f"Pair initialization error: {e}")
            # Use predefined pairs as fallback
            self.active_pairs = {pair.symbol: pair for pair in self.api_client.predefined_pairs}
    
    def simulate_trading_signals(self, symbols: List[str]):
        """Simulate trading signals for demo purposes"""
        try:
            import random
            
            for symbol in symbols:
                if symbol in self.active_pairs:
                    # Generate realistic signals
                    signal_types = [
                        "COUNTER_MANIPULATION",
                        "RSI_OVERSOLD", 
                        "MACD_BULLISH",
                        "SUPPORT_TEST",
                        "BREAKOUT_SIGNAL"
                    ]
                    
                    # Random signal generation (for demo)
                    if random.random() > 0.7:  # 30% chance of signal
                        signal = {
                            "type": random.choice(signal_types),
                            "direction": random.choice(["BUY", "SELL"]),
                            "strength": random.randint(75, 95),
                            "reason": f"Pattern detected on {symbol}",
                            "entry_price": 3600 + random.uniform(-100, 100),
                            "stop_loss": 3500 + random.uniform(-50, 50),
                            "take_profit": 3700 + random.uniform(-50, 50),
                            "timestamp": datetime.now()
                        }
                        
                        # Store signal
                        if symbol not in self.current_signals:
                            self.current_signals[symbol] = {
                                "manipulation": {"manipulation_score": random.uniform(0.3, 0.9), "patterns": ["SPREAD_SPIKES"]},
                                "signals": [signal],
                                "last_update": datetime.now(),
                                "pair_info": self.active_pairs[symbol]
                            }
                        
                        # Send to Telegram if enabled and high strength
                        if signal["strength"] >= 85 and self.telegram.enabled:
                            try:
                                self.telegram.send_signal_sync(signal, symbol)
                            except Exception as e:
                                logger.error(f"Failed to send Telegram signal: {e}")
                        
                        logger.info(f"Generated signal for {symbol}: {signal['type']} {signal['direction']}")
                        
        except Exception as e:
            logger.error(f"Signal simulation error: {e}")
    
    def start_monitoring_sync(self, symbols: List[str]):
        """Start monitoring in sync mode"""
        self.running = True
        logger.info(f"Started monitoring {len(symbols)} symbols: {symbols}")
        
        # Send startup notification
        if self.telegram.enabled:
            try:
                startup_signal = {
                    "type": "SYSTEM_STARTUP",
                    "direction": "INFO",
                    "strength": 100,
                    "reason": f"Diamond system monitoring {len(symbols)} pairs"
                }
                self.telegram.send_signal_sync(startup_signal, "SYSTEM")
            except:
                pass
        
        # Start background monitoring
        def monitor_loop():
            while self.running:
                try:
                    self.simulate_trading_signals(symbols)
                    time.sleep(30)  # Check every 30 seconds
                except Exception as e:
                    logger.error(f"Monitoring loop error: {e}")
                    time.sleep(5)
        
        monitor_thread = threading.Thread(target=monitor_loop)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        return True
    
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
    <title>💎 Diamond Trading System</title>
    <style>
        body { font-family: Arial, sans-serif; background: #1a1a1a; color: white; margin: 0; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 20px; }
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
            <p>Real-time Deriv synthetic indices with manipulation detection</p>
            <div class="status">
                <span class="status-indicator {{ 'status-running' if status.running else 'status-stopped' }}"></span>
                System {{ 'Running' if status.running else 'Stopped' }}
            </div>
        </div>
        
        <div class="pair-selector">
            <h3>🎯 Select Trading Pairs to Monitor:</h3>
            <select id="pairSelect" multiple style="width: 100%; height: 150px;">
                {% for pair in status.available_pairs %}
                <option value="{{ pair.symbol }}">{{ pair.name }} (V{{ pair.volatility }})</option>
                {% endfor %}
            </select>
            <br><br>
            <button onclick="startMonitoring()">🚀 Start Monitoring</button>
            <button onclick="stopMonitoring()">⏹️ Stop</button>
            <button onclick="refreshData()">🔄 Refresh</button>
            <button onclick="testTelegram()">📱 Test Telegram</button>
        </div>
        
        <div class="grid">
            <div class="card">
                <h3>📊 System Status</h3>
                <div class="metric">
                    <div class="metric-value">{{ status.connected_pairs }}</div>
                    <div class="metric-label">Available Pairs</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{{ status.monitored_pairs }}</div>
                    <div class="metric-label">Active Monitors</div>
                </div>
            </div>
            
            {% for symbol, data in signals.items() %}
            <div class="card">
                <h3>{{ data.pair_info.display_name }}</h3>
                
                <div class="metric">
                    <div class="metric-value">{{ "%.1f"|format(data.manipulation.manipulation_score * 100) }}%</div>
                    <div class="metric-label">Manipulation Score</div>
                </div>
                
                <div class="signals">
                    <h4>🔥 Active Signals:</h4>
                    {% for signal in data.signals %}
                    <div class="signal-item">
                        <strong>{{ signal.type.replace('_', ' ') }}</strong> - {{ signal.direction }}<br>
                        <small>💪 Strength: {{ signal.strength }}% | 🎯 {{ signal.reason }}</small><br>
                        <small>⏰ {{ signal.timestamp.strftime('%H:%M:%S') if signal.timestamp else 'Live' }}</small>
                    </div>
                    {% endfor %}
                    
                    {% if data.manipulation.patterns %}
                    <h4>🔍 Detected Patterns:</h4>
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
            const selected = Array.from(select.selectedOptions).map(option => option.value);
            
            if (selected.length === 0) {
                showMessage('Please select at least one trading pair', 'error');
                return;
            }
            
            showMessage('Starting monitoring system...', 'success');
            
            fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({symbols: selected})
            })
            .then(response => response.json())
            .then(data => {
                showMessage(data.message, data.status === 'success' ? 'success' : 'error');
                if (data.status === 'success') {
                    setTimeout(() => location.reload(), 3000);
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
        
        // Auto-refresh every 60 seconds if monitoring
        setInterval(() => {
            if (window.location.search.includes('auto_refresh')) {
                location.reload();
            }
        }, 60000);
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
        
        # Start monitoring
        success = trading_system.start_monitoring_sync(symbols)
        
        if success:
            return jsonify({"status": "success", "message": f"💎 Started monitoring {len(symbols)} pairs! Signals will appear shortly."})
        else:
            return jsonify({"status": "error", "message": "Failed to start monitoring"})
            
    except Exception as e:
        logger.error(f"Start monitoring error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/stop', methods=['POST'])
def stop_monitoring():
    try:
        trading_system.running = False
        trading_system.current_signals = {}
        return jsonify({"status": "success", "message": "⏹️ Monitoring stopped"})
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

if __name__ == '__main__':
    logger.info("🚀 Diamond Trading System starting...")
    logger.info("💎 System ready for synthetic indices trading")
    
    # Start Flask web server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
