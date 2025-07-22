# 💎 Diamond Trading System

**Production-ready synthetic trading system with advanced manipulation detection and Telegram notifications.**

## 🚀 Quick Deploy

### Option 1: Render (Recommended)
1. Fork this repository
2. Connect to [Render](https://render.com)
3. Set environment variables (see below)
4. Deploy automatically with `render.yaml`

### Option 2: Railway
```bash
railway login
railway init
railway up
```

### Option 3: Heroku
```bash
heroku create your-app-name
heroku config:set DERIV_API_TOKEN=your_token
heroku config:set TELEGRAM_BOT_TOKEN=your_bot_token
heroku config:set TELEGRAM_CHAT_ID=your_chat_id
git push heroku main
```

### Option 4: Docker
```bash
docker build -t diamond-trading .
docker run -p 5000:5000 --env-file .env diamond-trading
```

## 🔧 Environment Setup

### Required Variables
```env
DERIV_API_TOKEN=your_deriv_api_token_here
```

### Optional Variables (Telegram Notifications)
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

## 📋 Getting API Credentials

### 1. Deriv API Token
1. Visit: [https://app.deriv.com/account/api-token](https://app.deriv.com/account/api-token)
2. Create new token with permissions:
   - ✅ Read
   - ✅ Trading information
   - ✅ Payments (for account info)
3. Copy token to environment variables

### 2. Telegram Bot Setup (Optional)
1. **Create Bot:**
   - Message [@BotFather](https://t.me/BotFather) on Telegram
   - Send `/newbot` command
   - Follow instructions to create bot
   - Copy the bot token

2. **Get Chat ID:**
   - Start chat with your bot
   - Send any message to your bot
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find your chat ID in the response

3. **Add to Environment:**
   - `TELEGRAM_BOT_TOKEN`: Your bot token from BotFather
   - `TELEGRAM_CHAT_ID`: Your chat ID from getUpdates

## ✨ Features

### 🎯 Core Trading Features
- ✅ **Real Deriv API Integration** - Live connection to Deriv markets
- ✅ **Multiple Trading Pairs** - V10, V25, V50, V75, V100 synthetic indices
- ✅ **Historical Data Download** - 2+ years of tick data for analysis
- ✅ **Real-time Monitoring** - 1-second tick processing
- ✅ **SQLite Database** - Persistent data storage

### 🧠 Advanced Analysis
- ✅ **Manipulation Detection** - Identifies platform manipulation patterns
- ✅ **Spread Spike Analysis** - Detects artificial spread increases
- ✅ **Counter-Signal Generation** - Signals that exploit platform weaknesses
- ✅ **Pattern Recognition** - Advanced algorithmic pattern detection
- ✅ **Risk Management** - Dynamic stop-loss and take-profit calculations

### 📱 Telegram Notifications
- ✅ **Signal Alerts** - High-strength trading signals (≥80% confidence)
- ✅ **Manipulation Alerts** - Platform manipulation warnings (≥80% score)
- ✅ **System Status** - Startup/shutdown notifications
- ✅ **Smart Filtering** - Prevents spam with cooldown timers
- ✅ **Rich Formatting** - Professional signal layout with emojis

### 🌐 Web Dashboard
- ✅ **Real-time Dashboard** - Live monitoring interface
- ✅ **Pair Selection** - Choose which symbols to monitor
- ✅ **Signal Display** - Visual representation of all signals
- ✅ **Manipulation Metrics** - Live manipulation scoring
- ✅ **System Controls** - Start/stop monitoring, test Telegram

## 📊 Supported Trading Pairs

- **Volatility 10 (1s)** - V10_1S
- **Volatility 25 (1s)** - V25_1S  
- **Volatility 50 (1s)** - V50_1S
- **Volatility 75 (1s)** - V75_1S
- **Volatility 100 (1s)** - V100_1S

*And all other Deriv synthetic indices available via API*

## 🎮 How to Use

1. **Deploy** using one of the methods above
2. **Configure** environment variables
3. **Access** your dashboard at your deployed URL
4. **Select** trading pairs to monitor
5. **Start** monitoring and receive signals

### Dashboard Access
- **Local:** http://localhost:5000
- **Deployed:** https://your-app-name.onrender.com (or your domain)

### Telegram Notifications
Once configured, you'll receive:
- 🟢 **BUY signals** when counter-manipulation opportunities detected
- 🔴 **SELL signals** for bearish manipulation patterns
- 🚨 **Manipulation alerts** when platform bias exceeds 80%
- 🤖 **System updates** when monitoring starts/stops

## 🔒 Security & Disclaimers

### ⚠️ Important Warnings
- **Educational Purpose Only** - This system is for learning and analysis
- **Not Financial Advice** - All signals are educational, not trading recommendations
- **High Risk Activity** - Trading involves significant risk of loss
- **Demo Accounts Recommended** - Test with demo accounts first

### 🛡️ Security Features
- Environment variables for sensitive data
- No hardcoded credentials
- SQLite database for local data storage
- HTTPS recommended for production

## 📈 System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Deriv API     │────│  Diamond Core    │────│   Web Dashboard │
│  (WebSocket)    │    │    Engine        │    │   (Flask App)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                       ┌──────────────────┐
                       │  SQLite Database │
                       │  (Historical +   │
                       │   Live Data)     │
                       └──────────────────┘
                              │
                       ┌──────────────────┐
                       │ Telegram Bot API │
                       │  (Notifications) │
                       └──────────────────┘
```

## 🛠️ Local Development

```bash
# Clone repository
git clone https://github.com/yourusername/diamond-trading-system.git
cd diamond-trading-system

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your tokens

# Run locally
python app.py
```

## 📊 Performance Metrics

The system tracks and displays:
- **Manipulation Detection Rate** - Percentage of manipulative patterns detected
- **Signal Accuracy** - Success rate of generated signals
- **Response Time** - Latency from market event to signal generation
- **Data Processing Rate** - Ticks processed per second
- **System Uptime** - Reliability metrics

## 🔧 Troubleshooting

### Common Issues

**Connection Failed:**
- Verify `DERIV_API_TOKEN` is correct
- Check Deriv API token has required permissions
- Ensure internet connectivity

**Telegram Not Working:**
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
- Send a message to your bot first
- Use "Test Telegram" button in dashboard

**No Signals Generated:**
- System needs time to collect data (15-30 minutes)
- Ensure selected pairs are active
- Check manipulation detection is working

**Database Errors:**
- Ensure write permissions in application directory
- SQLite database created automatically
- Check disk space availability

## 📞 Support & Contributions

This is an open-source educational project. 

### Contributing
1. Fork the repository
2. Create feature branch
3. Make improvements
4. Submit pull request

### Issues
Report bugs and request features via GitHub issues.

## 📄 License

This project is for educational purposes only. Use at your own risk.

---

**Remember:** This system connects to real markets and generates real trading signals. Always use proper risk management and never trade with money you can't afford to lose.

**Test First:** Use demo accounts and paper trading before any live trading.

**Stay Legal:** Ensure compliance with your local regulations regarding automated trading systems.
