# Minervini Momentum Trading Bot

A momentum stock scanner and portfolio manager implementing Mark Minervini's SEPA methodology.

## Features

- 8-criteria SEPA scanner for breakout identification
- Portfolio management (max 16 positions)
- Automatic stop loss (7-8% configurable)
- Trend break detection (50-day MA)
- Real-time WebSocket updates
- Paper trading mode
- Position tracking and trade history

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, PostgreSQL
- **Frontend**: React + Vite
- **Broker**: Interactive Brokers (TWS/Gateway)
- **Database**: PostgreSQL 14+

## Installation

### Prerequisites

1. **PostgreSQL 14+** installed and running
2. **Python 3.10+**
3. **Node.js 18+**
4. **Interactive Brokers TWS or Gateway** running on port 7497

### Backend Setup

```bash
# 1. Create virtual environment
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure database
cp .env.example .env
# Edit .env with your PostgreSQL credentials

# 4. Initialize database
python scripts/init_database.py

# 5. Bootstrap historical data (one-time, takes 5-10 minutes)
python scripts/bootstrap_data.py

# 6. Run backend
python main.py
```

Backend will run on http://localhost:8000

### Frontend Setup

```bash
# 1. Install dependencies
cd frontend
npm install

# 2. Run development server
npm run dev
```

Frontend will run on http://localhost:5173

## Configuration

Edit `backend/.env`:

```env
# Database
DB_NAME=minervini_bot
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Interactive Brokers
IB_HOST=127.0.0.1
IB_PORT=7497
IB_CLIENT_ID=1

# Bot Settings (defaults, can be changed in UI)
DEFAULT_STOP_LOSS_PCT=8.0
DEFAULT_MAX_POSITIONS=16
DEFAULT_POSITION_SIZE=10000
```

## Usage

### 1. Add Tickers

Go to **Ticker Management** page and add your universe of stocks (100 max for delayed data).

Default list includes quality large caps and mid caps.

### 2. Bootstrap Data

First time only - run the bootstrap script to fetch 1 year of historical data:

```bash
cd backend
python scripts/bootstrap_data.py
```

### 3. Start Scanner

1. Ensure IB TWS/Gateway is running
2. Click **Start Scanner** in the UI
3. Scanner will continuously evaluate all tickers against 8 criteria
4. Qualified stocks show "BUY AT OPEN" in Action column

### 4. Configure Settings

In **Settings** panel:
- Set position size ($)
- Set max positions (default 16)
- Set stop loss % (default 8%)
- Toggle paper trading mode

### 5. Monitor Positions

- **Scanner View**: Shows all tickers with qualification status
- **Portfolio View**: Shows open positions with P&L and exit triggers

## 8-Criteria SEPA Scanner

All 8 must be TRUE for a stock to qualify:

1. ✅ Price within 5% of 52-week high
2. ✅ Price above 50-day MA
3. ✅ 50-day MA above 150-day MA
4. ✅ 150-day MA above 200-day MA
5. ✅ 200-day MA trending up (vs 1 month ago)
6. ✅ Price at least 30% above 52-week low
7. ✅ Breakout on above-average volume (1.5x)
8. ✅ SPY above its 50-day MA (market health)

## Exit Rules

Positions exit automatically when either trigger hits:

1. **Stop Loss**: Price closes 7-8% below entry (configurable)
2. **Trend Break**: Price closes below 50-day MA

## Database Schema

- `tickers`: Monitored stock universe
- `daily_bars`: Historical OHLCV data
- `scan_results`: Daily scanner results
- `positions`: Open positions
- `trades`: Trade history
- `bot_config`: Bot settings

## API Endpoints

- `GET /api/status` - Bot status
- `POST /api/scanner/start` - Start scanner
- `POST /api/scanner/stop` - Stop scanner
- `GET /api/scanner/results` - Latest scan results
- `GET /api/positions` - Open positions
- `GET /api/trades` - Trade history
- `GET /api/tickers` - Ticker list
- `POST /api/tickers` - Add ticker
- `DELETE /api/tickers/{symbol}` - Remove ticker
- `GET /api/config` - Bot configuration
- `PUT /api/config` - Update configuration

## WebSocket

Connect to `ws://localhost:8000/ws` for real-time updates:

- Scanner results
- Position updates
- Trade executions
- Bot status

## Development

### Run Tests

```bash
cd backend
pytest tests/
```

### Database Migrations

```bash
cd backend
python scripts/migrate.py
```

## Troubleshooting

### Can't connect to IB

- Ensure TWS/Gateway is running
- Check port 7497 is open
- Enable API connections in TWS settings
- Verify client ID doesn't conflict

### Scanner not finding qualified stocks

- Check SPY is above its 50-day MA (criterion #8)
- Verify historical data is loaded (`daily_bars` table)
- Market may not have qualifying breakouts today

### Missing historical data

Re-run bootstrap:
```bash
cd backend
python scripts/bootstrap_data.py --force
```

## License

Proprietary - Internal Use Only

## Support

Contact: jun@example.com
