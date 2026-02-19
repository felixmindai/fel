import React from 'react';

function StatusBar({ status, qualifiedCount, totalTickers, lastScanUpdate }) {
  if (!status) return null;

  const stats = status.statistics || {};

  return (
    <div className="summary-cards">

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
        <div className="subtext">{stats.total_trades || 0} closed trades</div>
      </div>

    </div>
  );
}

export default StatusBar;
