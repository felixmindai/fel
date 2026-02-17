# Complete Implementation Guide - Minervini Trading Bot

## 📦 What You Have

I've created a complete trading bot application with:

✅ **Backend (Python/FastAPI)**
- 8-criteria SEPA scanner
- PostgreSQL database integration
- IBKR API integration
- Position management
- WebSocket real-time updates

✅ **Frontend (React)**
- Scanner results table
- Portfolio management
- Ticker management
- Configuration panel

✅ **Scripts**
- Database initialization
- Historical data bootstrap
- Default ticker list (100 stocks)

---

## 🚀 Quick Start Instructions

### 1. Download & Extract

Download the project files and extract to your desired location.

### 2. Install PostgreSQL

**Windows:** https://www.postgresql.org/download/windows/
**Mac:** `brew install postgresql@14`
**Linux:** `sudo apt install postgresql`

Create database:
```sql
CREATE DATABASE minervini_bot;
```

### 3. Setup Backend

```bash
cd backend
python -m venv venv

# Activate venv:
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

pip install -r requirements.txt

# Configure .env
cp .env.example .env
# Edit .env and set DB_PASSWORD

# Initialize database
python scripts/init_database.py

# Add tickers
python scripts/bootstrap_data.py --add-tickers

# Fetch historical data (requires IB TWS running)
python scripts/bootstrap_data.py
```

### 4. Setup Frontend

```bash
cd frontend
npm install
```

### 5. Run Application

**Terminal 1 (Backend):**
```bash
cd backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
python main.py
```

**Terminal 2 (Frontend):**
```bash
cd frontend
npm run dev
```

Open http://localhost:5173

---

## 📝 Frontend Components Code

The following components need to be created in `frontend/src/components/`:

### StatusBar.jsx
```jsx
import React from 'react';

function StatusBar({ status, qualifiedCount, totalTickers }) {
  if (!status) return null;

  const stats = status.statistics || {};

  return (
    <div className="summary-cards">
      <div className="summary-card">
        <h3>Scanner Status</h3>
        <div className="value">{status.scanner_running ? '🟢 Running' : '⚪ Stopped'}</div>
        <div className="subtext">{totalTickers} tickers monitored</div>
      </div>

      <div className="summary-card">
        <h3>Qualified Stocks</h3>
        <div className="value" style={{ color: '#10b981' }}>{qualifiedCount}</div>
        <div className="subtext">Ready to buy</div>
      </div>

      <div className="summary-card">
        <h3>Open Positions</h3>
        <div className="value">{status.open_positions || 0}</div>
        <div className="subtext">of {status.config?.max_positions || 16} max</div>
      </div>

      <div className="summary-card">
        <h3>Win Rate</h3>
        <div className="value">{stats.win_rate?.toFixed(1) || 0}%</div>
        <div className="subtext">{stats.wins || 0}W / {stats.losses || 0}L</div>
      </div>

      <div className="summary-card">
        <h3>Total P&L</h3>
        <div className="value" style={{ color: (stats.total_pnl || 0) >= 0 ? '#10b981' : '#ef4444' }}>
          ${(stats.total_pnl || 0).toFixed(2)}
        </div>
        <div className="subtext">{stats.total_trades || 0} trades</div>
      </div>
    </div>
  );
}

export default StatusBar;
```

### PortfolioPanel.jsx
```jsx
import React from 'react';

function PortfolioPanel({ positions, config, onRefresh }) {
  const handleClosePosition = async (symbol) => {
    if (!confirm(`Close position in ${symbol}?`)) return;

    try {
      const response = await fetch(`/api/positions/${symbol}`, { method: 'DELETE' });
      const data = await response.json();
      
      if (data.success) {
        alert(`✅ Position closed: ${symbol}\nP&L: $${data.pnl.toFixed(2)} (${data.pnl_pct.toFixed(2)}%)`);
        onRefresh();
      }
    } catch (error) {
      alert('❌ Error closing position: ' + error.message);
    }
  };

  if (!positions || positions.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '3rem', color: '#6b7280' }}>
        <h2>No Open Positions</h2>
        <p>Qualified stocks will show in the Scanner tab.</p>
      </div>
    );
  }

  return (
    <div>
      <h2 style={{ marginBottom: '1rem' }}>Open Positions</h2>
      
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Entry Date</th>
            <th>Entry Price</th>
            <th>Current Price</th>
            <th>Quantity</th>
            <th>Cost Basis</th>
            <th>Current Value</th>
            <th>P&L $</th>
            <th>P&L %</th>
            <th>Stop Loss</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(pos => {
            const pnlColor = (pos.pnl || 0) >= 0 ? '#10b981' : '#ef4444';
            const stopLossWarning = pos.current_price && pos.current_price <= pos.stop_loss * 1.02;

            return (
              <tr key={pos.symbol} style={ stopLossWarning ? { background: 'rgba(239, 68, 68, 0.2)' } : {}}>
                <td><strong>{pos.symbol}</strong></td>
                <td>{pos.entry_date}</td>
                <td>${pos.entry_price?.toFixed(2)}</td>
                <td>${pos.current_price?.toFixed(2) || '--'}</td>
                <td>{pos.quantity}</td>
                <td>${pos.cost_basis?.toFixed(2)}</td>
                <td>${pos.current_value?.toFixed(2) || '--'}</td>
                <td style={{ color: pnlColor, fontWeight: 'bold' }}>
                  ${pos.pnl?.toFixed(2) || '--'}
                </td>
                <td style={{ color: pnlColor, fontWeight: 'bold' }}>
                  {pos.pnl_pct?.toFixed(2) || '--'}%
                </td>
                <td>${pos.stop_loss?.toFixed(2)}</td>
                <td>
                  <button 
                    className="btn btn-danger" 
                    style={{ padding: '0.5rem 1rem', fontSize: '0.875rem' }}
                    onClick={() => handleClosePosition(pos.symbol)}
                  >
                    Close
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default PortfolioPanel;
```

### TickerManager.jsx
```jsx
import React, { useState, useEffect } from 'react';

function TickerManager({ onUpdate }) {
  const [tickers, setTickers] = useState([]);
  const [newSymbol, setNewSymbol] = useState('');
  const [newName, setNewName] = useState('');
  const [newSector, setNewSector] = useState('');

  useEffect(() => {
    fetchTickers();
  }, []);

  const fetchTickers = async () => {
    try {
      const response = await fetch('/api/tickers');
      const data = await response.json();
      setTickers(data.tickers || []);
    } catch (error) {
      console.error('Error fetching tickers:', error);
    }
  };

  const handleAdd = async () => {
    if (!newSymbol.trim()) {
      alert('Please enter a ticker symbol');
      return;
    }

    try {
      const response = await fetch('/api/tickers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: newSymbol.toUpperCase(),
          name: newName || null,
          sector: newSector || null
        })
      });

      const data = await response.json();
      
      if (data.success) {
        alert(`✅ Added ${newSymbol.toUpperCase()}`);
        setNewSymbol('');
        setNewName('');
        setNewSector('');
        fetchTickers();
        onUpdate();
      }
    } catch (error) {
      alert('❌ Error adding ticker: ' + error.message);
    }
  };

  const handleRemove = async (symbol) => {
    if (!confirm(`Remove ${symbol}?`)) return;

    try {
      const response = await fetch(`/api/tickers/${symbol}`, { method: 'DELETE' });
      const data = await response.json();
      
      if (data.success) {
        alert(`✅ Removed ${symbol}`);
        fetchTickers();
        onUpdate();
      }
    } catch (error) {
      alert('❌ Error removing ticker: ' + error.message);
    }
  };

  const activeTickers = tickers.filter(t => t.active);

  return (
    <div>
      <h2>Ticker Management</h2>
      <p style={{ color: '#6b7280', marginBottom: '2rem' }}>
        Total: {activeTickers.length} active tickers (max 100 for delayed data)
      </p>

      <div style={{ background: '#1a1f2e', padding: '1.5rem', borderRadius: '0.5rem', marginBottom: '2rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>Add New Ticker</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 3fr 2fr 1fr', gap: '1rem' }}>
          <input
            type="text"
            placeholder="Symbol (e.g., AAPL)"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            style={{ padding: '0.75rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.5rem', color: '#fff' }}
          />
          <input
            type="text"
            placeholder="Name (optional)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={{ padding: '0.75rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.5rem', color: '#fff' }}
          />
          <input
            type="text"
            placeholder="Sector (optional)"
            value={newSector}
            onChange={(e) => setNewSector(e.target.value)}
            style={{ padding: '0.75rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.5rem', color: '#fff' }}
          />
          <button className="btn btn-primary" onClick={handleAdd}>Add</button>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Name</th>
            <th>Sector</th>
            <th>Added Date</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {tickers.map(ticker => (
            <tr key={ticker.symbol}>
              <td><strong>{ticker.symbol}</strong></td>
              <td>{ticker.name || '--'}</td>
              <td>{ticker.sector || '--'}</td>
              <td>{new Date(ticker.added_date).toLocaleDateString()}</td>
              <td>{ticker.active ? '✅ Active' : '❌ Inactive'}</td>
              <td>
                {ticker.active && (
                  <button 
                    className="btn btn-danger" 
                    style={{ padding: '0.5rem 1rem', fontSize: '0.875rem' }}
                    onClick={() => handleRemove(ticker.symbol)}
                  >
                    Remove
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default TickerManager;
```

### ConfigPanel.jsx
```jsx
import React, { useState, useEffect } from 'react';

function ConfigPanel({ config, onUpdate }) {
  const [formData, setFormData] = useState({
    stop_loss_pct: 8.0,
    max_positions: 16,
    position_size_usd: 10000,
    paper_trading: true,
    auto_execute: false
  });

  useEffect(() => {
    if (config) {
      setFormData({
        stop_loss_pct: config.stop_loss_pct || 8.0,
        max_positions: config.max_positions || 16,
        position_size_usd: config.position_size_usd || 10000,
        paper_trading: config.paper_trading !== false,
        auto_execute: config.auto_execute === true
      });
    }
  }, [config]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      const response = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });

      const data = await response.json();
      
      if (data.success) {
        alert('✅ Configuration updated!');
        onUpdate();
      }
    } catch (error) {
      alert('❌ Error updating configuration: ' + error.message);
    }
  };

  return (
    <div>
      <h2 style={{ marginBottom: '2rem' }}>Bot Configuration</h2>

      <form onSubmit={handleSubmit} style={{ maxWidth: '600px' }}>
        <div className="form-group">
          <label>Stop Loss Percentage (%)</label>
          <input
            type="number"
            step="0.1"
            min="1"
            max="20"
            value={formData.stop_loss_pct}
            onChange={(e) => setFormData({ ...formData, stop_loss_pct: parseFloat(e.target.value) })}
          />
          <small style={{ color: '#6b7280' }}>
            Position will exit when price drops this % below entry (default: 8%)
          </small>
        </div>

        <div className="form-group">
          <label>Maximum Positions</label>
          <input
            type="number"
            min="1"
            max="20"
            value={formData.max_positions}
            onChange={(e) => setFormData({ ...formData, max_positions: parseInt(e.target.value) })}
          />
          <small style={{ color: '#6b7280' }}>
            Maximum number of positions to hold simultaneously (default: 16)
          </small>
        </div>

        <div className="form-group">
          <label>Position Size ($)</label>
          <input
            type="number"
            step="1000"
            min="1000"
            value={formData.position_size_usd}
            onChange={(e) => setFormData({ ...formData, position_size_usd: parseFloat(e.target.value) })}
          />
          <small style={{ color: '#6b7280' }}>
            Dollar amount for each position (default: $10,000)
          </small>
        </div>

        <div className="form-group">
          <div className="toggle">
            <input
              type="checkbox"
              id="paper_trading"
              checked={formData.paper_trading}
              onChange={(e) => setFormData({ ...formData, paper_trading: e.target.checked })}
            />
            <label htmlFor="paper_trading">
              Paper Trading Mode
              <br />
              <small style={{ color: '#6b7280' }}>
                When ON, no real orders are placed (recommended for testing)
              </small>
            </label>
          </div>
        </div>

        <div className="form-group">
          <div className="toggle">
            <input
              type="checkbox"
              id="auto_execute"
              checked={formData.auto_execute}
              onChange={(e) => setFormData({ ...formData, auto_execute: e.target.checked })}
              disabled={!formData.paper_trading}
            />
            <label htmlFor="auto_execute">
              Auto-Execute Trades
              <br />
              <small style={{ color: '#6b7280' }}>
                When ON, bot will automatically place orders (requires Paper Trading OFF)
              </small>
            </label>
          </div>
        </div>

        <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '1rem' }}>
          💾 Save Configuration
        </button>
      </form>

      <div style={{ marginTop: '3rem', padding: '1.5rem', background: '#1a1f2e', borderRadius: '0.5rem', border: '1px solid #374151' }}>
        <h3 style={{ marginBottom: '1rem' }}>Current Settings Summary</h3>
        <ul style={{ listStyle: 'none', padding: 0 }}>
          <li style={{ marginBottom: '0.5rem' }}>🛑 Stop Loss: {formData.stop_loss_pct}%</li>
          <li style={{ marginBottom: '0.5rem' }}>📊 Max Positions: {formData.max_positions}</li>
          <li style={{ marginBottom: '0.5rem' }}>💰 Position Size: ${formData.position_size_usd.toLocaleString()}</li>
          <li style={{ marginBottom: '0.5rem' }}>
            {formData.paper_trading ? '📝 Paper Trading: ON' : '💸 Live Trading: ON'}
          </li>
          <li style={{ marginBottom: '0.5rem' }}>
            {formData.auto_execute ? '🤖 Auto-Execute: ON' : '👤 Manual Execute: ON'}
          </li>
        </ul>
      </div>
    </div>
  );
}

export default ConfigPanel;
```

---

## 📁 Complete File Structure

After following this guide, you should have:

```
minervini-bot/
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── scanner.py
│   ├── data_fetcher.py
│   ├── requirements.txt
│   ├── .env
│   └── scripts/
│       ├── init_database.py
│       └── bootstrap_data.py
│
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── index.css
│   │   └── components/
│   │       ├── ScannerTable.jsx
│   │       ├── StatusBar.jsx
│   │       ├── PortfolioPanel.jsx
│   │       ├── TickerManager.jsx
│   │       └── ConfigPanel.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── README.md
└── SETUP_GUIDE.md
```

---

## ✅ Verification Checklist

After setup, verify:

- [ ] PostgreSQL running and `minervini_bot` database exists
- [ ] Backend starts without errors (`python main.py`)
- [ ] Frontend starts and opens in browser (`npm run dev`)
- [ ] Can connect to Interactive Brokers (green indicator)
- [ ] Scanner shows 100 tickers
- [ ] Can start/stop scanner
- [ ] Settings can be updated and persist

---

## 🎯 Next Steps

1. **Test with Paper Trading** - Keep paper_trading ON initially
2. **Monitor Scanner** - Watch how stocks qualify throughout the day
3. **Review Criteria** - Understand why stocks pass/fail each criterion
4. **Practice Entries** - Manually create positions for qualified stocks
5. **Track Performance** - Monitor your paper trading P&L

---

## 📞 Support

If you encounter issues:
1. Check the SETUP_GUIDE.md for detailed troubleshooting
2. Verify all prerequisites are installed
3. Check terminal logs for error messages
4. Ensure IB TWS is running on correct port (7497)

---

## 🎉 You're All Set!

The complete application is ready. Follow the setup steps above and you'll have a fully functional Minervini momentum trading bot!

**Remember:** Start with paper trading and only go live after thorough testing.

Good luck! 🚀
