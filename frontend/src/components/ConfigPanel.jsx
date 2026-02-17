import React, { useState, useEffect } from 'react';

function ConfigPanel({ config, onUpdate }) {
  const [formData, setFormData] = useState({
    stop_loss_pct: 8.0,
    max_positions: 16,
    position_size_usd: 10000,
    paper_trading: true,
    auto_execute: false,
    default_entry_method: 'prev_close'
  });

  useEffect(() => {
    if (config) {
      setFormData({
        stop_loss_pct: config.stop_loss_pct || 8.0,
        max_positions: config.max_positions || 16,
        position_size_usd: config.position_size_usd || 10000,
        paper_trading: config.paper_trading !== false,
        auto_execute: config.auto_execute === true,
        default_entry_method: config.default_entry_method || 'prev_close'
      });
    }
  }, [config]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      const response = await fetch('http://localhost:8000/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });

      const data = await response.json();
      
      if (data.success) {
        alert('✅ Configuration updated!');
        // Refresh config from server to get updated values
        onUpdate();
        // Force re-fetch to update UI
        setTimeout(() => {
          window.location.reload();
        }, 500);
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
          <small style={{ color: '#6b7280', display: 'block', marginTop: '0.25rem' }}>
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
          <small style={{ color: '#6b7280', display: 'block', marginTop: '0.25rem' }}>
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
          <small style={{ color: '#6b7280', display: 'block', marginTop: '0.25rem' }}>
            Dollar amount for each position (default: $10,000)
          </small>
        </div>

        <div className="form-group">
          <label>Default Entry Method</label>
          <select
            value={formData.default_entry_method}
            onChange={(e) => setFormData({ ...formData, default_entry_method: e.target.value })}
            style={{
              width: '100%',
              padding: '0.5rem',
              background: '#111827',
              border: '1px solid #374151',
              borderRadius: '0.25rem',
              color: '#fff'
            }}
          >
            <option value="prev_close">Previous Day Close Price</option>
            <option value="market_open">Market Open Price</option>
            <option value="limit_1pct">Limit Order 1% Above Close</option>
          </select>
          <small style={{ color: '#6b7280', display: 'block', marginTop: '0.25rem' }}>
            Default entry method for newly qualified stocks
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
