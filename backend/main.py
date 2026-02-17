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
    if obj is None:
        return None
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, bool):
        return obj
    elif isinstance(obj, (int, float, str)):
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
    stop_loss_pct: Optional[float] = None
    max_positions: Optional[int] = None
    position_size_usd: Optional[float] = None
    paper_trading: Optional[bool] = None
    auto_execute: Optional[bool] = None

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
        self.fetcher = DataFetcher()
        self.async_fetcher = AsyncDataFetcher()
        self.scanner = MinerviniScanner(self.db, self.fetcher)
        self.monitor = PositionMonitor(self.db, self.fetcher)
        self.scanner_running = False
        self.scanner_task = None
        self.latest_results = []
        self.websocket_clients = []

bot_state = BotState()

# ============================================================================
# SCANNER BACKGROUND TASK
# ============================================================================

async def scanner_loop():
    """Background task that runs the scanner continuously."""
    logger.info("🚀 Scanner loop started")
    
    while bot_state.scanner_running:
        try:
            logger.info("🔍 Running scanner...")
            
            # Run scanner in executor to avoid blocking
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                bot_state.scanner.scan_all_tickers
            )
            
            bot_state.latest_results = results
            
            # Broadcast results to WebSocket clients
            await broadcast_scan_results(results)
            
            # Check for exit triggers
            logger.info("🔍 Checking position exit triggers...")
            exits = await asyncio.get_event_loop().run_in_executor(
                None,
                bot_state.monitor.check_exit_triggers
            )
            
            if exits:
                logger.warning(f"⚠️ {len(exits)} position(s) need to exit")
                await broadcast_exit_triggers(exits)
            
            # Wait before next scan (30 seconds)
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"❌ Scanner loop error: {e}")
            await asyncio.sleep(60)  # Wait longer on error
    
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
        except:
            disconnected.append(client)
    
    for client in disconnected:
        bot_state.websocket_clients.remove(client)

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
        except:
            disconnected.append(client)
    
    for client in disconnected:
        bot_state.websocket_clients.remove(client)

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
        logger.info("✅ Connected to Interactive Brokers")
    else:
        logger.warning("⚠️ Could not connect to IB - some features may be limited")
    
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

@app.get("/api/status")
async def get_status():
    """Get bot status."""
    config = bot_state.db.get_config()
    positions = bot_state.db.get_positions()
    stats = bot_state.db.get_statistics()
    
    # Convert all Decimals to floats for JSON serialization
    return convert_decimals({
        "scanner_running": bot_state.scanner_running,
        "ib_connected": bot_state.fetcher.connected,
        "active_tickers": len(bot_state.db.get_active_tickers()),
        "open_positions": len(positions),
        "config": config,
        "statistics": stats,
        "last_scan": len(bot_state.latest_results)
    })

# ============================================================================
# SCANNER ENDPOINTS
# ============================================================================

@app.post("/api/scanner/start")
async def start_scanner():
    """Start the scanner."""
    if bot_state.scanner_running:
        raise HTTPException(status_code=400, detail="Scanner already running")
    
    # Connect to IB if not connected
    if not bot_state.fetcher.connected:
        connected = await bot_state.async_fetcher.connect()
        if not connected:
            raise HTTPException(status_code=503, detail="Could not connect to Interactive Brokers")
    
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
    """Get all open positions."""
    positions = bot_state.db.get_positions()
    
    # Enrich with current prices
    for pos in positions:
        current_price = await bot_state.async_fetcher.fetch_current_price(pos['symbol'])
        if current_price:
            pos['current_price'] = current_price
            pos['current_value'] = current_price * pos['quantity']
            pos['pnl'] = pos['current_value'] - pos['cost_basis']
            pos['pnl_pct'] = (pos['pnl'] / pos['cost_basis']) * 100
    
    # Convert Decimals to floats
    return convert_decimals({"positions": positions})

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
        'entry_date': date.today(),
        'entry_price': position.entry_price,
        'quantity': position.quantity,
        'cost_basis': cost_basis
    }
    
    trade_id = bot_state.db.create_trade(trade)
    
    # Create position record
    pos = {
        'symbol': position.symbol,
        'entry_date': date.today(),
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
    
    # Get exit price
    if not exit_price:
        exit_price = await bot_state.async_fetcher.fetch_current_price(symbol)
        if not exit_price:
            raise HTTPException(status_code=503, detail="Could not fetch current price")
    
    # Calculate P&L
    proceeds = exit_price * position['quantity']
    pnl = proceeds - position['cost_basis']
    pnl_pct = (pnl / position['cost_basis']) * 100
    
    # Close trade
    bot_state.db.close_trade(
        position['trade_id'],
        date.today(),
        exit_price,
        proceeds,
        pnl,
        pnl_pct,
        'MANUAL_CLOSE'
    )
    
    # Close position
    bot_state.db.close_position(symbol)
    
    logger.info(f"✅ Closed position: {symbol} | P&L: ${pnl:.2f} ({pnl_pct:.2f}%)")
    
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
        'auto_execute': config.auto_execute if config.auto_execute is not None else current_config['auto_execute']
    }
    
    success = bot_state.db.update_config(updated_config)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")
    
    logger.info("✅ Configuration updated")
    
    return {"success": True, "config": updated_config}

# ============================================================================
# WEBSOCKET
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    try:
        await websocket.accept()
        bot_state.websocket_clients.append(websocket)
        logger.info(f"✅ WebSocket client connected (total: {len(bot_state.websocket_clients)}) [v3.0-MANUAL-JSON]")
        
        # Main loop - send updates every 2 seconds
        while True:
            try:
                # Get fresh status
                status = await get_status()
                
                # Build message in the structure frontend expects: { type: 'status', data: {...} }
                message = {
                    "type": "status",
                    "data": {
                        "scanner_running": bool(bot_state.scanner_running),
                        "ib_connected": bool(bot_state.fetcher.connected),
                        "active_tickers": int(status.get('active_tickers', 90)),
                        "open_positions": int(status.get('open_positions', 0)),
                        "last_scan": int(status.get('last_scan', 0))
                    }
                }
                
                # Add config if available
                if status.get('config'):
                    config = status['config']
                    message["data"]["config"] = {
                        "stop_loss_pct": float(config.get('stop_loss_pct', 8.0)),
                        "max_positions": int(config.get('max_positions', 16)),
                        "position_size_usd": float(config.get('position_size_usd', 10000)),
                        "paper_trading": bool(config.get('paper_trading', True)),
                        "auto_execute": bool(config.get('auto_execute', False))
                    }
                
                # Add statistics if available
                if status.get('statistics'):
                    stats = status['statistics']
                    message["data"]["statistics"] = {
                        "total_trades": int(stats.get('total_trades', 0)),
                        "wins": int(stats.get('wins', 0)),
                        "losses": int(stats.get('losses', 0)),
                        "win_rate": float(stats.get('win_rate', 0.0)),
                        "total_pnl": float(stats.get('total_pnl', 0.0))
                    }
                
                # Send using manual JSON encoding to catch serialization errors
                try:
                    json_string = json.dumps(message, cls=CustomJSONEncoder)
                    await websocket.send_text(json_string)
                except TypeError as json_err:
                    logger.error(f"JSON serialization error: {json_err}")
                    logger.error(f"Problematic message: {message}")
                    # Send minimal fallback
                    fallback = json.dumps({
                        "type": "status",
                        "data": {
                            "scanner_running": bool(bot_state.scanner_running),
                            "ib_connected": bool(bot_state.fetcher.connected)
                        }
                    })
                    await websocket.send_text(fallback)
                
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
        if websocket in bot_state.websocket_clients:
            bot_state.websocket_clients.remove(websocket)
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
