import React, { useState, useEffect } from 'react';

// ─── Number formatters ──────────────────────────────────────────────────────
const fmt$  = v => v == null ? '--' : '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPct = v => v == null ? '--' : Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%';
const fmtVol = v => v == null ? '--' : (v >= 1_000_000 ? (v / 1_000_000).toFixed(1) + 'M' : (v / 1000).toFixed(0) + 'K');
const R = { textAlign: 'right' }; // shorthand right-align style

// ─── Market-aware scan status helpers ──────────────────────────────────────
function getMarketStatus() {
  // All times in ET
  const now = new Date();
  const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const day = et.getDay(); // 0=Sun, 6=Sat
  const h = et.getHours();
  const m = et.getMinutes();
  const mins = h * 60 + m;
  const open  = 9 * 60 + 30;   // 09:30
  const close = 16 * 60;        // 16:00

  if (day === 0 || day === 6) return { open: false, label: 'weekend' };
  if (mins < open)  return { open: false, label: 'pre-market', nextOpen: _nextOpenStr(et, open) };
  if (mins >= close) return { open: false, label: 'after-hours', nextOpen: _nextOpenStr(et, open) };
  return { open: true, label: 'open' };
}

function _nextOpenStr(etNow, openMins) {
  const d = new Date(etNow);
  // advance to next weekday
  d.setHours(Math.floor(openMins / 60), openMins % 60, 0, 0);
  if (d <= etNow) d.setDate(d.getDate() + 1);
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
  return d.toLocaleString('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit' });
}

// ─── Sorting helpers ───────────────────────────────────────────────────────
const ASC  = 'asc';
const DESC = 'desc';

function nextDir(current) {
  if (!current)       return ASC;
  if (current === ASC) return DESC;
  return null; // third click clears sort
}

function SortIndicator({ col, sortCol, sortDir }) {
  if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 3, fontSize: '0.7rem' }}>⇅</span>;
  return <span style={{ marginLeft: 3, color: '#10b981', fontSize: '0.75rem' }}>{sortDir === ASC ? '▲' : '▼'}</span>;
}

// Columns that support sorting in the Scanner table
const SORTABLE = new Set(['symbol', 'price', 'week_52_high', 'volume', 'entry_price']);

function getScanSortValue(r, col) {
  switch (col) {
    case 'symbol':       return (r.symbol ?? '').toLowerCase();
    case 'price':        return r.price        ?? -Infinity;
    case 'week_52_high': return r.week_52_high ?? -Infinity;
    case 'volume':       return r.volume       ?? -Infinity;
    case 'entry_price':  return r.price        ?? -Infinity; // entry shown = scan price
    default:             return 0;
  }
}

function applySort(rows, col, dir) {
  if (!col || !dir) return rows;
  return [...rows].sort((a, b) => {
    const av = getScanSortValue(a, col);
    const bv = getScanSortValue(b, col);
    if (av < bv) return dir === ASC ? -1 : 1;
    if (av > bv) return dir === ASC ?  1 : -1;
    return 0;
  });
}
// ──────────────────────────────────────────────────────────────────────────

function ScannerTable({ results, onRefresh, lastUpdated, onOverrideToggle, onEntryMethodChange, openPositionSymbols, scannerRunning }) {
  const [filter, setFilter]     = useState('all');
  const [viewMode, setViewMode] = useState(
    () => localStorage.getItem('scannerViewMode') || 'simple'
  );
  const [sortCol, setSortCol]   = useState(null);
  const [sortDir, setSortDir]   = useState(null);
  const [tick, setTick]         = useState(0); // forces re-render every second for live elapsed time

  // Re-render every second so elapsed time and market status stay current
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

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

  const filteredResults = applySort(
    results.filter(r => {
      const inPortfolio = r.in_portfolio || openPositionSymbols?.has(r.symbol);
      if (filter === 'portfolio') return inPortfolio;
      if (filter === 'qualified') return r.qualified && !inPortfolio; // exclude in-portfolio
      if (filter === 'failed')    return !r.qualified;
      return true; // 'all'
    }),
    sortCol, sortDir
  );

  // Renders a sortable <th>
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
      <div style={{ marginBottom: '0.5rem', display: 'flex', gap: '0.75rem', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <h2 style={{ fontSize: '1rem', margin: 0 }}>Scanner Results</h2>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ padding: '0.3rem 0.5rem', fontSize: '0.82rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.25rem', color: '#fff' }}
          >
            <option value="all">All Tickers</option>
            <option value="qualified">Qualified Only</option>
            <option value="portfolio">In Portfolio</option>
            <option value="failed">Failed Only</option>
          </select>
          <select
            value={viewMode}
            onChange={(e) => { setViewMode(e.target.value); localStorage.setItem('scannerViewMode', e.target.value); }}
            style={{ padding: '0.3rem 0.5rem', fontSize: '0.82rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.25rem', color: '#fff' }}
          >
            <option value="simple">Simple View (✅/❌)</option>
            <option value="detailed">Detailed View (Numbers)</option>
          </select>
          {/* Refresh button commented out — redundant since WebSocket pushes results automatically every 30s.
              Keep onRefresh prop wired in App.jsx in case we want to restore it later.
          <button className="btn btn-primary" onClick={onRefresh}>🔄 Refresh</button>
          */}
        </div>
        {/* ── Scan status / market status ── */}
        {(() => {
          const mkt     = getMarketStatus();
          const secsAgo = lastUpdated ? Math.floor((new Date() - lastUpdated) / 1000) : null;
          const lastScanStr = lastUpdated
            ? lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : null;
          const agoStr = secsAgo == null ? null
            : secsAgo < 60    ? `${secsAgo}s ago`
            : secsAgo < 3600  ? `${Math.floor(secsAgo / 60)}m ago`
            : `${Math.floor(secsAgo / 3600)}h ago`;

          // ── State 1: Scanner manually stopped ──────────────────────────
          if (!scannerRunning) {
            return (
              <div style={{ fontSize: '13px', fontWeight: '500', textAlign: 'right', lineHeight: '1.5' }}>
                <span style={{ color: '#6b7280' }}>⏹ Scanner Stopped</span>
                {lastScanStr && (
                  <span style={{ color: '#4b5563', marginLeft: '0.75rem' }}>
                    · Last scan: {lastScanStr} ({agoStr})
                  </span>
                )}
              </div>
            );
          }

          // ── State 2: Scanner running, market open ───────────────────────
          if (mkt.open) {
            return (
              <div style={{ fontSize: '13px', fontWeight: '500', textAlign: 'right', lineHeight: '1.5' }}>
                <span style={{ color: '#10b981' }}>🟢 Market Open — Scanner Active</span>
                {lastScanStr && (
                  <span style={{ color: '#6b7280', marginLeft: '0.75rem' }}>
                    · Last scan: {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })} ({agoStr})
                  </span>
                )}
              </div>
            );
          }

          // ── State 3: Scanner running, market closed (sleeping) ──────────
          const statusColor = mkt.label === 'pre-market' ? '#f59e0b' : '#6b7280';
          const statusIcon  = mkt.label === 'weekend' ? '📅' : mkt.label === 'pre-market' ? '🌅' : '🌙';
          const marketLabel = mkt.label === 'weekend' ? 'Closed (Weekend)' : mkt.label === 'pre-market' ? 'Pre-Market' : 'After Hours';
          return (
            <div style={{ fontSize: '13px', fontWeight: '500', textAlign: 'right', lineHeight: '1.5' }}>
              <span style={{ color: statusColor }}>
                {statusIcon} {marketLabel} — Scanner sleeping
                {mkt.nextOpen && (
                  <span style={{ color: '#6b7280', fontWeight: '400' }}>, resumes {mkt.nextOpen} ET</span>
                )}
              </span>
              {lastScanStr && (
                <span style={{ color: '#4b5563', marginLeft: '0.75rem' }}>
                  · Last scan: {lastScanStr} ({agoStr})
                </span>
              )}
            </div>
          );
        })()}
      </div>

      <table>
        <thead>
          <tr>
            <Th col="symbol">Symbol</Th>
            <Th col="price" style={R}>Price</Th>
            <Th col="week_52_high" style={R}>52W High</Th>
            <th style={R}>Within 5%</th>
            <th style={R}>&gt;50MA</th>
            <th style={R}>50&gt;150</th>
            <th style={R}>150&gt;200</th>
            <th style={R}>200↑</th>
            <th style={R}>&gt;30% Low</th>
            <Th col="volume" style={R}>Volume</Th>
            <th>SPY OK</th>
            <th>Qualified</th>
            <th>Action</th>
            <Th col="entry_price">Entry Price</Th>
            <th>Override</th>
          </tr>
        </thead>
        <tbody>
          {filteredResults.map(r => {
            // Use DB-embedded flag (available on first fetch) OR live positions Set
            // (updated via WebSocket) — whichever resolves first, both are correct.
            const inPortfolio = r.in_portfolio || openPositionSymbols?.has(r.symbol);
            return (
              <tr key={r.symbol} className={r.qualified ? 'qualified-row' : ''}>
                <td>
                  <strong>{r.symbol}</strong>
                  {inPortfolio && (
                    <span style={{
                      marginLeft: '6px',
                      fontSize: '0.7rem',
                      background: 'rgba(16,185,129,0.15)',
                      color: '#10b981',
                      border: '1px solid #10b981',
                      borderRadius: '4px',
                      padding: '1px 5px',
                      fontWeight: '600',
                      whiteSpace: 'nowrap'
                    }}>✅ In Portfolio</span>
                  )}
                </td>
                <td style={R}>{fmt$(r.price)}</td>
                <td style={R}>{fmt$(r.week_52_high)}</td>

                {/* Criteria 1: Within 5% of 52W High */}
                <td className={r.criteria_1 ? 'criteria-pass' : 'criteria-fail'} style={R}>
                  {viewMode === 'simple' ? (
                    r.criteria_1 ? '✅' : '❌'
                  ) : (
                    <span style={{ color: r.criteria_1 ? '#10b981' : '#ef4444' }}>
                      {r.week_52_high && r.price
                        ? fmtPct((r.week_52_high - r.price) / r.week_52_high * 100)
                        : '--'}
                    </span>
                  )}
                </td>

                {/* Criteria 2: Price > 50MA */}
                <td className={r.criteria_2 ? 'criteria-pass' : 'criteria-fail'} style={R}>
                  {viewMode === 'simple' ? (
                    r.criteria_2 ? '✅' : '❌'
                  ) : (
                    <span style={{ color: r.criteria_2 ? '#10b981' : '#ef4444' }}>
                      {fmt$(r.ma_50)}
                    </span>
                  )}
                </td>

                {/* Criteria 3: 50MA > 150MA */}
                <td className={r.criteria_3 ? 'criteria-pass' : 'criteria-fail'} style={R}>
                  {viewMode === 'simple' ? (
                    r.criteria_3 ? '✅' : '❌'
                  ) : (
                    <span style={{ color: r.criteria_3 ? '#10b981' : '#ef4444' }}>
                      {fmt$(r.ma_150)}
                    </span>
                  )}
                </td>

                {/* Criteria 4: 150MA > 200MA */}
                <td className={r.criteria_4 ? 'criteria-pass' : 'criteria-fail'} style={R}>
                  {viewMode === 'simple' ? (
                    r.criteria_4 ? '✅' : '❌'
                  ) : (
                    <span style={{ color: r.criteria_4 ? '#10b981' : '#ef4444' }}>
                      {fmt$(r.ma_200)}
                    </span>
                  )}
                </td>

                {/* Criteria 5: 200MA Trending Up */}
                <td className={r.criteria_5 ? 'criteria-pass' : 'criteria-fail'} style={R}>
                  {viewMode === 'simple' ? (
                    r.criteria_5 ? '✅' : '❌'
                  ) : (
                    <span style={{ color: r.criteria_5 ? '#10b981' : '#ef4444' }}>
                      {fmt$(r.ma_200_1m_ago)}
                    </span>
                  )}
                </td>

                {/* Criteria 6: >30% above 52W Low */}
                <td className={r.criteria_6 ? 'criteria-pass' : 'criteria-fail'} style={R}>
                  {viewMode === 'simple' ? (
                    r.criteria_6 ? '✅' : '❌'
                  ) : (
                    <span style={{ color: r.criteria_6 ? '#10b981' : '#ef4444' }}>
                      {r.week_52_low && r.price
                        ? fmtPct((r.price - r.week_52_low) / r.week_52_low * 100)
                        : '--'}
                    </span>
                  )}
                </td>

                {/* Criteria 7: Volume > Avg */}
                <td className={r.criteria_7 ? 'criteria-pass' : 'criteria-fail'} style={R}>
                  {viewMode === 'simple' ? (
                    r.criteria_7 ? '✅' : '❌'
                  ) : (
                    <span style={{ color: r.criteria_7 ? '#10b981' : '#ef4444' }}>
                      {fmtVol(r.avg_volume_50)}
                    </span>
                  )}
                </td>

                {/* Criteria 8: SPY > 50MA */}
                <td className={r.criteria_8 ? 'criteria-pass' : 'criteria-fail'}>
                  {viewMode === 'simple' ? (
                    r.criteria_8 ? '✅' : '❌'
                  ) : (
                    <span style={{ color: r.criteria_8 ? '#10b981' : '#ef4444' }}>
                      {r.criteria_8 ? 'PASS' : 'FAIL'}
                    </span>
                  )}
                </td>

                <td className={r.qualified ? 'criteria-pass' : 'criteria-fail'}>
                  {r.qualified ? '✅ YES' : '❌ NO'}
                </td>

                <td>
                  {inPortfolio ? (
                    <span style={{ color: '#10b981', fontSize: '0.85rem' }}>📈 Holding</span>
                  ) : r.qualified ? (
                    <span className="action-buy">✅ BUYING</span>
                  ) : (
                    <span className="action-pass">⛔ SKIP</span>
                  )}
                </td>

                <td style={{ textAlign: 'center' }}>
                  {inPortfolio ? (
                    <span style={{ color: '#6b7280', fontSize: '0.8rem' }}>—</span>
                  ) : (
                    <select
                      value={r.entry_method || 'prev_close'}
                      onChange={(e) => onEntryMethodChange && onEntryMethodChange(r.symbol, e.target.value)}
                      style={{
                        padding: '4px 8px',
                        background: '#111827',
                        border: '1px solid #374151',
                        borderRadius: '4px',
                        color: '#fff',
                        fontSize: '12px',
                        cursor: 'pointer'
                      }}
                    >
                      <option value="prev_close">Prev Close ({fmt$(r.price)})</option>
                      <option value="market_open">Market Open (requires IB real-time data)</option>
                      <option value="limit_1pct">Limit +1% ({fmt$(r.price * 1.01)})</option>
                    </select>
                  )}
                </td>

                <td style={{ textAlign: 'center' }}>
                  {inPortfolio ? (
                    <span style={{ color: '#6b7280', fontSize: '0.8rem' }}>—</span>
                  ) : (
                    <input
                      type="checkbox"
                      checked={r.override || false}
                      onChange={(e) => onOverrideToggle(r.symbol, e.target.checked)}
                      style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                      title={r.qualified ? 'Check to SKIP buying this stock' : 'Check to mark as overridden'}
                    />
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {filteredResults.length === 0 && (
        <div style={{ textAlign: 'center', padding: '3rem', color: '#6b7280' }}>
          {filter === 'portfolio'
            ? 'No positions in portfolio yet.'
            : filter === 'qualified'
            ? 'No newly qualified stocks (all qualified stocks may already be in portfolio).'
            : 'No results yet. Start the scanner to see data.'}
        </div>
      )}
    </div>
  );
}

export default ScannerTable;
