import React, { useState, useEffect } from 'react';

// ─── Number formatters ──────────────────────────────────────────────────────
const fmt$  = v => v == null ? '--' : '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPct = v => v == null ? '--' : Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%';
const fmtVol = v => v == null ? '--' : (v >= 1_000_000 ? (v / 1_000_000).toFixed(1) + 'M' : (v / 1000).toFixed(0) + 'K');
const R = { textAlign: 'right' }; // shorthand right-align style

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

function ScannerTable({ results, onRefresh, onOverrideToggle, onEntryMethodChange, openPositionSymbols, onFilteredCountChange }) {
  const [filter, setFilter]     = useState('all');
  const [viewMode, setViewMode] = useState(
    () => localStorage.getItem('scannerViewMode') || 'simple'
  );
  const [sortCol, setSortCol]   = useState(null);
  const [sortDir, setSortDir]   = useState(null);

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

  // Pre-compute counts for each filter option (mirrors the filter conditions below)
  const totalCount     = results.length;
  const qualifiedCount = results.filter(r => {
    const inPortfolio = r.in_portfolio || openPositionSymbols?.has(r.symbol);
    return r.qualified && !inPortfolio;
  }).length;
  const portfolioCount = results.filter(r =>
    r.in_portfolio || openPositionSymbols?.has(r.symbol)
  ).length;
  const failedCount    = results.filter(r => !r.qualified).length;

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

  // Notify parent whenever the visible row count changes (filter or data change)
  useEffect(() => {
    onFilteredCountChange?.(filteredResults.length);
  }, [filteredResults.length, onFilteredCountChange]);

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
      <div style={{ marginBottom: '0.5rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <h2 style={{ fontSize: '1rem', margin: 0 }}>Scanner Results</h2>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ padding: '0.3rem 0.5rem', fontSize: '0.82rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.25rem', color: '#fff' }}
        >
          <option value="all">All Tickers ({totalCount})</option>
          <option value="qualified">Qualified Only ({qualifiedCount})</option>
          <option value="portfolio">In Portfolio ({portfolioCount})</option>
          <option value="failed">Failed Only ({failedCount})</option>
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
