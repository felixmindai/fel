import React, { useState } from 'react';
import { API_BASE } from '../config';

// ─── Formatters ──────────────────────────────────────────────────────────────
const fmt$  = v => v == null ? '--' : '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPct = v => v == null ? '--' : (Number(v) >= 0 ? '+' : '') + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%';
const R = { textAlign: 'right' };

// ─── Sort helpers ─────────────────────────────────────────────────────────────
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

const SORTABLE = new Set(['symbol', 'entry_date', 'exit_date', 'entry_price', 'exit_price', 'quantity', 'pnl', 'pnl_pct']);

function getSortValue(row, col) {
  switch (col) {
    case 'symbol':      return (row.symbol ?? '').toLowerCase();
    case 'entry_date':  return row.entry_date ?? '';
    case 'exit_date':   return row.exit_date  ?? '';
    case 'entry_price': return row.entry_price ?? -Infinity;
    case 'exit_price':  return row.exit_price  ?? -Infinity;
    case 'quantity':    return row.quantity    ?? 0;
    case 'pnl':         return row.pnl         ?? -Infinity;
    case 'pnl_pct':     return row.pnl_pct     ?? -Infinity;
    default:            return 0;
  }
}

function applySort(rows, col, dir) {
  if (!col || !dir) return rows;
  return [...rows].sort((a, b) => {
    const av = getSortValue(a, col);
    const bv = getSortValue(b, col);
    if (av < bv) return dir === ASC ? -1 : 1;
    if (av > bv) return dir === ASC ?  1 : -1;
    return 0;
  });
}

// ─── Exit reason → human label ───────────────────────────────────────────────
function exitLabel(reason) {
  if (!reason) return '—';
  switch (reason.toUpperCase()) {
    case 'MANUAL_CLOSE':       return '🤖 IB Sell';       // real IB market order via Sell button
    case 'MANUAL_MARK_CLOSED': return '✍️ Mark as Sold';  // DB-only via Mark as Sold button
    case 'STOP_LOSS':          return '🛑 Stop Loss';
    case 'TREND_BREAK':        return '📉 Trend Break';
    default:                   return reason;
  }
}

// ─── Component ────────────────────────────────────────────────────────────────
function ClosedPositionsPanel({ positions, onReopen }) {
  // Default: exit_date DESC (most recent first) — matches DB ORDER BY
  const [sortCol, setSortCol] = useState('exit_date');
  const [sortDir, setSortDir] = useState(DESC);

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

  const sorted = applySort(positions, sortCol, sortDir);

  // Summary totals
  const totalPnl    = positions.reduce((sum, p) => sum + (Number(p.pnl) || 0), 0);
  const totalWins   = positions.filter(p => (Number(p.pnl) || 0) > 0).length;
  const totalLosses = positions.filter(p => (Number(p.pnl) || 0) < 0).length;
  const winRate     = positions.length ? ((totalWins / positions.length) * 100).toFixed(0) : 0;
  const pnlColor    = totalPnl >= 0 ? '#10b981' : '#ef4444';

  const handleMarkAsOpen = async (tradeId, symbol) => {
    if (!confirm(`Revert ${symbol} back to Open Positions?\n\nThis will move the trade back to open status. No IB order is placed.`)) return;
    try {
      const response = await fetch(`${API_BASE}/trades/${tradeId}/reopen`, { method: 'PATCH' });
      const data = await response.json();
      if (!response.ok) {
        alert(`❌ Failed to reopen ${symbol}:\n\n${data.detail || response.statusText}`);
        return;
      }
      if (data.success) {
        alert(`✅ ${symbol} moved back to Open Positions\nStop Loss: ${data.stop_loss != null ? '$' + Number(data.stop_loss).toFixed(2) : 'N/A'}`);
        onReopen?.();
      }
    } catch (error) {
      alert('❌ Error: ' + error.message);
    }
  };

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

  return (
    <div>
      {/* ── Header bar ── */}
      <div style={{ marginBottom: '0.75rem', display: 'flex', gap: '1.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <h2 style={{ fontSize: '1rem', margin: 0 }}>Closed Positions</h2>

        {positions.length > 0 && (
          <>
            <span style={{ fontSize: '0.82rem', color: '#9ca3af' }}>
              {positions.length} trade{positions.length !== 1 ? 's' : ''}
            </span>
            <span style={{ fontSize: '0.82rem', color: '#9ca3af' }}>
              {totalWins}W / {totalLosses}L
              {positions.length > 0 && ` (${winRate}% win rate)`}
            </span>
            <span style={{ fontSize: '0.88rem', fontWeight: '600', color: pnlColor }}>
              Realized P&amp;L: {fmt$(totalPnl)}
            </span>
          </>
        )}
      </div>

      {/* ── Table ── */}
      {positions.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: '#6b7280' }}>
          No closed positions yet.
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <Th col="symbol">Symbol</Th>
              <Th col="entry_date">Entry Date</Th>
              <Th col="exit_date">Exit Date</Th>
              <Th col="entry_price" style={R}>Entry Price</Th>
              <Th col="exit_price"  style={R}>Exit Price</Th>
              <Th col="quantity"    style={R}>Shares</Th>
              <th style={R}>Cost Basis</th>
              <th style={R}>Proceeds</th>
              <Th col="pnl"     style={R}>P&amp;L $</Th>
              <Th col="pnl_pct" style={R}>P&amp;L %</Th>
              <th>Exit Reason</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((pos, idx) => {
              const pnl      = Number(pos.pnl) || 0;
              const pnlColor = pnl >= 0 ? '#10b981' : '#ef4444';
              const rowStyle = pnl >= 0
                ? { background: 'rgba(16, 185, 129, 0.04)' }
                : { background: 'rgba(239, 68, 68, 0.04)' };

              return (
                <tr key={`${pos.symbol}-${pos.exit_date}-${idx}`} style={rowStyle}>
                  <td><strong>{pos.symbol}</strong></td>
                  <td>{pos.entry_date ?? '—'}</td>
                  <td>{pos.exit_date  ?? '—'}</td>
                  <td style={R}>{fmt$(pos.entry_price)}</td>
                  <td style={R}>{fmt$(pos.exit_price)}</td>
                  <td style={R}>{pos.quantity ?? '—'}</td>
                  <td style={R}>{fmt$(pos.cost_basis)}</td>
                  <td style={R}>{fmt$(pos.proceeds)}</td>
                  <td style={{ ...R, color: pnlColor, fontWeight: 'bold' }}>
                    {fmt$(pos.pnl)}
                  </td>
                  <td style={{ ...R, color: pnlColor, fontWeight: 'bold' }}>
                    {fmtPct(pos.pnl_pct)}
                  </td>
                  <td style={{ fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
                    {exitLabel(pos.exit_reason)}
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', opacity: 0.75 }}
                      onClick={() => handleMarkAsOpen(pos.id, pos.symbol)}
                      title="Revert to Open Positions — no IB order placed"
                    >
                      Revert to Open
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>

          {/* ── Summary footer row ── */}
          <tfoot>
            <tr style={{ borderTop: '2px solid #374151', fontWeight: '600' }}>
              <td colSpan={8} style={{ paddingTop: '0.5rem', color: '#9ca3af', fontSize: '0.82rem' }}>
                Total ({positions.length} trades · {totalWins}W / {totalLosses}L · {winRate}% win rate)
              </td>
              <td style={{ ...R, color: pnlColor, paddingTop: '0.5rem' }}>{fmt$(totalPnl)}</td>
              <td colSpan={3} />
            </tr>
          </tfoot>
        </table>
      )}
    </div>
  );
}

export default ClosedPositionsPanel;
