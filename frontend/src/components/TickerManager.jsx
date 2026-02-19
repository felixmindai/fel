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
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', marginBottom: '0.75rem' }}>
        <h2 style={{ margin: 0 }}>Ticker Management</h2>
        <span style={{ color: '#6b7280', fontSize: '0.85rem' }}>
          {activeTickers.length} active tickers (max 100 for delayed data)
        </span>
      </div>

      <div style={{ background: '#1a1f2e', padding: '0.75rem 1rem', borderRadius: '0.5rem', marginBottom: '1rem', border: '1px solid #374151' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 3fr 2fr auto', gap: '0.6rem', alignItems: 'center' }}>
          <input
            type="text"
            placeholder="Symbol (e.g., AAPL)"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            style={{ padding: '0.4rem 0.6rem', fontSize: '0.85rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.375rem', color: '#fff' }}
          />
          <input
            type="text"
            placeholder="Name (optional)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={{ padding: '0.4rem 0.6rem', fontSize: '0.85rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.375rem', color: '#fff' }}
          />
          <input
            type="text"
            placeholder="Sector (optional)"
            value={newSector}
            onChange={(e) => setNewSector(e.target.value)}
            style={{ padding: '0.4rem 0.6rem', fontSize: '0.85rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.375rem', color: '#fff' }}
          />
          <button className="btn btn-primary" style={{ padding: '0.4rem 1rem', fontSize: '0.85rem', whiteSpace: 'nowrap' }} onClick={handleAdd}>Add Ticker</button>
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
                    style={{ padding: '0.25rem 0.75rem', fontSize: '0.8rem' }}
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
