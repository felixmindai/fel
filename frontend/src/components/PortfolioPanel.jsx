import React from 'react';

const API_BASE = 'http://localhost:8000/api';

function PortfolioPanel({ positions, config, onRefresh }) {
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

  return (
    <div>
      <h2 style={{ marginBottom: '1rem' }}>Open Positions</h2>
      
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Entry Date</th>
            <th>Entry Price</th>
            <th>Current Price</th>
            <th>Quantity</th>
            <th>Cost Basis</th>
            <th>Current Value</th>
            <th>P&L $</th>
            <th>P&L %</th>
            <th>Stop Loss</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(pos => {
            const pnlColor = (pos.pnl || 0) >= 0 ? '#10b981' : '#ef4444';
            const stopLossWarning = pos.current_price && pos.current_price <= pos.stop_loss * 1.02;

            return (
              <tr key={pos.symbol} style={stopLossWarning ? { background: 'rgba(239, 68, 68, 0.2)' } : {}}>
                <td><strong>{pos.symbol}</strong></td>
                <td>{pos.entry_date}</td>
                <td>${pos.entry_price?.toFixed(2)}</td>
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
