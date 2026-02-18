import React, { useState, useEffect } from 'react';
import { API_BASE } from '../config';

function TickerManager({ onUpdate }) {
  const [tickers, setTickers] = useState([]);
  const [newSymbol, setNewSymbol] = useState('');
  const [newName, setNewName] = useState('');
  const [newSector, setNewSector] = useState('');

  useEffect(() => {
    fetchTickers();
  }, []);

  const fetchTickers = async () => {
    try {
      const response = await fetch(`${API_BASE}/tickers`);
      const data = await response.json();
      setTickers(data.tickers || []);
    } catch (error) {
      console.error('Error fetching tickers:', error);
    }
  };

  const handleAdd = async () => {
    if (!newSymbol.trim()) {
      alert('Please enter a ticker symbol');
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/tickers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: newSymbol.toUpperCase(),
          name: newName || null,
          sector: newSector || null
        })
      });

      const data = await response.json();
      
      if (data.success) {
        alert(`✅ Added ${newSymbol.toUpperCase()}`);
        setNewSymbol('');
        setNewName('');
        setNewSector('');
        fetchTickers();
        onUpdate();
      }
    } catch (error) {
      alert('❌ Error adding ticker: ' + error.message);
    }
  };

  const handleRemove = async (symbol) => {
    if (!confirm(`Remove ${symbol}?`)) return;

    try {
      const response = await fetch(`${API_BASE}/tickers/${symbol}`, { method: 'DELETE' });
      const data = await response.json();
      
      if (data.success) {
        alert(`✅ Removed ${symbol}`);
        fetchTickers();
        onUpdate();
      }
    } catch (error) {
      alert('❌ Error removing ticker: ' + error.message);
    }
  };

  const activeTickers = tickers.filter(t => t.active);

  return (
    <div>
      <h2>Ticker Management</h2>
      <p style={{ color: '#6b7280', marginBottom: '2rem' }}>
        Total: {activeTickers.length} active tickers (max 100 for delayed data)
      </p>

      <div style={{ background: '#1a1f2e', padding: '1.5rem', borderRadius: '0.5rem', marginBottom: '2rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>Add New Ticker</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 3fr 2fr 1fr', gap: '1rem' }}>
          <input
            type="text"
            placeholder="Symbol (e.g., AAPL)"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            style={{ padding: '0.75rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.5rem', color: '#fff' }}
          />
          <input
            type="text"
            placeholder="Name (optional)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={{ padding: '0.75rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.5rem', color: '#fff' }}
          />
          <input
            type="text"
            placeholder="Sector (optional)"
            value={newSector}
            onChange={(e) => setNewSector(e.target.value)}
            style={{ padding: '0.75rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.5rem', color: '#fff' }}
          />
          <button className="btn btn-primary" onClick={handleAdd}>Add</button>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Name</th>
            <th>Sector</th>
            <th>Added Date</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {tickers.map(ticker => (
            <tr key={ticker.symbol}>
              <td><strong>{ticker.symbol}</strong></td>
              <td>{ticker.name || '--'}</td>
              <td>{ticker.sector || '--'}</td>
              <td>{new Date(ticker.added_date).toLocaleDateString()}</td>
              <td>{ticker.active ? '✅ Active' : '❌ Inactive'}</td>
              <td>
                {ticker.active && (
                  <button 
                    className="btn btn-danger" 
                    style={{ padding: '0.5rem 1rem', fontSize: '0.875rem' }}
                    onClick={() => handleRemove(ticker.symbol)}
                  >
                    Remove
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default TickerManager;
