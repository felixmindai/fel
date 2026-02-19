"""
Minervini Trading Bot - FastAPI Backend
========================================

RESTful API and WebSocket server for the Minervini momentum scanner.

Endpoints:
- Scanner control and results
- Position management
- Ticker management
- Configuration
- Real-time WebSocket updates
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime, date
from decimal import Decimal
import asyncio
import logging
import json

from database import Database
from data_fetcher import DataFetcher, AsyncDataFetcher
from scanner import MinerviniScanner, PositionMonitor
from data_updater import data_update_scheduler_loop, run_data_update, market_open_scheduler_loop
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")  # all date logic uses ET, not machine local

# Custom JSON encoder for handling special types
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        return super().default(obj)

# Helper function to convert Decimal to float for JSON serialization
def convert_decimals(obj):
    """Recursively convert Decimal objects and other non-JSON types to JSON-serializable formats."""
    import math
    if obj is None:
        return None
    elif isinstance(obj, Decimal):
        v = float(obj)
        # Guard against nan/inf produced by Decimal arithmetic
        return None if (math.isnan(v) or math.isinf(v)) else v
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, bool):
        return obj
    elif isinstance(obj, float):
        # nan and inf are not JSON-compliant — return None so the response serialises cleanly
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    elif isinstance(obj, (int, str)):
        return obj
    elif hasattr(obj, '__dict__'):
        # Handle objects with __dict__ (like database row objects)
        return convert_decimals(obj.__dict__)
    else:
        # For any other type, try to convert to string as last resort
        try:
            return str(obj)
        except:
            logger.warning(f"Could not serialize object of type {type(obj)}: {obj}")
            return None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class TickerAdd(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None

class ConfigUpdate(BaseModel):
    # Trading parameters
    stop_loss_pct: Optional[float] = None
    max_positions: Optional[int] = None
    position_size_usd: Optional[float] = None
    paper_trading: Optional[bool] = None
    auto_execute: Optional[bool] = None
    default_entry_method: Optional[str] = None
    data_update_time: Optional[str] = None
    order_execution_time: Optional[str] = None
    # Buy qualification criteria thresholds
    near_52wh_pct: Optional[float] = None
    above_52wl_pct: Optional[float] = None
    volume_multiplier: Optional[float] = None
    spy_filter_enabled: Optional[bool] = None
    limit_order_premium_pct: Optional[float] = None
    # Sell qualification
    trend_break_exit_enabled: Optional[bool] = None
    # Scanner scheduler
    scanner_interval_seconds: Optional[int] = None

class PositionCreate(BaseModel):
    symbol: str
    quantity: int
    entry_price: float

# ============================================================================
# GLOBAL STATE
# ============================================================================

class BotState:
    """Global bot state."""
    def __init__(self):
        self.db = Database()
        # Use a single DataFetcher instance shared by both the sync scanner/monitor
        # and the async wrapper. This ensures that connecting via async_fetcher
        # is immediately visible to the scanner (self.fetcher.connected == True).
        self.fetcher = DataFetcher()
        self.async_fetcher = AsyncDataFetcher(self.fetcher)
        self.scanner = MinerviniScanner(self.db, self.fetcher)
        self.monitor = PositionMonitor(self.db, self.fetcher)
        self.scanner_running = False
        self.scanner_task = None
        self.data_updater_task = None
        self.market_open_task = None
        self.latest_results = []
        self.websocket_clients = set()
        self.ib_connected = False
        self.execution_running = False        # True while run_order_execution is in progress
        self.last_execution: dict | None = None  # Summary of the most recent execution run

bot_state = BotState()

# ============================================================================
# SCANNER BACKGROUND TASK
# ============================================================================

def _seconds_until_market_open() -> float:
    """
    Return the number of seconds until the next regular market open (09:30 ET,
    Mon-Fri). Returns 0 if the market is currently open.
    """
    from scanner import MinerviniScanner
    from zoneinfo import ZoneInfo
    from datetime import time as dtime, timedelta
    _ET = ZoneInfo("America/New_York")
    now = datetime.now(_ET)

    if MinerviniScanner._market_is_open():
        return 0.0

    # Walk forward day by day until we find the next weekday
    candidate = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:          # skip Saturday (5) and Sunday (6)
        candidate += timedelta(days=1)

    return (candidate - now).total_seconds()


async def scanner_loop():
    """
    Background task that runs the scanner during market hours only.

    Behaviour:
      • Market OPEN  → scan every N seconds (configured interval), check exits.
      • Market CLOSED → log once and sleep until 09:30 ET next trading day.
        No DB queries, no IB calls, no wasted cycles overnight / weekends.
    """
    from scanner import MinerviniScanner
    logger.info("🚀 Scanner loop started")

    while bot_state.scanner_running:
        try:
            # ── Off-hours gate ────────────────────────────────────────────
            secs = _seconds_until_market_open()
            if secs > 0:
                from datetime import timedelta
                _ET = ET
                wake = datetime.now(_ET) + timedelta(seconds=secs)
                wake_str = wake.strftime('%a %b %d %I:%M %p ET').replace(' 0', ' ')
                hrs  = int(secs // 3600)
                mins = int((secs % 3600) // 60)
                logger.info(
                    f"🌙 Market closed — scanner sleeping {hrs}h {mins}m "
                    f"until {wake_str}"
                )
                # Sleep in short chunks so Stop Scanner works immediately
                slept = 0.0
                while slept < secs and bot_state.scanner_running:
                    chunk = min(60.0, secs - slept)
                    await asyncio.sleep(chunk)
                    slept += chunk
                    # Re-check: DST change or manual start could shift the gate
                    if MinerviniScanner._market_is_open():
                        break
                continue   # re-enter loop top — market may now be open

            # ── Market is open: run scan + exit-trigger check ─────────────
            loop = asyncio.get_running_loop()

            logger.info("🔍 Running scanner...")
            try:
                results = await asyncio.wait_for(
                    loop.run_in_executor(None, bot_state.scanner.scan_all_tickers),
                    timeout=120.0
                )
            except asyncio.TimeoutError:
                logger.error("❌ scan_all_tickers timed out after 120s — skipping this cycle")
                results = bot_state.latest_results  # keep last known results
            bot_state.latest_results = results
            await broadcast_scan_results(results)

            logger.info("🔍 Checking position exit triggers...")
            try:
                exits = await asyncio.wait_for(
                    loop.run_in_executor(None, bot_state.monitor.check_exit_triggers),
                    timeout=60.0
                )
            except asyncio.TimeoutError:
                logger.error("❌ check_exit_triggers timed out after 60s — skipping")
                exits = []
            if exits:
                logger.warning(f"⚠️ {len(exits)} position(s) need to exit")
                await broadcast_exit_triggers(exits)

            # Read interval dynamically so UI changes take effect without restart
            _cfg      = bot_state.db.get_config()
            _interval = int(_cfg.get('scanner_interval_seconds') or 30)
            logger.info(f"⏱  Scan cycle done — sleeping {_interval}s")
            await asyncio.sleep(_interval)

        except Exception as e:
            logger.error(f"❌ Scanner loop error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await asyncio.sleep(10)

    logger.info("🛑 Scanner loop stopped")

async def broadcast_scan_results(results: List[Dict]):
    """Broadcast scan results to all WebSocket clients."""
    if not bot_state.websocket_clients:
        return
    
    # Convert Decimals to floats
    results_clean = convert_decimals(results)
    
    message = {
        'type': 'scan_results',
        'timestamp': datetime.now().isoformat(),
        'results': results_clean
    }
    
    # Remove disconnected clients
    disconnected = []
    for client in bot_state.websocket_clients:
        try:
            await client.send_json(message)
        except Exception:
            disconnected.append(client)

    for client in disconnected:
        bot_state.websocket_clients.discard(client)

async def broadcast_exit_triggers(exits: List[Dict]):
    """Broadcast exit triggers to all WebSocket clients."""
    if not bot_state.websocket_clients:
        return
    
    # Convert Decimals to floats
    exits_clean = convert_decimals(exits)
    
    message = {
        'type': 'exit_triggers',
        'timestamp': datetime.now().isoformat(),
        'exits': exits_clean
    }
    
    disconnected = []
    for client in bot_state.websocket_clients:
        try:
            await client.send_json(message)
        except Exception:
            disconnected.append(client)

    for client in disconnected:
        bot_state.websocket_clients.discard(client)

async def broadcast_message(message: dict):
    """Broadcast an arbitrary message to all WebSocket clients."""
    if not bot_state.websocket_clients:
        return
    disconnected = []
    for client in bot_state.websocket_clients:
        try:
            await client.send_json(message)
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        bot_state.websocket_clients.discard(client)

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Minervini Trading Bot API",
    description="Momentum scanner and portfolio manager using Minervini's SEPA methodology",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# STARTUP / SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    logger.info("🚀 Starting Minervini Trading Bot API...")
    
    # Create tables
    bot_state.db.create_tables()
    
    # Connect to IB
    connected = await bot_state.async_fetcher.connect()
    if connected:
        bot_state.ib_connected = True
        logger.info("✅ Connected to Interactive Brokers")
    else:
        logger.warning("⚠️ Could not connect to IB - some features may be limited")

    # Start the scheduled data-update background task
    bot_state.data_updater_task = asyncio.create_task(
        data_update_scheduler_loop(bot_state)
    )

    # Start the market-open order execution scheduler
    bot_state.market_open_task = asyncio.create_task(
        market_open_scheduler_loop(bot_state)
    )

    # Auto-start the scanner — always runs unless manually stopped via Settings
    bot_state.scanner_running = True
    bot_state.db.set_scanner_status(True)
    bot_state.scanner_task = asyncio.create_task(scanner_loop())
    logger.info("✅ Scanner auto-started on startup")

    logger.info("✅ Bot API ready")

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    logger.info("🛑 Shutting down...")
    
    # Stop scanner
    if bot_state.scanner_running:
        bot_state.scanner_running = False
        if bot_state.scanner_task:
            bot_state.scanner_task.cancel()

    # Stop data updater scheduler
    if bot_state.data_updater_task:
        bot_state.data_updater_task.cancel()

    # Stop market-open order execution scheduler
    if bot_state.market_open_task:
        bot_state.market_open_task.cancel()

    # Disconnect from IB
    await bot_state.async_fetcher.disconnect()
    
    logger.info("✅ Shutdown complete")

# ============================================================================
# STATUS & INFO
# ============================================================================

@app.get("/")
async def root():
    """API root."""
    return {
        "name": "Minervini Trading Bot API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/api/version")
async def get_version():
    """Get backend version info."""
    return {
        "version": "3.0-MANUAL-JSON",
        "features": {
            "websocket": "Manual JSON serialization",
            "api": "Direct connection mode",
            "database": "PostgreSQL with Decimal conversion"
        },
        "timestamp": datetime.now().isoformat()
    }

async def _get_status_dict() -> dict:
    """Return current bot status as a plain dict (used by both the REST endpoint
    and the WebSocket loop — avoids calling the FastAPI route handler directly,
    which would return a Response object instead of a dict)."""
    config = bot_state.db.get_config()
    positions = bot_state.db.get_positions()
    stats = bot_state.db.get_statistics()
    return convert_decimals({
        "scanner_running": bot_state.scanner_running,
        "ib_connected": bot_state.fetcher.connected,
        "active_tickers": len(bot_state.db.get_active_tickers()),
        "open_positions": len(positions),
        "config": config,
        "statistics": stats,
        "last_scan": len(bot_state.latest_results)
    })

@app.get("/api/status")
async def get_status():
    """Get bot status."""
    return await _get_status_dict()

# ============================================================================
# SCANNER ENDPOINTS
# ============================================================================

@app.post("/api/scanner/start")
async def start_scanner():
    """Start the scanner."""
    if bot_state.scanner_running:
        raise HTTPException(status_code=400, detail="Scanner already running")
    
    # Connect to IB if not already connected
    if not bot_state.fetcher.connected:
        connected = await bot_state.async_fetcher.connect()
        if connected:
            bot_state.ib_connected = True
        else:
            # Allow scanner to start anyway — it will use DB prices as fallback
            logger.warning("⚠️ Could not connect to IB — scanner will use DB closing prices")

    bot_state.scanner_running = True
    bot_state.db.set_scanner_status(True)
    
    # Start scanner loop
    bot_state.scanner_task = asyncio.create_task(scanner_loop())
    
    logger.info("✅ Scanner started")
    
    return {"success": True, "message": "Scanner started"}

@app.post("/api/scanner/stop")
async def stop_scanner():
    """Stop the scanner."""
    if not bot_state.scanner_running:
        raise HTTPException(status_code=400, detail="Scanner not running")
    
    bot_state.scanner_running = False
    bot_state.db.set_scanner_status(False)
    
    if bot_state.scanner_task:
        bot_state.scanner_task.cancel()
    
    logger.info("🛑 Scanner stopped")
    
    return {"success": True, "message": "Scanner stopped"}

@app.get("/api/scanner/results")
async def get_scan_results():
    """Get latest scan results."""
    # Try to get from database first
    results = bot_state.db.get_latest_scan_results()
    
    if not results:
        results = bot_state.latest_results
    
    # Convert Decimals to floats
    return convert_decimals({
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "qualified_count": sum(1 for r in results if r.get('qualified', False))
    })

@app.post("/api/scanner/override/{symbol}")
async def update_override(symbol: str, override: bool):
    """Update override status for a symbol in today's scan results."""
    try:
        success = bot_state.db.update_scan_override(symbol, override)
        if success:
            return {"success": True, "symbol": symbol, "override": override}
        else:
            raise HTTPException(status_code=404, detail=f"No scan result found for {symbol} today")
    except Exception as e:
        logger.error(f"Error updating override for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scanner/entry-method/{symbol}")
async def update_entry_method(symbol: str, entry_method: str):
    """Update entry method for a symbol in today's scan results."""
    try:
        # Validate entry method
        valid_methods = ['prev_close', 'market_open', 'limit_1pct']
        if entry_method not in valid_methods:
            raise HTTPException(status_code=400, detail=f"Invalid entry method. Must be one of: {valid_methods}")
        
        success = bot_state.db.update_scan_entry_method(symbol, entry_method)
        if success:
            return {"success": True, "symbol": symbol, "entry_method": entry_method}
        else:
            raise HTTPException(status_code=404, detail=f"No scan result found for {symbol} today")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating entry method for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scanner/entry-method/{symbol}/reset")
async def reset_entry_method(symbol: str):
    """Reset entry method to use default from config."""
    try:
        # Set to NULL in database (will use default)
        success = bot_state.db.update_scan_entry_method(symbol, None)
        if success:
            return {"success": True, "symbol": symbol, "entry_method": "default"}
        else:
            raise HTTPException(status_code=404, detail=f"No scan result found for {symbol} today")
    except Exception as e:
        logger.error(f"Error resetting entry method for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scanner/run-once")
async def run_scanner_once():
    """Run scanner once manually."""
    if bot_state.scanner_running:
        raise HTTPException(status_code=400, detail="Scanner already running continuously")
    
    # Connect if needed
    if not bot_state.fetcher.connected:
        connected = await bot_state.async_fetcher.connect()
        if not connected:
            raise HTTPException(status_code=503, detail="Could not connect to IB")
    
    # Run scanner
    results = await asyncio.get_event_loop().run_in_executor(
        None,
        bot_state.scanner.scan_all_tickers
    )
    
    bot_state.latest_results = results
    
    return {
        "success": True,
        "results": results,
        "qualified_count": sum(1 for r in results if r.get('qualified', False))
    }

# ============================================================================
# TICKER MANAGEMENT
# ============================================================================

@app.get("/api/tickers")
async def get_tickers():
    """Get all tickers."""
    tickers = bot_state.db.get_all_tickers()
    return {"tickers": tickers}

@app.post("/api/tickers")
async def add_ticker(ticker: TickerAdd):
    """Add a new ticker."""
    success = bot_state.db.add_ticker(ticker.symbol, ticker.name, ticker.sector)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add ticker")
    
    return {"success": True, "message": f"Added ticker {ticker.symbol}"}

@app.delete("/api/tickers/{symbol}")
async def remove_ticker(symbol: str):
    """Remove a ticker."""
    success = bot_state.db.remove_ticker(symbol)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to remove ticker")
    
    return {"success": True, "message": f"Removed ticker {symbol}"}

# ============================================================================
# POSITION MANAGEMENT
# ============================================================================

@app.get("/api/positions")
async def get_positions():
    """Get all open positions with current prices fetched in a single batch call."""
    import math
    positions = bot_state.db.get_positions()

    if positions and bot_state.fetcher.connected:
        # Batch-fetch all prices in one round-trip (much faster than one-by-one)
        symbols = [pos['symbol'] for pos in positions]
        try:
            loop = asyncio.get_running_loop()
            live_prices = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: bot_state.fetcher.fetch_multiple_prices(symbols)
                ),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.warning("⏱ Position price fetch timed out — returning positions without live prices")
            live_prices = {}
        except Exception as e:
            logger.warning(f"Batch price fetch failed for positions: {e}")
            live_prices = {}

        for pos in positions:
            raw = live_prices.get(pos['symbol'])
            if raw:
                raw = float(raw)
                if math.isnan(raw) or math.isinf(raw) or raw <= 0:
                    raw = None
            current_price = raw
            if current_price:
                cost_basis = float(pos['cost_basis'])
                pos['current_price'] = current_price
                pos['current_value'] = current_price * float(pos['quantity'])
                pos['pnl'] = pos['current_value'] - cost_basis
                pos['pnl_pct'] = (pos['pnl'] / cost_basis) * 100 if cost_basis else 0

    # Convert Decimals to floats
    return convert_decimals({"positions": positions, "count": len(positions)})

@app.post("/api/positions")
async def create_position(position: PositionCreate):
    """Create a new position (for paper trading)."""
    config = bot_state.db.get_config()
    
    # Check max positions
    current_positions = len(bot_state.db.get_positions())
    if current_positions >= config['max_positions']:
        raise HTTPException(status_code=400, detail="Maximum positions reached")
    
    # Calculate stop loss
    stop_loss = position.entry_price * (1 - config['stop_loss_pct'] / 100)
    cost_basis = position.entry_price * position.quantity
    
    # Create trade record
    trade = {
        'symbol': position.symbol,
        'entry_date': datetime.now(ET).date(),
        'entry_price': position.entry_price,
        'quantity': position.quantity,
        'cost_basis': cost_basis
    }
    
    trade_id = bot_state.db.create_trade(trade)
    
    # Create position record
    pos = {
        'symbol': position.symbol,
        'entry_date': datetime.now(ET).date(),
        'entry_price': position.entry_price,
        'quantity': position.quantity,
        'stop_loss': stop_loss,
        'cost_basis': cost_basis,
        'trade_id': trade_id
    }
    
    success = bot_state.db.save_position(pos)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create position")
    
    logger.info(f"✅ Created position: {position.symbol} x{position.quantity} @ ${position.entry_price}")
    
    return {"success": True, "position": pos}

@app.delete("/api/positions/{symbol}")
async def close_position(symbol: str, exit_price: Optional[float] = None):
    """Close a position."""
    positions = bot_state.db.get_positions()
    position = next((p for p in positions if p['symbol'] == symbol), None)
    
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    # Get exit price — prefer caller-supplied price (avoids a blocking IB fetch).
    # If not supplied, fetch from IB with a timeout. Never fall back to stale
    # DB prices — using a wrong price could silently misrecord P&L.
    if not exit_price:
        try:
            loop = asyncio.get_running_loop()
            exit_price = await asyncio.wait_for(
                loop.run_in_executor(None, bot_state.fetcher.fetch_current_price, symbol),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=503, detail=f"IB price fetch timed out for {symbol} — please retry")
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Could not fetch live price for {symbol}: {e}")
    if not exit_price:
        raise HTTPException(status_code=503, detail=f"IB returned no price for {symbol} — please retry")
    
    # Calculate P&L — cast Decimal DB fields to float to avoid TypeError
    cost_basis = float(position['cost_basis'])
    proceeds   = exit_price * float(position['quantity'])
    pnl        = proceeds - cost_basis
    pnl_pct    = (pnl / cost_basis) * 100
    
    # Close trade
    bot_state.db.close_trade(
        position['trade_id'],
        datetime.now(ET).date(),
        exit_price,
        proceeds,
        pnl,
        pnl_pct,
        'MANUAL_CLOSE'
    )
    
    # Close position
    bot_state.db.close_position(symbol)

    logger.info(f"✅ Closed position: {symbol} | P&L: ${pnl:.2f} ({pnl_pct:.2f}%)")

    # Broadcast to all WS clients so every open browser tab refreshes immediately
    await broadcast_message({
        'type': 'orders_executed',
        'timestamp': datetime.now().isoformat(),
        'buys': 0,
        'exits': 1,
        'source': 'manual_close',
        'symbol': symbol
    })

    return {
        "success": True,
        "exit_price": exit_price,
        "pnl": pnl,
        "pnl_pct": pnl_pct
    }

# ============================================================================
# TRADE HISTORY
# ============================================================================

@app.get("/api/trades")
async def get_trades(status: Optional[str] = None, limit: int = 100):
    """Get trade history."""
    trades = bot_state.db.get_trades(status=status, limit=limit)
    return convert_decimals({"trades": trades})

# ============================================================================
# CONFIGURATION
# ============================================================================

@app.get("/api/config")
async def get_config():
    """Get bot configuration."""
    config = bot_state.db.get_config()
    return convert_decimals({"config": config})

@app.put("/api/config")
async def update_config(config: ConfigUpdate):
    """Update bot configuration."""
    current_config = bot_state.db.get_config()
    
    # Update only provided fields
    updated_config = {
        'stop_loss_pct': config.stop_loss_pct if config.stop_loss_pct is not None else current_config['stop_loss_pct'],
        'max_positions': config.max_positions if config.max_positions is not None else current_config['max_positions'],
        'position_size_usd': config.position_size_usd if config.position_size_usd is not None else current_config['position_size_usd'],
        'paper_trading': config.paper_trading if config.paper_trading is not None else current_config['paper_trading'],
        'auto_execute': config.auto_execute if config.auto_execute is not None else current_config['auto_execute'],
        'default_entry_method': config.default_entry_method if config.default_entry_method is not None else current_config.get('default_entry_method', 'prev_close'),
        'data_update_time': config.data_update_time if config.data_update_time is not None else current_config.get('data_update_time'),
        'order_execution_time': config.order_execution_time if config.order_execution_time is not None else current_config.get('order_execution_time'),
        'near_52wh_pct': config.near_52wh_pct if config.near_52wh_pct is not None else current_config.get('near_52wh_pct', 5.0),
        'above_52wl_pct': config.above_52wl_pct if config.above_52wl_pct is not None else current_config.get('above_52wl_pct', 30.0),
        'volume_multiplier': config.volume_multiplier if config.volume_multiplier is not None else current_config.get('volume_multiplier', 1.5),
        'spy_filter_enabled': config.spy_filter_enabled if config.spy_filter_enabled is not None else current_config.get('spy_filter_enabled', True),
        'trend_break_exit_enabled': config.trend_break_exit_enabled if config.trend_break_exit_enabled is not None else current_config.get('trend_break_exit_enabled', True),
        'limit_order_premium_pct': config.limit_order_premium_pct if config.limit_order_premium_pct is not None else current_config.get('limit_order_premium_pct', 1.0),
        'scanner_interval_seconds': max(5, config.scanner_interval_seconds) if config.scanner_interval_seconds is not None else current_config.get('scanner_interval_seconds', 30),
    }
    
    success = bot_state.db.update_config(updated_config)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")

    logger.info("✅ Configuration updated")

    return {"success": True, "config": updated_config}

# ============================================================================
# DATA UPDATE ENDPOINTS
# ============================================================================

@app.post("/api/data/update")
async def trigger_data_update():
    """Manually trigger a data update (fire-and-forget)."""
    status = bot_state.db.get_data_update_status()
    if status.get('data_update_status') == 'running':
        raise HTTPException(status_code=409, detail="Data update already in progress")

    asyncio.create_task(run_data_update(bot_state))
    return {"success": True, "message": "Data update started"}


@app.get("/api/data/status")
async def get_data_update_status():
    """Get current data update status."""
    return convert_decimals(bot_state.db.get_data_update_status())


@app.post("/api/orders/execute-now")
async def execute_orders_now():
    """Manually trigger order execution immediately (buy + exit), bypassing the scheduler."""
    from order_executor import run_order_execution
    config = bot_state.db.get_config()
    if not config.get("auto_execute"):
        raise HTTPException(status_code=400, detail="Auto-execute is OFF — enable it in Settings first")
    asyncio.create_task(run_order_execution(bot_state))
    return {"success": True, "message": "Order execution started"}


# ============================================================================
# WEBSOCKET
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    try:
        await websocket.accept()
        bot_state.websocket_clients.add(websocket)
        logger.info(f"✅ WebSocket client connected (total: {len(bot_state.websocket_clients)}) [v3.0-MANUAL-JSON]")
        
        # Main loop - send updates every 2 seconds
        while True:
            try:
                # Get fresh status using the plain dict helper (not the route handler)
                status = await _get_status_dict()
                
                # Build message in the structure frontend expects: { type: 'status', data: {...} }
                message = {
                    "type": "status",
                    "data": {
                        "scanner_running": bool(bot_state.scanner_running),
                        "ib_connected": bool(bot_state.fetcher.connected),
                        "active_tickers": int(status.get('active_tickers') or 0),
                        "open_positions": int(status.get('open_positions') or 0),
                        "last_scan": int(status.get('last_scan') or 0),
                        "execution_running": bool(bot_state.execution_running),
                        "last_execution": bot_state.last_execution,
                    }
                }
                
                # Add config if available
                if status.get('config'):
                    config = status['config']
                    message["data"]["config"] = {
                        "stop_loss_pct": float(config.get('stop_loss_pct') or 8.0),
                        "max_positions": int(config.get('max_positions') or 16),
                        "position_size_usd": float(config.get('position_size_usd') or 10000),
                        "paper_trading": bool(config.get('paper_trading', True)),
                        "auto_execute": bool(config.get('auto_execute', False)),
                        "order_execution_time": config.get('order_execution_time')
                    }
                
                # Add statistics if available
                if status.get('statistics'):
                    stats = status['statistics']
                    message["data"]["statistics"] = {
                        "total_trades": int(stats.get('total_trades') or 0),
                        "wins": int(stats.get('wins') or 0),
                        "losses": int(stats.get('losses') or 0),
                        "win_rate": float(stats.get('win_rate') or 0.0),
                        "total_pnl": float(stats.get('total_pnl') or 0.0)
                    }

                # Add data update status
                try:
                    du = convert_decimals(bot_state.db.get_data_update_status())
                    message["data"]["data_update"] = {
                        "last_update": du.get('last_data_update'),
                        "status": du.get('data_update_status', 'idle'),
                        "error": du.get('data_update_error')
                    }
                except Exception:
                    pass  # non-critical — don't break the WS loop

                # Send using manual JSON encoding to catch serialization errors
                try:
                    json_string = json.dumps(message, cls=CustomJSONEncoder)
                    await websocket.send_text(json_string)
                except TypeError as json_err:
                    logger.error(f"JSON serialization error: {json_err}")
                    logger.error(f"Problematic message: {message}")
                    # Send minimal fallback
                    try:
                        fallback = json.dumps({
                            "type": "status",
                            "data": {
                                "scanner_running": bool(bot_state.scanner_running),
                                "ib_connected": bool(bot_state.fetcher.connected)
                            }
                        })
                        await websocket.send_text(fallback)
                    except:
                        break  # Connection dead, exit loop
                except (ConnectionError, ConnectionAbortedError, ConnectionResetError) as conn_err:
                    logger.debug(f"WebSocket connection error (client likely disconnected): {conn_err}")
                    break  # Exit loop cleanly
                except Exception as send_err:
                    logger.error(f"Unexpected error sending WebSocket message: {send_err}")
                    break
                
            except Exception as e:
                logger.error(f"Error sending status: {e}")
                import traceback
                logger.error(traceback.format_exc())
                break
            
            await asyncio.sleep(2)
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        bot_state.websocket_clients.discard(websocket)
        logger.info(f"WebSocket cleanup (remaining: {len(bot_state.websocket_clients)})")

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*80)
    print("🚀 MINERVINI TRADING BOT - BACKEND v3.0-MANUAL-JSON")
    print("="*80)
    print("✅ WebSocket: Manual JSON serialization with error handling")
    print("✅ API: Direct connection mode (no proxy)")
    print("✅ Database: PostgreSQL with Decimal conversion")
    print("="*80 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
