import React, { useState } from 'react';
import { API_BASE } from '../config';

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
  'symbol', 'entry_date', 'entry_price', 'current_price',
  'quantity', 'cost_basis', 'current_value', 'pnl', 'pnl_pct', 'stop_loss',
]);

function getPortfolioSortValue(pos, col) {
  switch (col) {
    case 'symbol':        return (pos.symbol ?? '').toLowerCase();
    case 'entry_date':    return pos.entry_date ?? '';
    case 'entry_price':   return pos.entry_price   ?? -Infinity;
    case 'current_price': return pos.current_price ?? -Infinity;
    case 'quantity':      return pos.quantity       ?? -Infinity;
    case 'cost_basis':    return pos.cost_basis     ?? -Infinity;
    case 'current_value': return pos.current_value  ?? -Infinity;
    case 'pnl':           return pos.pnl            ?? -Infinity;
    case 'pnl_pct':       return pos.pnl_pct        ?? -Infinity;
    case 'stop_loss':     return pos.stop_loss       ?? -Infinity;
    default:              return 0;
  }
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

function PortfolioPanel({ positions, config, onRefresh }) {
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState(null);

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

  const handleClosePosition = async (symbol) => {
    if (!confirm(`Close position in ${symbol}?`)) return;

    try {
      const response = await fetch(`${API_BASE}/positions/${symbol}`, { method: 'DELETE' });
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

  const sortedPositions = applySort(positions, sortCol, sortDir);

  return (
    <div>
      <h2 style={{ marginBottom: '1rem' }}>Open Positions</h2>

      <table>
        <thead>
          <tr>
            <Th col="symbol">Symbol</Th>
            <Th col="entry_date">Entry Date</Th>
            <Th col="entry_price">Fill Price</Th>
            <Th col="current_price">Current Price</Th>
            <Th col="quantity">Quantity</Th>
            <Th col="cost_basis">Cost Basis</Th>
            <Th col="current_value">Current Value</Th>
            <Th col="pnl">P&amp;L $</Th>
            <Th col="pnl_pct">P&amp;L %</Th>
            <Th col="stop_loss">Stop Loss</Th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {sortedPositions.map(pos => {
            const pnlColor = (pos.pnl || 0) >= 0 ? '#10b981' : '#ef4444';
            const stopLossWarning = pos.current_price && pos.current_price <= pos.stop_loss * 1.02;
            const pendingExit = pos.pending_exit === true;
            const exitReasonLabel = pos.exit_reason === 'STOP_LOSS'
              ? '🛑 Stop Loss'
              : pos.exit_reason === 'TREND_BREAK'
              ? '📉 Trend Break'
              : pos.exit_reason || '';

            let rowStyle = {};
            if (pendingExit)      rowStyle = { background: 'rgba(239, 68, 68, 0.25)' };
            else if (stopLossWarning) rowStyle = { background: 'rgba(239, 68, 68, 0.1)' };

            return (
              <tr key={pos.symbol} style={rowStyle}>
                <td><strong>{pos.symbol}</strong></td>
                <td>{pos.entry_date}</td>
                <td>
                  <div style={{ lineHeight: '1.2' }}>
                    <span>${pos.entry_price?.toFixed(2)}</span>
                    {pos.submitted_price && Math.abs(pos.submitted_price - pos.entry_price) >= 0.005 && (
                      <div style={{ fontSize: '0.7rem', color: '#6b7280', marginTop: '2px' }}>
                        submitted: ${pos.submitted_price?.toFixed(2)}
                      </div>
                    )}
                  </div>
                </td>
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
                  {pendingExit ? (
                    <span style={{
                      background: 'rgba(239, 68, 68, 0.2)',
                      color: '#ef4444',
                      padding: '0.25rem 0.5rem',
                      borderRadius: '0.25rem',
                      fontSize: '0.75rem',
                      fontWeight: 'bold',
                      whiteSpace: 'nowrap'
                    }}>
                      ⏳ Sell at Open<br />
                      <span style={{ fontWeight: 'normal', fontSize: '0.7rem' }}>{exitReasonLabel}</span>
                    </span>
                  ) : (
                    <span style={{ color: '#10b981', fontSize: '0.85rem' }}>✅ Holding</span>
                  )}
                </td>
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
