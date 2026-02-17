import React, { useState, useEffect } from 'react';
import './App.css';
import ScannerTable from './components/ScannerTable';
import PortfolioPanel from './components/PortfolioPanel';
import TickerManager from './components/TickerManager';
import ConfigPanel from './components/ConfigPanel';
import StatusBar from './components/StatusBar';

function App() {
  const [activeTab, setActiveTab] = useState('scanner');
  const [status, setStatus] = useState(null);
  const [scanResults, setScanResults] = useState([]);
  const [positions, setPositions] = useState([]);
  const [config, setConfig] = useState(null);
  const [ws, setWs] = useState(null);
  const [overrides, setOverrides] = useState({}); // Track which stocks are overridden

  const handleOverrideToggle = (symbol, checked) => {
    setOverrides(prev => ({
      ...prev,
      [symbol]: checked
    }));
  };
  const [lastUpdated, setLastUpdated] = useState(null);
  const [lastScanUpdate, setLastScanUpdate] = useState(null);

  // Connect to WebSocket
  useEffect(() => {
    console.log('🚀 MINERVINI BOT v2.0-DIRECT-CONNECT - Starting...');
    console.log('📡 Connecting to: ws://localhost:8000/ws');
    console.log('🔗 API Base: http://localhost:8000/api/');
    
    const websocket = new WebSocket('ws://localhost:8000/ws');
    
    websocket.onopen = () => {
      console.log('✅ WebSocket connected');
    };
    
    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
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
    
    websocket.onerror = (error) => {
      console.error('❌ WebSocket error:', error);
    };
    
    websocket.onclose = () => {
      console.log('WebSocket disconnected');
    };
    
    setWs(websocket);
    
    return () => {
      websocket.close();
    };
  }, []);

  // Fetch initial data
  useEffect(() => {
    fetchStatus();
    fetchScanResults();
    fetchPositions();
    fetchConfig();
  }, []);

  const fetchStatus = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/status');
      const data = await response.json();
      setStatus(data);
    } catch (error) {
      console.error('Error fetching status:', error);
    }
  };

  const fetchScanResults = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/scanner/results');
      const data = await response.json();
      setScanResults(data.results || []);
      setLastScanUpdate(new Date());
    } catch (error) {
      console.error('Error fetching scan results:', error);
    }
  };

  const fetchPositions = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/positions');
      const data = await response.json();
      setPositions(data.positions || []);
    } catch (error) {
      console.error('Error fetching positions:', error);
    }
  };

  const fetchConfig = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/config');
      const data = await response.json();
      setConfig(data.config);
    } catch (error) {
      console.error('Error fetching config:', error);
    }
  };

  const handleStartScanner = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/scanner/start', { method: 'POST' });
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
      const response = await fetch('http://localhost:8000/api/scanner/stop', { method: 'POST' });
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
        <h1>📈 Minervini Momentum Scanner <span style={{fontSize: '14px', backgroundColor: '#ffeb3b', color: '#000', padding: '4px 8px', borderRadius: '4px', marginLeft: '10px', fontWeight: 'bold'}}>v2.0-DIRECT-CONNECT</span></h1>
        <div className="header-controls">
          {status && (
            <>
              <span className={status.scanner_running ? 'status-running' : 'status-stopped'}>
                {status.scanner_running ? '🟢 SCANNING' : '⚪ STOPPED'}
              </span>
              <span className={status.ib_connected ? 'status-connected' : 'status-disconnected'}>
                {status.ib_connected ? '✅ IB Connected' : '❌ IB Disconnected'}
              </span>
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
              override: overrides[r.symbol] || false
            }))}
            onRefresh={fetchScanResults}
            lastUpdated={lastScanUpdate}
            onOverrideToggle={handleOverrideToggle}
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
