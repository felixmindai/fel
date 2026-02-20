import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '../config';

// ─── Formatters ──────────────────────────────────────────────────────────────
const fmt$ = v =>
  v == null ? '--' : '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const fmtPct = v =>
  v == null ? '--' : (Number(v) * 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%';

const fmtNum = v =>
  v == null ? '--' : Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// ─── Section definitions ─────────────────────────────────────────────────────
const SECTIONS = [
  {
    title: 'Balance & Liquidity',
    fields: [
      { key: 'net_liquidation',   label: 'Net Liquidation Value', fmt: fmt$ },
      { key: 'equity_with_loan',  label: 'Equity w/ Loan Value',  fmt: fmt$ },
      { key: 'total_cash',        label: 'Total Cash',            fmt: fmt$ },
      { key: 'settled_cash',      label: 'Settled Cash',          fmt: fmt$ },
      { key: 'available_funds',   label: 'Available Funds',       fmt: fmt$ },
      { key: 'buying_power',      label: 'Buying Power',          fmt: fmt$ },
      { key: 'excess_liquidity',  label: 'Excess Liquidity',      fmt: fmt$ },
      { key: 'cushion',           label: 'Cushion',               fmt: fmtPct },
      { key: 'accrued_cash',      label: 'Accrued Cash',          fmt: fmt$ },
    ],
  },
  {
    title: 'Positions',
    fields: [
      { key: 'gross_position_value', label: 'Gross Position Value', fmt: fmt$ },
      { key: 'leverage',             label: 'Leverage',             fmt: fmtNum },
    ],
  },
  {
    title: 'P&L',
    fields: [
      { key: 'unrealized_pnl', label: 'Unrealized P&L', fmt: fmt$, colored: true },
      { key: 'realized_pnl',   label: 'Realized P&L',   fmt: fmt$, colored: true },
    ],
  },
  {
    title: 'Margin',
    fields: [
      { key: 'init_margin_req',      label: 'Initial Margin Req.',  fmt: fmt$ },
      { key: 'maint_margin_req',     label: 'Maint. Margin Req.',   fmt: fmt$ },
      { key: 'full_init_margin_req', label: 'Full Init. Margin',    fmt: fmt$ },
      { key: 'full_maint_margin_req',label: 'Full Maint. Margin',   fmt: fmt$ },
    ],
  },
  {
    title: 'Day Trading',
    fields: [
      { key: 'day_trades_remaining', label: 'Day Trades Remaining', fmt: fmtNum },
      { key: 'day_trades_t1',        label: 'Day Trades T+1',       fmt: fmtNum },
      { key: 'day_trades_t2',        label: 'Day Trades T+2',       fmt: fmtNum },
    ],
  },
  {
    title: 'Reg T / Other',
    fields: [
      { key: 'regt_equity',    label: 'Reg T Equity',      fmt: fmt$ },
      { key: 'regt_margin',    label: 'Reg T Margin',      fmt: fmt$ },
      { key: 'sma',            label: 'SMA',               fmt: fmt$ },
      { key: 'dividends',      label: 'Dividends',         fmt: fmt$ },
      { key: 'prev_day_equity',label: 'Prev. Day Equity',  fmt: fmt$ },
    ],
  },
];

// ─── MetricCard ──────────────────────────────────────────────────────────────
function MetricCard({ label, value, fmt, colored }) {
  const formatted = fmt ? fmt(value) : (value == null ? '--' : value);
  const valueColor = colored && value != null
    ? (Number(value) >= 0 ? '#10b981' : '#ef4444')
    : '#f9fafb';

  return (
    <div style={{
      background: '#1f2937',
      border: '1px solid #374151',
      borderRadius: '0.5rem',
      padding: '0.875rem 1rem',
      minWidth: '175px',
      flex: '1 1 175px',
    }}>
      <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginBottom: '0.35rem', whiteSpace: 'nowrap' }}>
        {label}
      </div>
      <div style={{ fontSize: '1.05rem', fontWeight: '700', color: valueColor }}>
        {formatted}
      </div>
    </div>
  );
}

// ─── AccountSection ───────────────────────────────────────────────────────────
function AccountSection({ title, fields, data }) {
  // Only render fields that IB actually returned (omit absent/null keys entirely
  // when the raw key is completely missing from data — null values still show as '--')
  const presentFields = fields.filter(f => f.key in data);
  if (presentFields.length === 0) return null;

  return (
    <div style={{ marginBottom: '1.25rem' }}>
      <h3 style={{
        fontSize: '0.78rem',
        fontWeight: '600',
        color: '#6b7280',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        marginBottom: '0.6rem',
        marginTop: 0,
      }}>
        {title}
      </h3>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem' }}>
        {presentFields.map(f => (
          <MetricCard
            key={f.key}
            label={f.label}
            value={data[f.key]}
            fmt={f.fmt}
            colored={f.colored}
          />
        ))}
      </div>
    </div>
  );
}

// ─── DashboardPanel ──────────────────────────────────────────────────────────
function DashboardPanel({ isActive }) {
  const [account, setAccount]     = useState(null);
  const [loading, setLoading]     = useState(true);   // true = first load spinner
  const [error, setError]         = useState(null);
  const [lastFetch, setLastFetch] = useState(null);

  const fetchAccount = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/account`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail || `Error ${res.status}`);
        // Don't clear account — keep stale data visible with the error banner
        return;
      }
      const data = await res.json();
      setAccount(data);
      setError(null);
      setLastFetch(new Date());
    } catch (e) {
      setError('Network error: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch immediately when tab becomes active; poll every 60 s while visible.
  // fetchAccount is stable (useCallback []) so it's safe to omit from deps.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!isActive) return;
    fetchAccount();
    const id = setInterval(fetchAccount, 60_000);
    return () => clearInterval(id);
  }, [isActive]);

  // ── Loading state ──
  if (loading && !account) {
    return (
      <div style={{ textAlign: 'center', padding: '4rem', color: '#6b7280' }}>
        <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>⏳</div>
        Fetching account data from IB…
      </div>
    );
  }

  // ── Error / disconnected state ──
  if (error && !account) {
    return (
      <div style={{ textAlign: 'center', padding: '4rem', color: '#6b7280' }}>
        <div style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>🔌</div>
        <div style={{ fontSize: '1rem', color: '#ef4444', marginBottom: '0.5rem' }}>
          {error}
        </div>
        <div style={{ fontSize: '0.85rem', marginBottom: '1.25rem' }}>
          Make sure IB Gateway / TWS is running and the scanner has been started.
        </div>
        <button
          className="btn btn-primary"
          onClick={fetchAccount}
          style={{ fontSize: '0.85rem' }}
        >
          🔄 Retry
        </button>
      </div>
    );
  }

  const acct = account || {};

  return (
    <div>
      {/* ── Header bar ── */}
      <div style={{
        marginBottom: '1.25rem',
        display: 'flex',
        gap: '1rem',
        alignItems: 'center',
        flexWrap: 'wrap',
      }}>
        <h2 style={{ fontSize: '1rem', margin: 0 }}>Account Dashboard</h2>

        {acct.account_id && (
          <span style={{
            fontSize: '0.88rem',
            fontWeight: '600',
            color: '#e5e7eb',
            background: '#1f2937',
            border: '1px solid #374151',
            borderRadius: '0.35rem',
            padding: '0.2rem 0.6rem',
          }}>
            {acct.account_id}
            {acct.account_type && (
              <span style={{ color: '#9ca3af', fontWeight: '400', marginLeft: '0.5rem' }}>
                · {acct.account_type}
              </span>
            )}
          </span>
        )}

        {lastFetch && (
          <span style={{ fontSize: '0.78rem', color: '#6b7280', marginLeft: 'auto' }}>
            as of {lastFetch.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        )}

        <button
          className="btn btn-secondary"
          onClick={fetchAccount}
          style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem' }}
          title="Refresh account data from IB"
        >
          🔄 Refresh
        </button>
      </div>

      {/* ── Inline error banner (when we have stale data but last call failed) ── */}
      {error && account && (
        <div style={{
          marginBottom: '0.75rem',
          padding: '0.4rem 0.75rem',
          background: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: '0.35rem',
          fontSize: '0.8rem',
          color: '#ef4444',
        }}>
          ⚠️ Last refresh failed: {error} — showing previous data
        </div>
      )}

      {/* ── Sections ── */}
      {SECTIONS.map(s => (
        <AccountSection key={s.title} title={s.title} fields={s.fields} data={acct} />
      ))}
    </div>
  );
}

export default DashboardPanel;
