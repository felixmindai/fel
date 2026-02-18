import React from 'react';

function StatusBar({ status, qualifiedCount, totalTickers, lastScanUpdate, dataUpdateStatus, onUpdateDataNow }) {
  if (!status) return null;

  const stats = status.statistics || {};

  // ── Data Update card helpers ──────────────────────────────────────────────
  const duStatus  = dataUpdateStatus?.status  || 'idle';
  const duRunning = duStatus === 'running';
  const duFailed  = duStatus === 'failed';
  const duDone    = dataUpdateStatus?.done;
  const duTotal   = dataUpdateStatus?.total;

  let duLabel, duSub, duColor;
  if (duRunning) {
    duColor = '#f59e0b';
    const progress = (duDone != null && duTotal) ? ` ${duDone}/${duTotal}` : '';
    duLabel = `Updating…${progress}`;
    duSub   = dataUpdateStatus?.current_symbol ? `→ ${dataUpdateStatus.current_symbol}` : 'Fetching bars…';
  } else if (duFailed) {
    duColor = '#ef4444';
    duLabel = 'Update failed';
    duSub   = dataUpdateStatus?.error
      ? dataUpdateStatus.error.slice(0, 40)
      : 'Check backend logs';
  } else if (duStatus === 'success' || dataUpdateStatus?.last_update) {
    duColor = '#10b981';
    const ts = dataUpdateStatus?.last_update;
    if (ts) {
      const d = new Date(ts);
      duLabel = `Updated ${d.toLocaleDateString([], { month: '2-digit', day: '2-digit' })} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    } else {
      duLabel = 'Up to date';
    }
    duSub = 'Daily bars current';
  } else {
    duColor = '#6b7280';
    duLabel = 'Never updated';
    duSub   = 'Click to fetch bars';
  }

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
        <div className="subtext">{stats.total_trades || 0} closed trades</div>
      </div>

      {/* ── Data Update card ───────────────────────────────────────────── */}
      <div className="summary-card">
        <h3>Data Update</h3>
        <div className="value" style={{ color: duColor, fontSize: '1rem', lineHeight: '1.3' }}>
          {duLabel}
        </div>
        <div className="subtext" style={{ marginBottom: '0.5rem' }}>{duSub}</div>
        <button
          className="btn btn-primary"
          style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem', marginTop: '0.25rem' }}
          onClick={onUpdateDataNow}
          disabled={duRunning}
        >
          {duRunning ? 'Updating…' : 'Update Now'}
        </button>
      </div>
    </div>
  );
}

export default StatusBar;
