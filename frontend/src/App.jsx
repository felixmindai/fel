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

// ─── Market status helpers (ET-aware) ────────────────────────────────────────
function _getMarketStatus() {
  const now = new Date();
  const et  = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const day  = et.getDay();
  const mins = et.getHours() * 60 + et.getMinutes();
  const open = 9 * 60 + 30, close = 16 * 60;
  if (day === 0 || day === 6) return { open: false, label: 'weekend' };
  if (mins < open)  return { open: false, label: 'pre-market',  nextOpen: _nextOpenStr(et, open) };
  if (mins >= close) return { open: false, label: 'after-hours', nextOpen: _nextOpenStr(et, open) };
  return { open: true, label: 'open' };
}
function _nextOpenStr(etNow, openMins) {
  const d = new Date(etNow);
  d.setHours(Math.floor(openMins / 60), openMins % 60, 0, 0);
  if (d <= etNow) d.setDate(d.getDate() + 1);
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
  return d.toLocaleString('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit' });
}

// ─── Scanner status bar (lives in tab nav, always visible) ───────────────────
function ScannerStatusBar({ scannerRunning, lastUpdated }) {
  const [, setTick] = React.useState(0);
  React.useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const mkt     = _getMarketStatus();
  const secsAgo = lastUpdated ? Math.floor((new Date() - lastUpdated) / 1000) : null;
  const agoStr  = secsAgo == null ? null
    : secsAgo < 60   ? `${secsAgo}s ago`
    : secsAgo < 3600 ? `${Math.floor(secsAgo / 60)}m ago`
    : `${Math.floor(secsAgo / 3600)}h ago`;
  const lastScanStr = lastUpdated
    ? lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null;

  let icon, mainColor, mainText, subText;

  if (!scannerRunning) {
    icon = '⏹'; mainColor = '#ef4444'; mainText = 'Scanner Stopped';
    subText = lastScanStr ? ` — Last scan: ${lastScanStr} (${agoStr})` : '';
  } else if (mkt.open) {
    const liveSec = lastUpdated
      ? lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : null;
    icon = '🟢'; mainColor = '#10b981'; mainText = 'Market Open';
    subText = liveSec ? ` — Last scan: ${liveSec} (${agoStr})` : '';
  } else {
    const icons  = { weekend: '📅', 'pre-market': '🌅', 'after-hours': '🌙' };
    const labels = { weekend: 'Closed (Weekend)', 'pre-market': 'Pre-Market', 'after-hours': 'After Hours' };
    icon = icons[mkt.label]; mainColor = mkt.label === 'pre-market' ? '#f59e0b' : '#6b7280';
    mainText = labels[mkt.label];
    subText  = mkt.nextOpen ? ` — Resumes ${mkt.nextOpen} ET` : '';
  }

  return (
    <div style={{ marginLeft: 'auto', fontSize: '12px', fontWeight: '500', whiteSpace: 'nowrap', paddingRight: '0.5rem', display: 'flex', alignItems: 'center' }}>
      <span style={{ color: mainColor }}>{icon} {mainText}</span>
      <span style={{ color: '#4b5563', fontWeight: '400' }}>{subText}</span>
    </div>
  );
}

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

  const [lastScanUpdate, setLastScanUpdate] = useState(null);
  const [dataUpdateStatus, setDataUpdateStatus] = useState(null);

  // Fetch functions defined before WebSocket so they are in scope for the WS message handler
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
        // Sync data_update state from piggyback field so UI survives WS reconnects
        if (data.data?.data_update) {
          setDataUpdateStatus(prev => ({
            ...(prev || {}),
            ...data.data.data_update
          }));
        }
      } else if (data.type === 'scan_results') {
        setScanResults(data.results || []);
        setLastScanUpdate(new Date());
      } else if (data.type === 'orders_executed') {
        // Buys or exits were just executed — refresh positions immediately
        fetchPositions();
        fetchStatus();
      } else if (data.type === 'exit_triggers') {
        console.warn('🛑 Exit triggers:', data.exits);
      } else if (data.type === 'data_update_started') {
        setDataUpdateStatus({ status: 'running', total: data.data?.total || 0, done: 0 });
      } else if (data.type === 'data_update_progress') {
        setDataUpdateStatus(prev => ({
          ...(prev || {}),
          status: 'running',
          done: data.data?.done || 0,
          total: data.data?.total || 0,
          current_symbol: data.data?.current_symbol
        }));
      } else if (data.type === 'data_update_complete') {
        setDataUpdateStatus(prev => ({
          ...(prev || {}),
          status: data.data?.status || 'success',
          error: data.data?.error || null,
          last_update: data.data?.status === 'success' ? new Date().toISOString() : prev?.last_update
        }));
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

  const handleStartScanner = async () => {
    try {
      const response = await fetch(`${API_BASE}/scanner/start`, { method: 'POST' });
      const data = await response.json();
      if (data.success) fetchStatus();
    } catch (error) {
      console.error('Failed to start scanner:', error.message);
    }
  };

  const handleStopScanner = async () => {
    try {
      const response = await fetch(`${API_BASE}/scanner/stop`, { method: 'POST' });
      const data = await response.json();
      if (data.success) fetchStatus();
    } catch (error) {
      console.error('Failed to stop scanner:', error.message);
    }
  };

  const handleUpdateDataNow = async () => {
    try {
      const res = await fetch(`${API_BASE}/data/update`, { method: 'POST' });
      if (res.status === 409) {
        alert('⏳ Data update already in progress');
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert('❌ Failed to start update: ' + (err.detail || res.statusText));
      }
      // Progress will arrive via WebSocket broadcasts automatically
    } catch (error) {
      alert('❌ Error starting data update: ' + error.message);
    }
  };

  const openPositionSymbols = new Set(positions.map(p => p.symbol));
  // Use DB-embedded in_portfolio flag OR live positions set — same dual-check as ScannerTable
  // so the count is correct even before positions state has loaded
  const qualifiedCount = scanResults.filter(
    r => r.qualified && !r.in_portfolio && !openPositionSymbols.has(r.symbol)
  ).length;

  // ── Reusable status indicator: coloured dot + "Label: Value" ─────────────
  const StatusDot = ({ color, label, value }) => (
    <span className={`status-indicator ${color}`}>
      <span className="dot" />
      <span className="label">{label}:</span>
      <span className="value">{value}</span>
    </span>
  );

  // Compute execute value string once
  const execValue = !wsConnected || !status ? null
    : status.execution_running ? 'Running'
    : status.last_execution?.status === 'completed'
      ? `Done — ${status.last_execution.buys}B / ${status.last_execution.exits}E @ ${new Date(status.last_execution.finished_at).toLocaleTimeString()}`
    : status.last_execution?.status === 'error'
      ? `Error @ ${new Date(status.last_execution.finished_at).toLocaleTimeString()}`
    : 'Idle';

  const execColor = !status ? 'grey'
    : status.execution_running ? 'amber'
    : status.last_execution?.status === 'completed' ? 'green'
    : status.last_execution?.status === 'error' ? 'red'
    : 'grey';

  return (
    <div className="app">
      <header className="app-header">
        <h1>📈 Minervini Momentum Scanner <span style={{fontSize: '14px', backgroundColor: '#ffeb3b', color: '#000', padding: '4px 8px', borderRadius: '4px', marginLeft: '10px', fontWeight: 'bold'}}>v2.0</span></h1>
        <div className="header-controls">

          {/* IB — only shown once WS is connected */}
          {wsConnected && status && (
            status.ib_connected
              ? <StatusDot color="green" label="IB" value="Connected" />
              : <StatusDot color="red"   label="IB" value="Disconnected" />
          )}

          {/* Scanner — 4 states:
               WS down        → red    Connecting…
               Stopped        → red    Stopped
               Running+closed → amber  Sleeping
               Running+open   → green  Running                */}
          {!wsConnected
            ? <StatusDot color="red" label="Scanner" value="Connecting…" />
            : (() => {
                if (!status?.scanner_running)
                  return <StatusDot color="red"   label="Scanner" value="Stopped" />;
                // Check if market is currently open (ET, Mon-Fri 09:30-16:00)
                const now = new Date();
                const et  = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
                const day = et.getDay();
                const mins = et.getHours() * 60 + et.getMinutes();
                const marketOpen = day >= 1 && day <= 5 && mins >= 570 && mins < 960; // 9:30–16:00
                return marketOpen
                  ? <StatusDot color="green" label="Scanner" value="Running" />
                  : <StatusDot color="amber" label="Scanner" value="Sleeping" />;
              })()
          }

          {/* Execute — only shown once WS is connected */}
          {wsConnected && status && (
            <StatusDot color={execColor} label="Execute" value={execValue} />
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
        <ScannerStatusBar
          scannerRunning={status?.scanner_running ?? false}
          lastUpdated={lastScanUpdate}
        />
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
            onOverrideToggle={handleOverrideToggle}
            onEntryMethodChange={handleEntryMethodChange}
            openPositionSymbols={openPositionSymbols}
          />
        )}
        {activeTab === 'portfolio' && (
          <PortfolioPanel
            positions={positions}
            config={config}
            onRefresh={fetchPositions}
            onStatusRefresh={fetchStatus}
          />
        )}
        {activeTab === 'tickers' && (
          <TickerManager onUpdate={fetchStatus} />
        )}
        {activeTab === 'config' && (
          <ConfigPanel
            config={config}
            onUpdate={fetchConfig}
            status={status}
            dataUpdateStatus={dataUpdateStatus}
            onUpdateDataNow={handleUpdateDataNow}
          />
        )}
      </main>

      <footer className="app-footer">
        <p>Minervini Trading Bot v1.0 | Paper Trading: {config?.paper_trading ? 'ON' : 'OFF'}</p>
      </footer>
    </div>
  );
}

export default App;
