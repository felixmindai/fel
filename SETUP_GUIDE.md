# Minervini Trading Bot - Complete Setup Guide

## 📋 What You Need

### Prerequisites
1. **PostgreSQL 14+** - Database server
2. **Python 3.10+** - Backend
3. **Node.js 18+** - Frontend
4. **Interactive Brokers TWS/Gateway** - Broker connection

---

## 🚀 Installation Steps

### Step 1: PostgreSQL Setup

#### On Windows:
1. Download PostgreSQL from https://www.postgresql.org/download/windows/
2. Install with default settings
3. Remember the password you set for `postgres` user
4. PostgreSQL will run on port 5432 by default

#### On Mac:
```bash
brew install postgresql@14
brew services start postgresql@14
```

#### On Linux:
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

#### Create Database:
```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE minervini_bot;

# Exit
\q
```

---

### Step 2: Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env file with your database password
# Open .env in any text editor and update:
# DB_PASSWORD=your_postgres_password_here
```

---

### Step 3: Initialize Database

```bash
# Still in backend directory with venv activated
python scripts/init_database.py
```

You should see:
```
============================================================
DATABASE INITIALIZATION
============================================================
✅ Database initialized successfully!
```

---

### Step 4: Add Tickers

```bash
# Add default 100-ticker universe
python scripts/bootstrap_data.py --add-tickers
```

---

### Step 5: Bootstrap Historical Data (IMPORTANT!)

This fetches 1 year of historical data from Interactive Brokers.
**Make sure IB TWS or Gateway is running first!**

```bash
# Fetch historical data (takes 5-10 minutes for 100 tickers)
python scripts/bootstrap_data.py
```

You should see progress like:
```
[1/100] Processing AAPL...
  Fetching 1 year of historical data...
  ✅ Saved 252 bars for AAPL
[2/100] Processing MSFT...
  ...
```

---

### Step 6: Frontend Setup

Open a **NEW terminal** window:

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend will run on http://localhost:5173

---

### Step 7: Start Backend Server

In the **backend terminal** (with venv activated):

```bash
# Make sure you're in backend directory
python main.py
```

Backend will run on http://localhost:8000

You should see:
```
🚀 Starting Minervini Trading Bot API...
✅ Connected to Interactive Brokers
✅ Bot API ready
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## 🎯 Using the Application

### 1. Open the App
Go to http://localhost:5173 in your browser

### 2. Configure Settings
- Click **Settings** tab
- Set your preferences:
  - Stop Loss %: 8.0 (default)
  - Max Positions: 16 (default)
  - Position Size: $10,000 (or your preferred amount)
  - Paper Trading: ON (recommended for testing)

### 3. Start Scanner
- Click **Start Scanner** button
- Scanner will continuously check all 100 tickers against 8 criteria
- Results update every 30 seconds

### 4. View Results
- **Scanner View**: Shows all tickers with qualification status
- Green rows = Qualified (all 8 criteria met)
- See each criterion: ✅ or ❌
- Action column shows "BUY_AT_OPEN" or "PASS"

### 5. Portfolio View
- Shows your open positions
- Current P&L for each position
- Stop loss levels
- Exit triggers highlighted in red

---

## 📊 Understanding the 8 Criteria

The scanner checks these requirements for EVERY stock:

1. ✅ **Within 5% of 52-week high** - Breakout near all-time highs
2. ✅ **Above 50-day MA** - Short-term uptrend
3. ✅ **50-day MA > 150-day MA** - Medium-term strength
4. ✅ **150-day MA > 200-day MA** - Long-term uptrend
5. ✅ **200-day MA trending up** - Base quality (vs 1 month ago)
6. ✅ **30% above 52-week low** - Not a falling knife
7. ✅ **Breakout volume 1.5x average** - Institutional buying
8. ✅ **SPY above 50-day MA** - Market health (blocks ALL entries if fails)

**ALL 8 must be TRUE** for a stock to qualify.

---

## 🛡️ Exit Rules

Positions exit automatically when EITHER trigger hits:

### Exit 1: Stop Loss (8% default)
- Price closes 8% below entry → SELL at next open
- Hard stop, no exceptions
- Configurable in Settings (7-10% typical)

### Exit 2: Trend Break
- Price closes below 50-day MA → SELL at next open
- Trend is broken, exit even if above stop

---

## 🔧 Troubleshooting

### "Could not connect to Interactive Brokers"
✅ **Solution:**
1. Make sure TWS or IB Gateway is running
2. Check it's on port 7497 (TWS) or 4001 (Gateway)
3. In TWS: File → Global Configuration → API → Settings
   - Enable ActiveX and Socket Clients
   - Socket port: 7497
   - Trusted IP addresses: 127.0.0.1

### "No data for symbol XYZ"
✅ **Solution:**
1. Check symbol is valid and traded on US exchanges
2. Re-run bootstrap: `python scripts/bootstrap_data.py --force`

### "Database connection error"
✅ **Solution:**
1. Check PostgreSQL is running
2. Verify password in `.env` file
3. Test: `psql -U postgres -d minervini_bot`

### "SPY below 50-day MA - no stocks qualify"
✅ **This is normal!**
- When the market (SPY) is weak, the bot blocks ALL entries
- This is criterion #8 - market health protection
- Wait for market to recover above 50-day MA

### Scanner shows 0 qualified stocks
✅ **Possible reasons:**
1. SPY is below 50-day MA (check criterion #8)
2. Market is range-bound, no breakouts today
3. Volume too light (criterion #7)
4. This is normal - some days have no setups

---

## 📱 Daily Workflow

### Morning (After Market Open)
1. Check scanner results
2. Review qualified stocks (if any)
3. If paper trading: manually create positions
4. If auto-execute: bot will place orders at open

### During Market Hours
- Monitor positions in Portfolio view
- Red highlights = exit trigger hit
- Scanner continues to find new opportunities

### End of Day
- Scanner runs final check
- Exit triggers evaluated on closing prices
- Positions that hit stops will show in red

---

## 🎓 Tips for Success

### Start with Paper Trading
- Toggle ON in Settings
- Practice without real money
- Learn the system first

### Position Sizing
- Don't risk more than 1-2% per trade
- Example: $100K account, 16 positions = $6,250 each
- Configure in Settings

### Entry Discipline
- Only enter stocks that show "BUY_AT_OPEN"
- All 8 criteria must be green
- Don't chase - wait for setup

### Exit Discipline
- Honor the stop loss - NO EXCEPTIONS
- If 50-day MA breaks - EXIT
- Don't hope for recovery

### Market Health
- When SPY < 50-day MA → NO NEW ENTRIES
- Existing positions can stay (they have own stops)
- Wait for market recovery

---

## 📁 Project Structure

```
minervini-bot/
├── backend/
│   ├── main.py              # FastAPI server
│   ├── database.py          # PostgreSQL operations
│   ├── scanner.py           # 8-criteria logic
│   ├── data_fetcher.py      # IBKR data
│   ├── requirements.txt
│   ├── .env                 # YOUR CONFIG
│   └── scripts/
│       ├── init_database.py
│       └── bootstrap_data.py
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main app
│   │   └── components/      # UI components
│   ├── package.json
│   └── vite.config.js
│
└── README.md
```

---

## 🔄 Daily Maintenance

### Update Historical Data
Run daily after market close to get latest bars:

```bash
cd backend
python scripts/update_data.py  # (TODO: create this)
```

For now, the scanner fetches live prices, so daily bars are less critical.

### Backup Database
```bash
pg_dump -U postgres minervini_bot > backup_$(date +%Y%m%d).sql
```

### Restore from Backup
```bash
psql -U postgres minervini_bot < backup_20260217.sql
```

---

## 📞 Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review logs in terminal
3. Verify all prerequisites are installed
4. Contact: jun@example.com

---

## ⚖️ Important Disclaimers

- This is an educational tool
- Past performance doesn't guarantee future results
- Always use stop losses
- Start with paper trading
- Never risk more than you can afford to lose
- Consult a financial advisor for investment decisions

---

## 🎉 You're Ready!

You should now have:
- ✅ Database running
- ✅ 100 tickers added
- ✅ Historical data loaded
- ✅ Backend API running (port 8000)
- ✅ Frontend UI running (port 5173)
- ✅ Connected to Interactive Brokers

**Open http://localhost:5173 and start scanning!**

Good luck and trade safely! 🚀
