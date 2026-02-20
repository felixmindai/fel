import React, { useState } from 'react';
import { API_BASE } from '../config';

// ─── Number formatters ──────────────────────────────────────────────────────
const fmt$   = v => v == null ? '--' : '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPct = v => v == null ? '--' : Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%';
const R = { textAlign: 'right' };

// ─── Sorting helpers ───────────────────────────────────────────────────────
const ASC  = 'asc';
const DESC = 'desc';

function nextDir(current) {
  if (!current)        return ASC;
  if (current === ASC) return DESC;
  return null;
}

function SortIndicator({ col, sortCol, sortDir }) {
  if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 3, fontSize: '0.7rem' }}>⇅</span>;
  return <span style={{ marginLeft: 3, color: '#10b981', fontSize: '0.75rem' }}>{sortDir === ASC ? '▲' : '▼'}</span>;
}

const SORTABLE = new Set([
  'symbol', 'entry_date', 'entry_price', 'last_price',
  'quantity', 'cost_basis', 'current_value', 'pnl', 'pnl_pct', 'stop_loss', 'ma_50',
]);

function getPortfolioSortValue(pos, col) {
  switch (col) {
    case 'symbol':        return (pos.symbol ?? '').toLowerCase();
    case 'entry_date':    return pos.entry_date ?? '';
    case 'entry_price':   return pos.entry_price  ?? -Infinity;
    case 'last_price':    return pos.last_price   ?? -Infinity;
    case 'quantity':      return pos.quantity      ?? -Infinity;
    case 'cost_basis':    return pos.cost_basis    ?? -Infinity;
    case 'current_value': return pos.current_value ?? -Infinity;
    case 'pnl':           return pos.pnl           ?? -Infinity;
    case 'pnl_pct':       return pos.pnl_pct       ?? -Infinity;
    case 'stop_loss':     return pos.stop_loss      ?? -Infinity;
    case 'ma_50':         return pos.ma_50          ?? -Infinity;
    default:              return 0;
  }
}

// How stale is the last scan price? Returns a short human string or null.
function priceAgeLabel(scanTimeStr) {
  if (!scanTimeStr) return null;
  const secs = Math.floor((Date.now() - new Date(scanTimeStr).getTime()) / 1000);
  if (secs < 120)        return null;              // fresh — don't clutter
  if (secs < 3600)       return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400)      return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

function applySort(rows, col, dir) {
  if (!col || !dir) return rows;
  return [...rows].sort((a, b) => {
    const av = getPortfolioSortValue(a, col);
    const bv = getPortfolioSortValue(b, col);
    if (av < bv) return dir === ASC ? -1 : 1;
    if (av > bv) return dir === ASC ?  1 : -1;
    return 0;
  });
}
// ──────────────────────────────────────────────────────────────────────────

function PortfolioPanel({ positions, config, onRefresh, onStatusRefresh, isMarketOpen }) {
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState(null);
  const [filter, setFilter]   = useState(
    () => localStorage.getItem('portfolioFilter') || 'all'
  );

  function handleSort(col) {
    if (!SORTABLE.has(col)) return;
    if (sortCol === col) {
      const next = nextDir(sortDir);
      if (!next) { setSortCol(null); setSortDir(null); }
      else        setSortDir(next);
    } else {
      setSortCol(col);
      setSortDir(ASC);
    }
  }

  function Th({ col, children, style }) {
    const sortable = SORTABLE.has(col);
    return (
      <th
        onClick={sortable ? () => handleSort(col) : undefined}
        style={{
          cursor: sortable ? 'pointer' : 'default',
          userSelect: 'none',
          whiteSpace: 'nowrap',
          ...style,
        }}
        title={sortable ? 'Click to sort' : undefined}
      >
        {children}
        {sortable && <SortIndicator col={col} sortCol={sortCol} sortDir={sortDir} />}
      </th>
    );
  }

  const handleClosePosition = async (symbol, quantity) => {
    if (!confirm(`Place SELL order for ${symbol} in IB?\n\nThis will sell ${quantity} shares at market price.`)) return;

    try {
      const response = await fetch(`${API_BASE}/positions/${symbol}`, { method: 'DELETE' });
      const data = await response.json();

      if (!response.ok) {
        alert(`❌ Failed to close ${symbol}:\n\n${data.detail || response.statusText}`);
        return;
      }
      if (data.success) {
        const modeLabel = data.mode === 'LIVE' ? '🔴 LIVE' : '📄 PAPER';
        alert(
          `✅ [${modeLabel}] Sell order filled: ${symbol}\n` +
          `Fill Price: $${data.exit_price.toFixed(2)}\n` +
          `P&L: $${data.pnl.toFixed(2)} (${data.pnl_pct.toFixed(2)}%)\n` +
          `IB Order ID: ${data.ib_order_id || 'N/A'} | Status: ${data.ib_status || 'N/A'}`
        );
        onRefresh();         // re-fetch positions list → removes row from table
        onStatusRefresh?.(); // re-fetch status → updates summary cards + tab count
      }
    } catch (error) {
      alert('❌ Error closing position: ' + error.message);
    }
  };

  const handleMarkClosed = async (symbol, entryPrice) => {
    const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
    const defaultPrice = entryPrice != null ? Number(entryPrice).toFixed(2) : '';
    const input = window.prompt(
      `Mark ${symbol} as closed in DB (no IB order).\n\nEnter:  exit-date, exit-price\nExample: ${today}, ${defaultPrice}`,
      `${today}, ${defaultPrice}`
    );
    if (input === null) return; // cancelled

    const parts = input.split(',').map(s => s.trim());
    if (parts.length !== 2) {
      alert('❌ Please enter date and price separated by a comma.\nExample: 2026-02-19, 245.50');
      return;
    }
    const [exitDateStr, exitPriceStr] = parts;

    // Validate date — must be YYYY-MM-DD
    if (!/^\d{4}-\d{2}-\d{2}$/.test(exitDateStr)) {
      alert('❌ Invalid date format — use YYYY-MM-DD (e.g. 2026-02-19).');
      return;
    }
    const exitPrice = parseFloat(exitPriceStr);
    if (isNaN(exitPrice) || exitPrice <= 0) {
      alert('❌ Invalid price — please enter a positive number.');
      return;
    }

    try {
      const response = await fetch(
        `${API_BASE}/positions/${symbol}/mark-closed?exit_price=${exitPrice}&exit_date=${exitDateStr}`,
        { method: 'PATCH' }
      );
      const data = await response.json();
      if (!response.ok) {
        alert(`❌ Failed to mark ${symbol} closed:\n\n${data.detail || response.statusText}`);
        return;
      }
      if (data.success) {
        alert(
          `✅ ${symbol} marked as closed in DB\n` +
          `Exit Date: ${data.exit_date}\n` +
          `Exit Price: $${data.exit_price.toFixed(2)}\n` +
          `P&L: $${data.pnl.toFixed(2)} (${data.pnl_pct.toFixed(2)}%)\n` +
          `(No IB order was placed)`
        );
        onRefresh();
        onStatusRefresh?.();
      }
    } catch (error) {
      alert('❌ Error: ' + error.message);
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

  const sortedPositions = applySort(positions, sortCol, sortDir);
  const trendBreakEnabled = config?.trend_break_exit_enabled !== false; // default true

  // ── Pre-compute sell status for every position (needed for filter counts) ──
  const positionsWithStatus = sortedPositions.map(pos => {
    const slHit      = pos.last_price != null && pos.last_price <= pos.stop_loss;
    const tbHit      = trendBreakEnabled && pos.last_price != null && pos.ma_50 != null
                       && pos.last_price < pos.ma_50;
    const sellQual   = slHit || tbHit;
    const pendingExit = pos.pending_exit === true;
    return { ...pos, _slHit: slHit, _tbHit: tbHit, _sellQual: sellQual, _pendingExit: pendingExit };
  });

  const sellCount    = positionsWithStatus.filter(p => p._pendingExit || p._sellQual).length;
  const holdingCount = positionsWithStatus.filter(p => !p._pendingExit && !p._sellQual).length;

  const filteredPositions = positionsWithStatus.filter(pos => {
    if (filter === 'sell')    return pos._pendingExit || pos._sellQual;
    if (filter === 'holding') return !pos._pendingExit && !pos._sellQual;
    return true; // 'all'
  });

  // ── Summary totals ──────────────────────────────────────────────────────
  const totalUnrealizedPnl     = positions.reduce((sum, p) => sum + (Number(p.pnl)        || 0), 0);
  const totalUnrealizedPnlPct  = (() => {
    const totalCost = positions.reduce((sum, p) => sum + (Number(p.cost_basis) || 0), 0);
    return totalCost > 0 ? (totalUnrealizedPnl / totalCost) * 100 : 0;
  })();
  const totalMarketValue       = positions.reduce((sum, p) => sum + (Number(p.current_value) || 0), 0);
  const totalCostBasis         = positions.reduce((sum, p) => sum + (Number(p.cost_basis)    || 0), 0);

  const unrealizedColor = totalUnrealizedPnl >= 0 ? '#10b981' : '#ef4444';

  return (
    <div>
      <div style={{ marginBottom: '0.75rem', display: 'flex', gap: '1.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <h2 style={{ fontSize: '1rem', margin: 0 }}>Open Positions</h2>
        <select
          value={filter}
          onChange={e => { setFilter(e.target.value); localStorage.setItem('portfolioFilter', e.target.value); }}
          style={{ fontSize: '0.82rem', padding: '0.2rem 0.4rem', borderRadius: '4px', border: '1px solid #374151', background: '#1f2937', color: '#f9fafb', cursor: 'pointer' }}
        >
          <option value="all">All Positions ({positions.length})</option>
          <option value="sell">Sell at Open ({sellCount})</option>
          <option value="holding">Holding ({holdingCount})</option>
        </select>
        {positions.length > 0 && (
          <>
            <span style={{ fontSize: '0.82rem', color: '#9ca3af' }}>
              {filteredPositions.length !== positions.length
                ? `${filteredPositions.length} of ${positions.length} position${positions.length !== 1 ? 's' : ''}`
                : `${positions.length} position${positions.length !== 1 ? 's' : ''}`}
            </span>
            <span style={{ fontSize: '0.82rem', color: '#9ca3af' }}>
              Market Value: {fmt$(totalMarketValue)} (Cost: {fmt$(totalCostBasis)})
            </span>
            <span style={{ fontSize: '0.88rem', fontWeight: '600', color: unrealizedColor }}>
              Unrealized P&amp;L: {fmt$(totalUnrealizedPnl)} ({(totalUnrealizedPnl >= 0 ? '+' : '') + totalUnrealizedPnlPct.toFixed(2)}%)
            </span>
          </>
        )}
      </div>

      <table>
        <thead>
          <tr>
            <Th col="symbol">Symbol</Th>
            <Th col="entry_date">Entry Date</Th>
            <Th col="entry_price" style={R}>Fill Price</Th>
            <Th col="last_price" style={R}>Last Price</Th>
            <Th col="quantity" style={R}>Qty</Th>
            <Th col="cost_basis" style={R}>Cost Basis</Th>
            <Th col="current_value" style={R}>{isMarketOpen ? 'Cur. Value' : 'Last Value'}</Th>
            <Th col="pnl" style={R}>P&amp;L $</Th>
            <Th col="pnl_pct" style={R}>P&amp;L %</Th>
            <Th col="stop_loss" style={R}>Stop Loss</Th>
            <Th col="ma_50" style={R}>MA (50)</Th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {filteredPositions.map(pos => {
            const pnlColor    = (pos.pnl || 0) >= 0 ? '#10b981' : '#ef4444';
            const pendingExit = pos._pendingExit;
            const sellQual    = pos._sellQual;
            const ageLabel    = priceAgeLabel(pos.price_scan_time);

            // ── Distance indicators (how far from each trigger) ──
            // Positive = safe margin above threshold; negative = already triggered
            const distToStop = pos.last_price != null && pos.stop_loss != null
              ? ((pos.last_price - pos.stop_loss) / pos.stop_loss) * 100
              : null;
            const distToMA = pos.last_price != null && pos.ma_50 != null
              ? ((pos.last_price - pos.ma_50) / pos.ma_50) * 100
              : null;
            const fmtDist = v => v == null ? null
              : (v >= 0 ? '+' : '') + v.toFixed(1) + '%';

            let rowStyle = {};
            if (pendingExit || sellQual) rowStyle = { background: 'rgba(239, 68, 68, 0.18)' };

            return (
              <tr key={pos.symbol} style={rowStyle}>
                <td><strong>{pos.symbol}</strong></td>
                <td>{pos.entry_date}</td>
                <td style={R}>
                  <div style={{ lineHeight: '1.2' }}>
                    <span>{fmt$(pos.entry_price)}</span>
                    {pos.submitted_price && Math.abs(pos.submitted_price - pos.entry_price) >= 0.005 && (
                      <div style={{ fontSize: '0.7rem', color: '#6b7280', marginTop: '2px' }}>
                        submitted: {fmt$(pos.submitted_price)}
                      </div>
                    )}
                  </div>
                </td>
                <td style={R}>
                  <div style={{ lineHeight: '1.3' }}>
                    <span>{fmt$(pos.last_price)}</span>
                    {ageLabel && (
                      <div style={{ fontSize: '0.68rem', color: '#6b7280', marginTop: '1px' }}>
                        {ageLabel}
                      </div>
                    )}
                  </div>
                </td>
                <td style={R}>{pos.quantity}</td>
                <td style={R}>{fmt$(pos.cost_basis)}</td>
                <td style={R}>{fmt$(pos.current_value)}</td>
                <td style={{ ...R, color: pnlColor, fontWeight: 'bold' }}>
                  {fmt$(pos.pnl)}
                </td>
                <td style={{ ...R, color: pnlColor, fontWeight: 'bold' }}>
                  {fmtPct(pos.pnl_pct)}
                </td>
                <td style={R}>
                  <div style={{ lineHeight: '1.3' }}>
                    <span>{fmt$(pos.stop_loss)}</span>
                    {distToStop != null && (
                      <div style={{ fontSize: '0.68rem', color: distToStop < 5 ? '#f59e0b' : '#6b7280', marginTop: '1px' }}>
                        {fmtDist(distToStop)}
                      </div>
                    )}
                  </div>
                </td>
                <td style={R}>
                  <div style={{ lineHeight: '1.3' }}>
                    <span>{fmt$(pos.ma_50)}</span>
                    {distToMA != null && (
                      <div style={{ fontSize: '0.68rem', color: distToMA < 3 ? '#f59e0b' : '#6b7280', marginTop: '1px' }}>
                        {fmtDist(distToMA)}
                      </div>
                    )}
                  </div>
                </td>
                <td>
                  {(pendingExit || sellQual) ? (
                    // Sell triggered — either backend confirmed (pendingExit) or
                    // frontend detects criteria met (sellQual). Both mean: sell at next open.
                    <span style={{
                      background: 'rgba(239, 68, 68, 0.2)',
                      color: '#ef4444',
                      padding: '0.25rem 0.5rem',
                      borderRadius: '0.25rem',
                      fontSize: '0.75rem',
                      fontWeight: 'bold',
                      whiteSpace: 'nowrap'
                    }}>
                      ⏳ Sell at Open
                    </span>
                  ) : (
                    <span style={{ color: '#10b981', fontSize: '0.85rem' }}>✅ Holding</span>
                  )}
                </td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  {/* Close — places real IB SELL order, disabled when market is closed */}
                  <button
                    className="btn btn-danger"
                    style={{ padding: '0.25rem 0.75rem', fontSize: '0.8rem', marginRight: '0.4rem' }}
                    onClick={() => handleClosePosition(pos.symbol, pos.quantity)}
                    disabled={!isMarketOpen}
                    title={!isMarketOpen
                      ? 'Market is closed — available Mon-Fri 9:30am–4:00pm ET'
                      : `Sell ${pos.quantity} shares at market price via IB`}
                  >
                    Sell
                  </button>
                  {/* DB-only status sync — for when position is already closed in IB */}
                  <button
                    className="btn btn-secondary"
                    style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', opacity: 0.65 }}
                    onClick={() => handleMarkClosed(pos.symbol, pos.entry_price)}
                    title="Sync DB: mark this position as sold without placing an IB order"
                  >
                    Mark as Sold
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
