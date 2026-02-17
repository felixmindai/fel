import React, { useState } from 'react';

function ScannerTable({ results, onRefresh, lastUpdated, onOverrideToggle }) {
  const [filter, setFilter] = useState('all');
  const [viewMode, setViewMode] = useState('simple'); // 'simple' or 'detailed'

  const filteredResults = results.filter(r => {
    if (filter === 'qualified') return r.qualified;
    if (filter === 'failed') return !r.qualified;
    return true;
  });

  return (
    <div>
      <div style={{ marginBottom: '1rem', display: 'flex', gap: '1rem', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <h2>Scanner Results</h2>
          <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{padding: '0.5rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.25rem', color: '#fff'}}>
            <option value="all">All Tickers</option>
            <option value="qualified">Qualified Only</option>
            <option value="failed">Failed Only</option>
          </select>
          <select value={viewMode} onChange={(e) => setViewMode(e.target.value)} style={{padding: '0.5rem', background: '#111827', border: '1px solid #374151', borderRadius: '0.25rem', color: '#fff'}}>
            <option value="simple">Simple View (✅/❌)</option>
            <option value="detailed">Detailed View (Numbers)</option>
          </select>
          <button className="btn btn-primary" onClick={onRefresh}>🔄 Refresh</button>
        </div>
        {lastUpdated && (
          <div style={{ fontSize: '14px', color: '#10b981', fontWeight: '500' }}>
            📊 Last Scan: {lastUpdated.toLocaleTimeString()} ({Math.floor((new Date() - lastUpdated) / 1000)}s ago)
          </div>
        )}
      </div>

      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Price</th>
            <th>52W High</th>
            <th>Within 5%</th>
            <th>&gt;50MA</th>
            <th>50&gt;150</th>
            <th>150&gt;200</th>
            <th>200↑</th>
            <th>&gt;30% Low</th>
            <th>Volume</th>
            <th>SPY OK</th>
            <th>Qualified</th>
            <th>Action</th>
            <th>Override</th>
          </tr>
        </thead>
        <tbody>
          {filteredResults.map(r => (
            <tr key={r.symbol} className={r.qualified ? 'qualified-row' : ''}>
              <td><strong>{r.symbol}</strong></td>
              <td>${r.price?.toFixed(2) || '--'}</td>
              <td>${r.week_52_high?.toFixed(2) || '--'}</td>
              
              {/* Criteria 1: Within 5% of 52W High */}
              <td className={r.criteria_1 ? 'criteria-pass' : 'criteria-fail'}>
                {viewMode === 'simple' ? (
                  r.criteria_1 ? '✅' : '❌'
                ) : (
                  <span style={{color: r.criteria_1 ? '#10b981' : '#ef4444'}}>
                    {r.week_52_high && r.price 
                      ? (((r.week_52_high - r.price) / r.week_52_high * 100).toFixed(1) + '%')
                      : '--'
                    }
                  </span>
                )}
              </td>
              
              {/* Criteria 2: Price > 50MA */}
              <td className={r.criteria_2 ? 'criteria-pass' : 'criteria-fail'}>
                {viewMode === 'simple' ? (
                  r.criteria_2 ? '✅' : '❌'
                ) : (
                  <span style={{color: r.criteria_2 ? '#10b981' : '#ef4444'}}>
                    ${r.ma_50?.toFixed(2) || '--'}
                  </span>
                )}
              </td>
              
              {/* Criteria 3: 50MA > 150MA */}
              <td className={r.criteria_3 ? 'criteria-pass' : 'criteria-fail'}>
                {viewMode === 'simple' ? (
                  r.criteria_3 ? '✅' : '❌'
                ) : (
                  <span style={{color: r.criteria_3 ? '#10b981' : '#ef4444'}}>
                    ${r.ma_150?.toFixed(2) || '--'}
                  </span>
                )}
              </td>
              
              {/* Criteria 4: 150MA > 200MA */}
              <td className={r.criteria_4 ? 'criteria-pass' : 'criteria-fail'}>
                {viewMode === 'simple' ? (
                  r.criteria_4 ? '✅' : '❌'
                ) : (
                  <span style={{color: r.criteria_4 ? '#10b981' : '#ef4444'}}>
                    ${r.ma_200?.toFixed(2) || '--'}
                  </span>
                )}
              </td>
              
              {/* Criteria 5: 200MA Trending Up */}
              <td className={r.criteria_5 ? 'criteria-pass' : 'criteria-fail'}>
                {viewMode === 'simple' ? (
                  r.criteria_5 ? '✅' : '❌'
                ) : (
                  <span style={{color: r.criteria_5 ? '#10b981' : '#ef4444'}}>
                    ${r.ma_200_1m_ago?.toFixed(2) || '--'}
                  </span>
                )}
              </td>
              
              {/* Criteria 6: >30% above 52W Low */}
              <td className={r.criteria_6 ? 'criteria-pass' : 'criteria-fail'}>
                {viewMode === 'simple' ? (
                  r.criteria_6 ? '✅' : '❌'
                ) : (
                  <span style={{color: r.criteria_6 ? '#10b981' : '#ef4444'}}>
                    {r.week_52_low && r.price
                      ? (((r.price - r.week_52_low) / r.week_52_low * 100).toFixed(1) + '%')
                      : '--'
                    }
                  </span>
                )}
              </td>
              
              {/* Criteria 7: Volume > Avg */}
              <td className={r.criteria_7 ? 'criteria-pass' : 'criteria-fail'}>
                {viewMode === 'simple' ? (
                  r.criteria_7 ? '✅' : '❌'
                ) : (
                  <span style={{color: r.criteria_7 ? '#10b981' : '#ef4444'}}>
                    {r.avg_volume_50 ? (r.avg_volume_50 / 1000).toFixed(0) + 'K' : '--'}
                  </span>
                )}
              </td>
              
              {/* Criteria 8: SPY > 50MA */}
              <td className={r.criteria_8 ? 'criteria-pass' : 'criteria-fail'}>
                {viewMode === 'simple' ? (
                  r.criteria_8 ? '✅' : '❌'
                ) : (
                  <span style={{color: r.criteria_8 ? '#10b981' : '#ef4444'}}>
                    {r.criteria_8 ? 'PASS' : 'FAIL'}
                  </span>
                )}
              </td>
              
              <td className={r.qualified ? 'criteria-pass' : 'criteria-fail'}>
                {r.qualified ? '✅ YES' : '❌ NO'}
              </td>
              
              <td>
                {r.qualified ? (
                  <span className="action-buy">✅ BUYING</span>
                ) : (
                  <span className="action-pass">⛔ SKIP</span>
                )}
              </td>
              
              <td style={{textAlign: 'center'}}>
                <input 
                  type="checkbox"
                  checked={r.override || false}
                  onChange={(e) => onOverrideToggle(r.symbol, e.target.checked)}
                  style={{
                    width: '18px',
                    height: '18px',
                    cursor: 'pointer'
                  }}
                  title={r.qualified ? "Check to SKIP buying this stock" : "Check to mark as overridden"}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {filteredResults.length === 0 && (
        <div style={{ textAlign: 'center', padding: '3rem', color: '#6b7280' }}>
          No results yet. Start the scanner to see data.
        </div>
      )}
    </div>
  );
}

export default ScannerTable;
