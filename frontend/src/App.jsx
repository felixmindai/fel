import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';
import ScannerTable from './components/ScannerTable';
import PortfolioPanel from './components/PortfolioPanel';
import TickerManager from './components/TickerManager';
import ConfigPanel from './components/ConfigPanel';
import StatusBar from './components/StatusBar';
import { API_BASE, WS_URL } from './config';

// Reconnect delays: 1s, 2s, 4s, 8s, 16s, 30s (capped)
const getReconnectDelay = (attempt) => Math.min(1000 * Math.pow(2, attempt), 30000);

function App() {
  const [activeTab, setActiveTab] = useState('scanner');
  const [status, setStatus] = useState(null);
  const [scanResults, setScanResults] = useState([]);
  const [positions, setPositions] = useState([]);
  const [config, setConfig] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [overrides, setOverrides] = useState({}); // Track which stocks are overridden
  const [entryMethods, setEntryMethods] = useState({}); // Track manually set entry methods

  // Refs so reconnect logic always has latest values without stale closures
  const wsRef = useRef(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef(null);
  const unmountedRef = useRef(false);

  const handleOverrideToggle = async (symbol, checked) => {
    // Update local state immediately for responsive UI
    setOverrides(prev => ({
      ...prev,
      [symbol]: checked
    }));

    // Save to backend
    try {
      const response = await fetch(`${API_BASE}/scanner/override/${symbol}?override=${checked}`, {
        method: 'POST'
      });

      if (!response.ok) {
        console.error('Failed to save override');
        // Revert on failure
        setOverrides(prev => ({
          ...prev,
          [symbol]: !checked
        }));
      }
    } catch (error) {
      console.error('Error saving override:', error);
      // Revert on error
      setOverrides(prev => ({
        ...prev,
        [symbol]: !checked
      }));
    }
  };

  const handleEntryMethodChange = async (symbol, method) => {
    // Update local state immediately for responsive UI
    setEntryMethods(prev => ({
      ...prev,
      [symbol]: method
    }));

    // Save to backend
    try {
      const response = await fetch(`${API_BASE}/scanner/entry-method/${symbol}?entry_method=${method}`, {
        method: 'POST'
      });

      if (!response.ok) {
        console.error('Failed to save entry method');
        // Revert on failure
        setEntryMethods(prev => {
          const newState = {...prev};
          delete newState[symbol];
          return newState;
        });
      }
    } catch (error) {
      console.error('Error saving entry method:', error);
      // Revert on error
      setEntryMethods(prev => {
        const newState = {...prev};
        delete newState[symbol];
        return newState;
      });
    }
  };

  const handleResetEntryMethod = async (symbol) => {
    // Reset to default by clearing manual selection
    setEntryMethods(prev => {
      const newState = {...prev};
      delete newState[symbol];
      return newState;
    });

    // Clear in backend (set to NULL)
    try {
      const response = await fetch(`${API_BASE}/scanner/entry-method/${symbol}/reset`, {
        method: 'POST'
      });

      if (!response.ok) {
        console.error('Failed to reset entry method');
      }
    } catch (error) {
      console.error('Error resetting entry method:', error);
    }
  };

  const [lastUpdated, setLastUpdated] = useState(null);
  const [lastScanUpdate, setLastScanUpdate] = useState(null);

  // ─── WebSocket with auto-reconnect ────────────────────────────────────────
  const connectWebSocket = useCallback(() => {
    // Don't reconnect if the component has been unmounted
    if (unmountedRef.current) return;

    const attempt = reconnectAttemptRef.current;
    console.log(`📡 WS connecting (attempt ${attempt + 1}) → ${WS_URL}`);

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      if (unmountedRef.current) { ws.close(); return; }
      console.log('✅ WebSocket connected');
      setWsConnected(true);
      reconnectAttemptRef.current = 0; // reset backoff on successful connect
    };

    ws.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (parseErr) {
        console.warn('⚠️ WS message parse error — skipping frame:', parseErr);
        return;
      }

      if (data.type === 'status') {
        setStatus(data.data);
        setLastUpdated(new Date());
      } else if (data.type === 'scan_results') {
        setScanResults(data.results || []);
        setLastScanUpdate(new Date());
      } else if (data.type === 'exit_triggers') {
        console.warn('🛑 Exit triggers:', data.exits);
      }
    };

    ws.onerror = (error) => {
      // onerror always fires before onclose; log but let onclose handle reconnect
      console.error('❌ WebSocket error:', error);
    };

    ws.onclose = (event) => {
      if (unmountedRef.current) return; // component gone, don't reconnect
      setWsConnected(false);
      const delay = getReconnectDelay(reconnectAttemptRef.current);
      console.log(`🔁 WS closed (code ${event.code}). Reconnecting in ${delay / 1000}s…`);
      reconnectAttemptRef.current += 1;
      reconnectTimerRef.current = setTimeout(connectWebSocket, delay);
    };
  }, []); // stable reference — no deps needed because we use refs

  useEffect(() => {
    console.log('🚀 MINERVINI BOT v2.0 - Starting...');
    console.log(`🔗 API Base: ${API_BASE}`);
    unmountedRef.current = false;
    connectWebSocket();

    return () => {
      unmountedRef.current = true;
      clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connectWebSocket]);

  // Fetch initial data
  useEffect(() => {
    fetchStatus();
    fetchScanResults();
    fetchPositions();
    fetchConfig();
  }, []);

  const fetchStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/status`);
      const data = await response.json();
      setStatus(data);
    } catch (error) {
      console.error('Error fetching status:', error);
    }
  };

  const fetchScanResults = async () => {
    try {
      const response = await fetch(`${API_BASE}/scanner/results`);
      const data = await response.json();
      setScanResults(data.results || []);
      setLastScanUpdate(new Date());
    } catch (error) {
      console.error('Error fetching scan results:', error);
    }
  };

  const fetchPositions = async () => {
    try {
      const response = await fetch(`${API_BASE}/positions`);
      const data = await response.json();
      setPositions(data.positions || []);
    } catch (error) {
      console.error('Error fetching positions:', error);
    }
  };

  const fetchConfig = async () => {
    try {
      const response = await fetch(`${API_BASE}/config`);
      const data = await response.json();
      setConfig(data.config);
    } catch (error) {
      console.error('Error fetching config:', error);
    }
  };

  const handleStartScanner = async () => {
    try {
      const response = await fetch(`${API_BASE}/scanner/start`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        alert('✅ Scanner started!');
        fetchStatus();
      }
    } catch (error) {
      alert('❌ Failed to start scanner: ' + error.message);
    }
  };

  const handleStopScanner = async () => {
    try {
      const response = await fetch(`${API_BASE}/scanner/stop`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        alert('✅ Scanner stopped');
        fetchStatus();
      }
    } catch (error) {
      alert('❌ Failed to stop scanner: ' + error.message);
    }
  };

  const qualifiedCount = scanResults.filter(r => r.qualified).length;

  return (
    <div className="app">
      <header className="app-header">
        <h1>📈 Minervini Momentum Scanner <span style={{fontSize: '14px', backgroundColor: '#ffeb3b', color: '#000', padding: '4px 8px', borderRadius: '4px', marginLeft: '10px', fontWeight: 'bold'}}>v2.0</span></h1>
        <div className="header-controls">
          {/* WebSocket live connection indicator */}
          <span style={{
            fontSize: '12px',
            padding: '3px 8px',
            borderRadius: '4px',
            backgroundColor: wsConnected ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
            border: `1px solid ${wsConnected ? '#10b981' : '#ef4444'}`,
            color: wsConnected ? '#10b981' : '#ef4444',
            fontWeight: '600'
          }}>
            {wsConnected ? '🟢 Live' : '🔴 Reconnecting…'}
          </span>

          {status && (
            <>
              <span className={status.scanner_running ? 'status-running' : 'status-stopped'}>
                {status.scanner_running ? '🟢 SCANNING' : '⚪ STOPPED'}
              </span>
              {/* Only show IB status when WS is actually connected so it reflects real backend state */}
              {wsConnected && (
                <span className={status.ib_connected ? 'status-connected' : 'status-disconnected'}>
                  {status.ib_connected ? '✅ IB Connected' : '⚠️ IB Disconnected'}
                </span>
              )}
              {lastUpdated && (
                <span style={{fontSize: '12px', color: '#666', marginLeft: '15px'}}>
                  Status: {lastUpdated.toLocaleTimeString()}
                </span>
              )}
            </>
          )}
        </div>
      </header>

      {status && (
        <StatusBar 
          status={status}
          qualifiedCount={qualifiedCount}
          totalTickers={scanResults.length}
          lastScanUpdate={lastScanUpdate}
        />
      )}

      <div className="scanner-controls">
        {!status?.scanner_running ? (
          <button className="btn btn-primary" onClick={handleStartScanner}>
            🚀 Start Scanner
          </button>
        ) : (
          <button className="btn btn-danger" onClick={handleStopScanner}>
            🛑 Stop Scanner
          </button>
        )}
      </div>

      <nav className="tab-nav">
        <button 
          className={activeTab === 'scanner' ? 'active' : ''} 
          onClick={() => setActiveTab('scanner')}
        >
          🔍 Scanner ({qualifiedCount})
        </button>
        <button 
          className={activeTab === 'portfolio' ? 'active' : ''} 
          onClick={() => setActiveTab('portfolio')}
        >
          💼 Portfolio ({positions.length})
        </button>
        <button 
          className={activeTab === 'tickers' ? 'active' : ''} 
          onClick={() => setActiveTab('tickers')}
        >
          📋 Tickers ({status?.active_tickers || 0})
        </button>
        <button 
          className={activeTab === 'config' ? 'active' : ''} 
          onClick={() => setActiveTab('config')}
        >
          ⚙️ Settings
        </button>
      </nav>

      <main className="app-content">
        {activeTab === 'scanner' && (
          <ScannerTable 
            results={scanResults.map(r => ({
              ...r,
              override: overrides[r.symbol] || false,
              entry_method: entryMethods[r.symbol] || r.entry_method || config?.default_entry_method || 'prev_close',
              manually_set: !!entryMethods[r.symbol] || (r.entry_method && r.entry_method !== config?.default_entry_method)
            }))}
            onRefresh={fetchScanResults}
            lastUpdated={lastScanUpdate}
            onOverrideToggle={handleOverrideToggle}
            onEntryMethodChange={handleEntryMethodChange}
            defaultEntryMethod={config?.default_entry_method || 'prev_close'}
          />
        )}
        {activeTab === 'portfolio' && (
          <PortfolioPanel 
            positions={positions} 
            config={config}
            onRefresh={fetchPositions} 
          />
        )}
        {activeTab === 'tickers' && (
          <TickerManager onUpdate={fetchStatus} />
        )}
        {activeTab === 'config' && (
          <ConfigPanel config={config} onUpdate={fetchConfig} />
        )}
      </main>

      <footer className="app-footer">
        <p>Minervini Trading Bot v1.0 | Paper Trading: {config?.paper_trading ? 'ON' : 'OFF'}</p>
      </footer>
    </div>
  );
}

export default App;
