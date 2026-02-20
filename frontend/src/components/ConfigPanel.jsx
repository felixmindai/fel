import React, { useState, useEffect } from 'react';
import { API_BASE } from '../config';

const GROUP_STYLE = {
  marginBottom: '1rem',
  padding: '1.25rem',
  background: '#1a1f2e',
  borderRadius: '0.5rem',
  border: '1px solid #374151'
};

const GROUP_HEADER_STYLE = {
  marginBottom: '1rem',
  marginTop: 0,
  color: '#d1d5db',
  fontSize: '1rem',
  fontWeight: '600',
  letterSpacing: '0.02em',
  borderBottom: '1px solid #374151',
  paddingBottom: '0.5rem'
};

const SELECT_STYLE = {
  width: '100%',
  padding: '0.5rem',
  background: '#111827',
  border: '1px solid #374151',
  borderRadius: '0.25rem',
  color: '#fff'
};

const HINT = { color: '#6b7280', display: 'block', marginTop: '0.25rem' };

// Two-column grid wrapper for the groups
const GRID_STYLE = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: '1rem',
  alignItems: 'start',
};

// Each column stacks its groups vertically
const COL_STYLE = {
  display: 'flex',
  flexDirection: 'column',
  gap: '1rem',
};

function ConfigPanel({ config, onUpdate, status, dataUpdateStatus, onUpdateDataNow }) {
  const [executing, setExecuting] = useState(false);
  const [scannerBusy, setScannerBusy] = useState(false);
  const [dataUpdating, setDataUpdating] = useState(false);

  const scannerRunning = status?.scanner_running ?? false;
  const duRunning = dataUpdateStatus?.status === 'running';

  // ── Manual controls ───────────────────────────────────────────────────────

  const handleExecuteNow = async () => {
    if (!window.confirm('Execute orders now? This will immediately run buy + exit logic for all qualified tickers.')) return;
    setExecuting(true);
    try {
      const response = await fetch(`${API_BASE}/orders/execute-now`, { method: 'POST' });
      const data = await response.json();
      if (!response.ok) {
        alert('❌ ' + (data.detail || data.message || 'Execution failed'));
      }
    } catch (error) {
      alert('❌ Error: ' + error.message);
    } finally {
      setExecuting(false);
    }
  };

  const handleToggleScanner = async () => {
    setScannerBusy(true);
    try {
      const endpoint = scannerRunning ? '/scanner/stop' : '/scanner/start';
      await fetch(`${API_BASE}${endpoint}`, { method: 'POST' });
      onUpdate(); // refresh parent status
    } catch (error) {
      console.error('Scanner toggle error:', error.message);
    } finally {
      setScannerBusy(false);
    }
  };

  const handleUpdateData = async () => {
    setDataUpdating(true);
    try {
      await onUpdateDataNow();
    } finally {
      setDataUpdating(false);
    }
  };

  const [formData, setFormData] = useState({
    // Buy qualification
    near_52wh_pct: '',
    above_52wl_pct: '',
    volume_multiplier: '',
    spy_filter_enabled: true,
    max_positions: '',
    position_size_usd: '',
    default_entry_method: 'prev_close',
    limit_order_premium_pct: '',
    // Sell qualification
    stop_loss_pct: '',
    trend_break_exit_enabled: true,
    // Scanner scheduler
    data_update_time: '',
    scanner_interval_seconds: '',
    // Execute schedule
    order_execution_time: '',
    auto_execute: false,
    paper_trading: true,
  });

  useEffect(() => {
    if (config) {
      setFormData({
        near_52wh_pct: config.near_52wh_pct ?? '',
        above_52wl_pct: config.above_52wl_pct ?? '',
        volume_multiplier: config.volume_multiplier ?? '',
        spy_filter_enabled: config.spy_filter_enabled !== false,
        max_positions: config.max_positions ?? '',
        position_size_usd: config.position_size_usd ?? '',
        default_entry_method: config.default_entry_method ?? 'prev_close',
        limit_order_premium_pct: config.limit_order_premium_pct ?? '',
        stop_loss_pct: config.stop_loss_pct ?? '',
        trend_break_exit_enabled: config.trend_break_exit_enabled !== false,
        data_update_time: config.data_update_time ?? '',
        scanner_interval_seconds: config.scanner_interval_seconds ?? '',
        order_execution_time: config.order_execution_time ?? '',
        auto_execute: config.auto_execute === true,
        paper_trading: config.paper_trading !== false,
      });
    }
  }, [config]);

  const set = (field, value) => setFormData(prev => ({ ...prev, [field]: value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${API_BASE}/config`, {
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
      <form onSubmit={handleSubmit}>

        {/* ── 2-Column Grid ── */}
        <div style={GRID_STYLE}>

          {/* ── LEFT COLUMN ── */}
          <div style={COL_STYLE}>

            {/* GROUP 1: Buy Qualification */}
            <div style={GROUP_STYLE}>
              <h3 style={GROUP_HEADER_STYLE}>📈 Buy Qualification</h3>

              <div className="form-group">
                <label>Near 52W High (%)</label>
                <input type="number" step="0.5" min="1" max="20"
                  value={formData.near_52wh_pct}
                  onChange={(e) => set('near_52wh_pct', parseFloat(e.target.value))} />
                <small style={HINT}>
                  Criteria 1: Price must be within this % of the 52-week high (Minervini default: 5%)
                </small>
              </div>

              <div className="form-group">
                <label>Above 52W Low (%)</label>
                <input type="number" step="1" min="10" max="100"
                  value={formData.above_52wl_pct}
                  onChange={(e) => set('above_52wl_pct', parseFloat(e.target.value))} />
                <small style={HINT}>
                  Criteria 6: Price must be at least this % above the 52-week low (Minervini default: 30%)
                </small>
              </div>

              <div className="form-group">
                <label>Volume Multiplier (× 50-day avg)</label>
                <input type="number" step="0.1" min="1.0" max="5.0"
                  value={formData.volume_multiplier}
                  onChange={(e) => set('volume_multiplier', parseFloat(e.target.value))} />
                <small style={HINT}>
                  Criteria 7: Volume must be this multiple of the 50-day average (Minervini default: 1.5×)
                </small>
              </div>

              <div className="form-group">
                <div className="toggle">
                  <input type="checkbox" id="spy_filter_enabled"
                    checked={formData.spy_filter_enabled}
                    onChange={(e) => set('spy_filter_enabled', e.target.checked)} />
                  <label htmlFor="spy_filter_enabled">
                    SPY Market Health Filter (Criteria 8)
                    <br />
                    <small style={{ color: '#6b7280' }}>
                      When ON, no stocks qualify if SPY is below its 50-day MA (Minervini default: ON)
                    </small>
                  </label>
                </div>
              </div>

              <div className="form-group">
                <label>Maximum Positions</label>
                <input type="number" min="1" max="100"
                  value={formData.max_positions}
                  onChange={(e) => set('max_positions', parseInt(e.target.value))} />
                <small style={HINT}>Maximum number of positions to hold simultaneously</small>
              </div>

              <div className="form-group">
                <label>Position Size ($)</label>
                <input type="number" step="1000" min="1000"
                  value={formData.position_size_usd}
                  onChange={(e) => set('position_size_usd', parseFloat(e.target.value))} />
                <small style={HINT}>Dollar amount allocated per position</small>
              </div>

              <div className="form-group">
                <label>Default Entry Method</label>
                <select value={formData.default_entry_method}
                  onChange={(e) => set('default_entry_method', e.target.value)}
                  style={SELECT_STYLE}>
                  <option value="prev_close">Previous Day Close Price</option>
                  <option value="market_open">Market Open Price (requires IB real-time data)</option>
                  <option value="limit_1pct">Limit Order Above Close</option>
                </select>
                <small style={HINT}>Default entry method applied to newly qualified stocks</small>
              </div>

              <div className="form-group">
                <label>Limit Order Premium (%)</label>
                <input type="number" step="0.1" min="0.1" max="10"
                  value={formData.limit_order_premium_pct}
                  onChange={(e) => set('limit_order_premium_pct', parseFloat(e.target.value))} />
                <small style={HINT}>
                  Applies to "Limit Order Above Close" entry method — % above prev close to set the limit price (default: 1%)
                </small>
              </div>
            </div>

            {/* GROUP 3: Scanner Scheduler */}
            <div style={GROUP_STYLE}>
              <h3 style={GROUP_HEADER_STYLE}>🔍 Scanner Scheduler</h3>

              <div className="form-group">
                <label>Data Update Time (ET, 24h format)</label>
                <input type="text" placeholder="17:00"
                  value={formData.data_update_time}
                  onChange={(e) => set('data_update_time', e.target.value)} />
                <small style={HINT}>
                  When to pull new daily bar data from IB. Weekdays only. Format: HH:MM (e.g. 17:00 = 5 PM ET).
                  Takes effect on the next scheduler cycle.
                </small>
              </div>

              <div className="form-group">
                <label>Scanner Interval (seconds)</label>
                <input type="number" step="5" min="5" max="300"
                  value={formData.scanner_interval_seconds}
                  onChange={(e) => set('scanner_interval_seconds', parseInt(e.target.value))} />
                <small style={HINT}>
                  How often the live scanner re-evaluates all tickers while running (default: 30s, min: 5s).
                  Takes effect on the next scan cycle.
                </small>
              </div>
            </div>

          </div>{/* end LEFT COLUMN */}

          {/* ── RIGHT COLUMN ── */}
          <div style={COL_STYLE}>

            {/* GROUP 2: Sell Qualification */}
            <div style={GROUP_STYLE}>
              <h3 style={GROUP_HEADER_STYLE}>🛑 Sell Qualification</h3>

              <div className="form-group">
                <label>Stop Loss (%)</label>
                <input type="number" step="0.1" min="1" max="50"
                  value={formData.stop_loss_pct}
                  onChange={(e) => set('stop_loss_pct', parseFloat(e.target.value))} />
                <small style={HINT}>
                  Position exits when price drops this % below entry price (Minervini default: 8%, max 50%)
                </small>
              </div>

              <div className="form-group">
                <div className="toggle">
                  <input type="checkbox" id="trend_break_exit_enabled"
                    checked={formData.trend_break_exit_enabled}
                    onChange={(e) => set('trend_break_exit_enabled', e.target.checked)} />
                  <label htmlFor="trend_break_exit_enabled">
                    Trend Break Exit (Price below 50-day MA)
                    <br />
                    <small style={{ color: '#6b7280' }}>
                      When ON, positions exit when price drops below the 50-day moving average (Minervini default: ON)
                    </small>
                  </label>
                </div>
              </div>
            </div>

            {/* GROUP 4: Execute Schedule */}
            <div style={GROUP_STYLE}>
              <h3 style={GROUP_HEADER_STYLE}>⚡ Execute Schedule</h3>

              <div className="form-group">
                <label>Order Execution Time (ET, 24h format)</label>
                <input type="text" placeholder="09:30"
                  value={formData.order_execution_time}
                  onChange={(e) => set('order_execution_time', e.target.value)} />
                <small style={HINT}>
                  Time to place buy/sell orders. Weekdays only. Format: HH:MM (e.g. 09:30 = market open ET).
                  Takes effect on the next scheduler cycle.
                </small>
              </div>

              <div className="form-group">
                <div className="toggle">
                  <input type="checkbox" id="auto_execute"
                    checked={formData.auto_execute}
                    onChange={(e) => set('auto_execute', e.target.checked)} />
                  <label htmlFor="auto_execute">
                    Auto-Execute Trades
                    <br />
                    <small style={{ color: '#6b7280' }}>
                      When ON, bot automatically places orders at the configured execution time.
                      Orders go to Interactive Brokers — paper account (port 7496) or live account (port 7497) per your .env file.
                    </small>
                  </label>
                </div>
              </div>

              <div className="form-group">
                <div className="toggle">
                  <input type="checkbox" id="paper_trading"
                    checked={formData.paper_trading}
                    onChange={(e) => set('paper_trading', e.target.checked)} />
                  <label htmlFor="paper_trading">
                    Paper Trading Mode
                    <br />
                    <small style={{ color: '#6b7280' }}>
                      When ON, no real orders are placed (recommended for testing)
                    </small>
                  </label>
                </div>
              </div>
            </div>

            {/* GROUP 5: Others */}
            <div style={{ ...GROUP_STYLE, borderColor: '#1f2937' }}>
              <h3 style={{ ...GROUP_HEADER_STYLE, color: '#6b7280', borderColor: '#1f2937', fontWeight: '400', fontSize: '0.9rem' }}>⚙️ Others (System Defaults)</h3>
              <ul style={{ listStyle: 'none', padding: 0, color: '#6b7280', fontSize: '0.85rem', margin: 0 }}>
                <li style={{ marginBottom: '0.4rem' }}>📡 IB API rate limit: 0.5s between bar requests (prevents IB throttling)</li>
                <li style={{ marginBottom: '0.4rem' }}>📅 Max historical fetch: 1 year per ticker per update cycle</li>
                <li style={{ marginBottom: '0.4rem' }}>⏱ Order fill poll interval: 1s (checks IB for fill confirmation)</li>
                <li style={{ marginBottom: '0.4rem' }}>⏱ Order fill timeout: 60s (max wait for fill before giving up)</li>
                <li style={{ marginBottom: '0.4rem' }}>🔄 Scheduler anti-jitter buffer: 2 minutes after each scheduled run</li>
                <li style={{ marginBottom: '0.4rem' }}>🔄 Restart grace window: 10 minutes (fires immediately if restarted shortly after scheduled time)</li>
                <li>🔌 IB connection settings (host, port, client ID): configured in .env file</li>
              </ul>
            </div>

          </div>{/* end RIGHT COLUMN */}

        </div>{/* end GRID */}

        {/* ── Save Button — full width ── */}
        <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '1rem' }}>
          💾 Save Configuration
        </button>

      </form>

      {/* ── Manual Controls — full width, below the save button ── */}
      <div style={{ marginTop: '1.25rem', padding: '1.25rem', background: '#1a1f2e', borderRadius: '0.5rem', border: '1px solid #374151' }}>
        <h3 style={{ ...GROUP_HEADER_STYLE, marginBottom: '1rem' }}>🎛️ Manual Controls</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>

          {/* Scanner toggle */}
          <div>
            <button
              onClick={handleToggleScanner}
              disabled={scannerBusy}
              style={{
                width: '100%', padding: '0.6rem',
                background: scannerRunning ? '#7f1d1d' : '#1e3a5f',
                color: scannerRunning ? '#fca5a5' : '#93c5fd',
                border: `1px solid ${scannerRunning ? '#ef4444' : '#3b82f6'}`,
                borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '600',
                cursor: scannerBusy ? 'not-allowed' : 'pointer', opacity: scannerBusy ? 0.5 : 1
              }}
            >
              {scannerBusy ? '⏳ …' : scannerRunning ? '🛑 Stop Scanner' : '🚀 Start Scanner'}
            </button>
            <small style={{ ...HINT, textAlign: 'center' }}>
              Scanner auto-starts on boot. Stop only for maintenance.
            </small>
          </div>

          {/* Data Update Now */}
          <div>
            <button
              onClick={handleUpdateData}
              disabled={duRunning || dataUpdating}
              style={{
                width: '100%', padding: '0.6rem',
                background: '#1a2e1a',
                color: '#86efac',
                border: '1px solid #22c55e',
                borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '600',
                cursor: (duRunning || dataUpdating) ? 'not-allowed' : 'pointer',
                opacity: (duRunning || dataUpdating) ? 0.5 : 1
              }}
            >
              {duRunning ? `⏳ Updating… ${dataUpdateStatus?.done ?? ''}/${dataUpdateStatus?.total ?? ''}` : '📥 Update Data Now'}
            </button>
            <small style={{ ...HINT, textAlign: 'center' }}>
              Pulls latest daily bars from IB for all tickers.
            </small>
          </div>

          {/* Execute Now */}
          <div>
            <button
              onClick={handleExecuteNow}
              disabled={executing || formData.auto_execute}
              style={{
                width: '100%', padding: '0.6rem',
                background: formData.auto_execute ? '#1f2937' : '#3b0f0f',
                color: formData.auto_execute ? '#4b5563' : '#fca5a5',
                border: `1px solid ${formData.auto_execute ? '#374151' : '#dc2626'}`,
                borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '600',
                cursor: (executing || formData.auto_execute) ? 'not-allowed' : 'pointer',
                opacity: (executing || formData.auto_execute) ? 0.5 : 1
              }}
            >
              {executing ? '⏳ Executing…' : '⚡ Execute Now'}
            </button>
            <small style={{ ...HINT, textAlign: 'center' }}>
              Manually executes the Trading, requires "Auto Execute Trades" to be unchecked.
            </small>
          </div>

        </div>
      </div>

      {/* ── Current Settings Summary — full width ── */}
      <div style={{ marginTop: '1.5rem', padding: '1.25rem', background: '#1a1f2e', borderRadius: '0.5rem', border: '1px solid #374151' }}>
        <h3 style={{ marginBottom: '1rem', marginTop: 0 }}>Current Settings Summary</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.25rem 2rem' }}>
          <div>📈 Near 52W High: <strong>{formData.near_52wh_pct}%</strong></div>
          <div>🛑 Stop Loss: <strong>{formData.stop_loss_pct}%</strong></div>
          <div>📉 Above 52W Low: <strong>{formData.above_52wl_pct}%</strong></div>
          <div>📊 Trend Break Exit: <strong>{formData.trend_break_exit_enabled ? 'ON' : 'OFF'}</strong></div>
          <div>📊 Volume Multiplier: <strong>{formData.volume_multiplier}×</strong></div>
          <div>🕔 Order Execution: <strong>{formData.order_execution_time} ET</strong></div>
          <div>🔭 SPY Filter: <strong>{formData.spy_filter_enabled ? 'ON' : 'OFF'}</strong></div>
          <div>🤖 Auto-Execute: <strong>{formData.auto_execute ? 'ON' : 'OFF'}</strong></div>
          <div>📊 Max Positions: <strong>{formData.max_positions}</strong></div>
          <div>{formData.paper_trading ? '📝 Paper Trading: ' : '💸 Live Trading: '}<strong>ON</strong></div>
          <div>💰 Position Size: <strong>${Number(formData.position_size_usd).toLocaleString()}</strong></div>
          <div>🕔 Data Update: <strong>{formData.data_update_time} ET</strong></div>
          <div>🎯 Entry Method: <strong>{formData.default_entry_method}</strong></div>
          <div>⏱ Scanner Interval: <strong>{formData.scanner_interval_seconds}s</strong></div>
          <div>📐 Limit Premium: <strong>{formData.limit_order_premium_pct}%</strong></div>
        </div>
      </div>

    </div>
  );
}

export default ConfigPanel;
