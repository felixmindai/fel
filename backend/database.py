"""
Database Manager for Minervini Trading Bot
==========================================

Handles all PostgreSQL database operations including:
- Connection management
- Table creation and migrations
- CRUD operations for tickers, bars, positions, trades
- Data persistence and recovery
"""

import psycopg2
from psycopg2 import sql, extras
from psycopg2.extras import RealDictCursor
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
import json
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Database:
    """Manages all database operations for the Minervini trading bot."""
    
    def __init__(self):
        """Initialize database connection from environment variables."""
        self.connection_params = {
            'dbname': os.getenv('DB_NAME', 'minervini_bot'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', ''),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432'))
        }
        
        logger.info(f"Database config: {self.connection_params['host']}:{self.connection_params['port']}/{self.connection_params['dbname']}")
        
        # Test connection
        self.test_connection()
    
    def get_connection(self):
        """Get a new database connection."""
        try:
            conn = psycopg2.connect(**self.connection_params)
            return conn
        except psycopg2.Error as e:
            logger.error(f"❌ Database connection error: {e}")
            raise
    
    def test_connection(self):
        """Test database connectivity."""
        try:
            conn = self.get_connection()
            conn.close()
            logger.info("✅ PostgreSQL connection successful")
        except Exception as e:
            logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
            raise
    
    def create_tables(self):
        """Create all required database tables."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Tickers table - monitored stock universe
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickers (
                    symbol VARCHAR(20) PRIMARY KEY,
                    name VARCHAR(200),
                    sector VARCHAR(100),
                    active BOOLEAN DEFAULT true,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Daily bars - historical OHLCV data
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_bars (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    date DATE NOT NULL,
                    open DECIMAL(12, 4),
                    high DECIMAL(12, 4),
                    low DECIMAL(12, 4),
                    close DECIMAL(12, 4),
                    volume BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date)
                )
            """)
            
            # Scanner results - daily qualification status
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_results (
                    id SERIAL PRIMARY KEY,
                    scan_date DATE NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    price DECIMAL(12, 4),
                    week_52_high DECIMAL(12, 4),
                    week_52_low DECIMAL(12, 4),
                    ma_50 DECIMAL(12, 4),
                    ma_150 DECIMAL(12, 4),
                    ma_200 DECIMAL(12, 4),
                    ma_200_1m_ago DECIMAL(12, 4),
                    volume BIGINT,
                    avg_volume_50 BIGINT,
                    criteria_1_within_5pct_52w_high BOOLEAN,
                    criteria_2_above_50ma BOOLEAN,
                    criteria_3_50ma_above_150ma BOOLEAN,
                    criteria_4_150ma_above_200ma BOOLEAN,
                    criteria_5_200ma_trending_up BOOLEAN,
                    criteria_6_above_30pct_52w_low BOOLEAN,
                    criteria_7_breakout_volume BOOLEAN,
                    criteria_8_spy_above_50ma BOOLEAN,
                    qualified BOOLEAN,
                    action VARCHAR(50),
                    override BOOLEAN DEFAULT false,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(scan_date, symbol)
                )
            """)
            
            # Add override column if it doesn't exist (migration)
            cursor.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='scan_results' AND column_name='override'
                    ) THEN
                        ALTER TABLE scan_results ADD COLUMN override BOOLEAN DEFAULT false;
                    END IF;
                END $$;
            """)
            
            # Positions - open positions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    symbol VARCHAR(20) PRIMARY KEY,
                    entry_date DATE NOT NULL,
                    entry_price DECIMAL(12, 4) NOT NULL,
                    quantity INTEGER NOT NULL,
                    stop_loss DECIMAL(12, 4) NOT NULL,
                    cost_basis DECIMAL(12, 2) NOT NULL,
                    max_price DECIMAL(12, 4) DEFAULT 0,
                    max_gain_pct DECIMAL(10, 4) DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'OPEN',
                    trade_id INTEGER,
                    notes TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Trades - complete trade history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    entry_date DATE NOT NULL,
                    entry_price DECIMAL(12, 4) NOT NULL,
                    exit_date DATE,
                    exit_price DECIMAL(12, 4),
                    quantity INTEGER NOT NULL,
                    cost_basis DECIMAL(12, 2) NOT NULL,
                    proceeds DECIMAL(12, 2),
                    pnl DECIMAL(12, 2),
                    pnl_pct DECIMAL(10, 4),
                    exit_reason VARCHAR(100),
                    status VARCHAR(20) DEFAULT 'OPEN',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Bot configuration
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    stop_loss_pct DECIMAL(5, 2) DEFAULT 8.0,
                    max_positions INTEGER DEFAULT 16,
                    position_size_usd DECIMAL(12, 2) DEFAULT 10000.0,
                    paper_trading BOOLEAN DEFAULT true,
                    auto_execute BOOLEAN DEFAULT false,
                    scanner_running BOOLEAN DEFAULT false,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CHECK (id = 1)
                )
            """)
            
            # Insert default config if not exists
            cursor.execute("""
                INSERT INTO bot_config (id) 
                VALUES (1) 
                ON CONFLICT (id) DO NOTHING
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_bars_symbol ON daily_bars(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_bars_date ON daily_bars(date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_bars_symbol_date ON daily_bars(symbol, date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_results_date ON scan_results(scan_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_results_qualified ON scan_results(qualified)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
            
            conn.commit()
            logger.info("✅ Database tables created/verified")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error creating tables: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    # ==================== TICKERS ====================
    
    def add_ticker(self, symbol: str, name: str = None, sector: str = None) -> bool:
        """Add a ticker to the monitored universe."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO tickers (symbol, name, sector, active)
                VALUES (%s, %s, %s, true)
                ON CONFLICT (symbol) DO UPDATE 
                SET active = true, name = EXCLUDED.name, sector = EXCLUDED.sector
            """, (symbol.upper(), name, sector))
            
            conn.commit()
            logger.info(f"✅ Added ticker: {symbol}")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error adding ticker {symbol}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def remove_ticker(self, symbol: str) -> bool:
        """Remove a ticker (soft delete)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE tickers 
                SET active = false 
                WHERE symbol = %s
            """, (symbol.upper(),))
            
            conn.commit()
            logger.info(f"✅ Removed ticker: {symbol}")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error removing ticker {symbol}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def get_active_tickers(self) -> List[str]:
        """Get list of active tickers."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT symbol FROM tickers 
                WHERE active = true 
                ORDER BY symbol
            """)
            
            tickers = [row[0] for row in cursor.fetchall()]
            return tickers
            
        finally:
            cursor.close()
            conn.close()
    
    def get_all_tickers(self) -> List[Dict]:
        """Get all tickers with details."""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT symbol, name, sector, active, added_date 
                FROM tickers 
                ORDER BY symbol
            """)
            
            return [dict(row) for row in cursor.fetchall()]
            
        finally:
            cursor.close()
            conn.close()
    
    # ==================== DAILY BARS ====================
    
    def save_daily_bars(self, symbol: str, bars: List[Dict]) -> int:
        """Save multiple daily bars for a symbol."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            inserted = 0
            for bar in bars:
                cursor.execute("""
                    INSERT INTO daily_bars (symbol, date, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) 
                    DO UPDATE SET 
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume
                """, (
                    symbol.upper(),
                    bar['date'],
                    bar['open'],
                    bar['high'],
                    bar['low'],
                    bar['close'],
                    bar['volume']
                ))
                inserted += 1
            
            conn.commit()
            logger.info(f"✅ Saved {inserted} bars for {symbol}")
            return inserted
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error saving bars for {symbol}: {e}")
            return 0
        finally:
            cursor.close()
            conn.close()
    
    def get_daily_bars(self, symbol: str, limit: int = 300) -> List[Dict]:
        """Get recent daily bars for a symbol."""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT date, open, high, low, close, volume
                FROM daily_bars
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT %s
            """, (symbol.upper(), limit))
            
            return [dict(row) for row in cursor.fetchall()]
            
        finally:
            cursor.close()
            conn.close()
    
    def get_latest_bar_date(self, symbol: str) -> Optional[date]:
        """Get the date of the most recent bar for a symbol."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT MAX(date) FROM daily_bars WHERE symbol = %s
            """, (symbol.upper(),))
            
            result = cursor.fetchone()
            return result[0] if result and result[0] else None
            
        finally:
            cursor.close()
            conn.close()
    
    # ==================== SCAN RESULTS ====================
    
    def save_scan_result(self, result: Dict) -> bool:
        """Save a scan result."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO scan_results (
                    scan_date, symbol, price, week_52_high, week_52_low,
                    ma_50, ma_150, ma_200, ma_200_1m_ago,
                    volume, avg_volume_50,
                    criteria_1_within_5pct_52w_high,
                    criteria_2_above_50ma,
                    criteria_3_50ma_above_150ma,
                    criteria_4_150ma_above_200ma,
                    criteria_5_200ma_trending_up,
                    criteria_6_above_30pct_52w_low,
                    criteria_7_breakout_volume,
                    criteria_8_spy_above_50ma,
                    qualified, action
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (scan_date, symbol) 
                DO UPDATE SET
                    price = EXCLUDED.price,
                    week_52_high = EXCLUDED.week_52_high,
                    week_52_low = EXCLUDED.week_52_low,
                    ma_50 = EXCLUDED.ma_50,
                    ma_150 = EXCLUDED.ma_150,
                    ma_200 = EXCLUDED.ma_200,
                    ma_200_1m_ago = EXCLUDED.ma_200_1m_ago,
                    volume = EXCLUDED.volume,
                    avg_volume_50 = EXCLUDED.avg_volume_50,
                    criteria_1_within_5pct_52w_high = EXCLUDED.criteria_1_within_5pct_52w_high,
                    criteria_2_above_50ma = EXCLUDED.criteria_2_above_50ma,
                    criteria_3_50ma_above_150ma = EXCLUDED.criteria_3_50ma_above_150ma,
                    criteria_4_150ma_above_200ma = EXCLUDED.criteria_4_150ma_above_200ma,
                    criteria_5_200ma_trending_up = EXCLUDED.criteria_5_200ma_trending_up,
                    criteria_6_above_30pct_52w_low = EXCLUDED.criteria_6_above_30pct_52w_low,
                    criteria_7_breakout_volume = EXCLUDED.criteria_7_breakout_volume,
                    criteria_8_spy_above_50ma = EXCLUDED.criteria_8_spy_above_50ma,
                    qualified = EXCLUDED.qualified,
                    action = EXCLUDED.action,
                    created_at = CURRENT_TIMESTAMP
            """, (
                result['scan_date'], result['symbol'], result['price'],
                result['week_52_high'], result['week_52_low'],
                result['ma_50'], result['ma_150'], result['ma_200'], result['ma_200_1m_ago'],
                result['volume'], result['avg_volume_50'],
                result['criteria_1'], result['criteria_2'], result['criteria_3'],
                result['criteria_4'], result['criteria_5'], result['criteria_6'],
                result['criteria_7'], result['criteria_8'],
                result['qualified'], result['action']
            ))
            
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error saving scan result for {result.get('symbol')}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def get_latest_scan_results(self) -> List[Dict]:
        """Get the most recent scan results for all symbols."""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT * FROM scan_results
                WHERE scan_date = (SELECT MAX(scan_date) FROM scan_results)
                ORDER BY qualified DESC, symbol
            """)
            
            return [dict(row) for row in cursor.fetchall()]
            
        finally:
            cursor.close()
            conn.close()
    
    def update_scan_override(self, symbol: str, override: bool) -> bool:
        """Update override status for a symbol in today's scan results."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            today = date.today()
            cursor.execute("""
                UPDATE scan_results 
                SET override = %s
                WHERE symbol = %s AND scan_date = %s
            """, (override, symbol, today))
            
            if cursor.rowcount > 0:
                conn.commit()
                logger.info(f"✅ Updated override for {symbol}: {override}")
                return True
            else:
                logger.warning(f"⚠️ No scan result found for {symbol} on {today}")
                return False
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error updating override for {symbol}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    # ==================== POSITIONS ====================
    
    def save_position(self, position: Dict) -> bool:
        """Save or update a position."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO positions (
                    symbol, entry_date, entry_price, quantity, stop_loss,
                    cost_basis, max_price, max_gain_pct, status, trade_id, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET
                    entry_price = EXCLUDED.entry_price,
                    quantity = EXCLUDED.quantity,
                    stop_loss = EXCLUDED.stop_loss,
                    cost_basis = EXCLUDED.cost_basis,
                    max_price = EXCLUDED.max_price,
                    max_gain_pct = EXCLUDED.max_gain_pct,
                    status = EXCLUDED.status,
                    trade_id = EXCLUDED.trade_id,
                    notes = EXCLUDED.notes,
                    last_updated = CURRENT_TIMESTAMP
            """, (
                position['symbol'], position['entry_date'], position['entry_price'],
                position['quantity'], position['stop_loss'], position['cost_basis'],
                position.get('max_price', 0), position.get('max_gain_pct', 0),
                position.get('status', 'OPEN'), position.get('trade_id'),
                position.get('notes', '')
            ))
            
            conn.commit()
            logger.info(f"✅ Saved position: {position['symbol']}")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error saving position {position.get('symbol')}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def get_positions(self) -> List[Dict]:
        """Get all open positions."""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT * FROM positions 
                WHERE status = 'OPEN'
                ORDER BY entry_date
            """)
            
            return [dict(row) for row in cursor.fetchall()]
            
        finally:
            cursor.close()
            conn.close()
    
    def close_position(self, symbol: str) -> bool:
        """Mark a position as closed."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE positions 
                SET status = 'CLOSED', last_updated = CURRENT_TIMESTAMP
                WHERE symbol = %s
            """, (symbol.upper(),))
            
            conn.commit()
            logger.info(f"✅ Closed position: {symbol}")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error closing position {symbol}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    # ==================== TRADES ====================
    
    def create_trade(self, trade: Dict) -> Optional[int]:
        """Create a new trade record."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO trades (
                    symbol, entry_date, entry_price, quantity, cost_basis, status
                ) VALUES (%s, %s, %s, %s, %s, 'OPEN')
                RETURNING id
            """, (
                trade['symbol'], trade['entry_date'], trade['entry_price'],
                trade['quantity'], trade['cost_basis']
            ))
            
            trade_id = cursor.fetchone()[0]
            conn.commit()
            logger.info(f"✅ Created trade #{trade_id}: {trade['symbol']}")
            return trade_id
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error creating trade for {trade.get('symbol')}: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
    
    def close_trade(self, trade_id: int, exit_date: date, exit_price: float, 
                    proceeds: float, pnl: float, pnl_pct: float, reason: str) -> bool:
        """Close a trade."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE trades 
                SET exit_date = %s, exit_price = %s, proceeds = %s,
                    pnl = %s, pnl_pct = %s, exit_reason = %s, status = 'CLOSED'
                WHERE id = %s
            """, (exit_date, exit_price, proceeds, pnl, pnl_pct, reason, trade_id))
            
            conn.commit()
            logger.info(f"✅ Closed trade #{trade_id}")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error closing trade #{trade_id}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def get_trades(self, status: str = None, limit: int = 100) -> List[Dict]:
        """Get trade history."""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            if status:
                cursor.execute("""
                    SELECT * FROM trades 
                    WHERE status = %s
                    ORDER BY entry_date DESC
                    LIMIT %s
                """, (status, limit))
            else:
                cursor.execute("""
                    SELECT * FROM trades 
                    ORDER BY entry_date DESC
                    LIMIT %s
                """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
            
        finally:
            cursor.close()
            conn.close()
    
    # ==================== CONFIG ====================
    
    def get_config(self) -> Dict:
        """Get bot configuration."""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("SELECT * FROM bot_config WHERE id = 1")
            result = cursor.fetchone()
            return dict(result) if result else {}
            
        finally:
            cursor.close()
            conn.close()
    
    def update_config(self, config: Dict) -> bool:
        """Update bot configuration."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE bot_config 
                SET stop_loss_pct = %s,
                    max_positions = %s,
                    position_size_usd = %s,
                    paper_trading = %s,
                    auto_execute = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (
                config.get('stop_loss_pct'),
                config.get('max_positions'),
                config.get('position_size_usd'),
                config.get('paper_trading'),
                config.get('auto_execute')
            ))
            
            conn.commit()
            logger.info("✅ Updated bot configuration")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error updating config: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def set_scanner_status(self, running: bool) -> bool:
        """Update scanner running status."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE bot_config 
                SET scanner_running = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (running,))
            
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error updating scanner status: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    # ==================== STATISTICS ====================
    
    def get_statistics(self) -> Dict:
        """Get overall statistics."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Closed trades stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(pnl), 0) as total_pnl,
                    COALESCE(AVG(pnl), 0) as avg_pnl,
                    COALESCE(MAX(pnl), 0) as max_win,
                    COALESCE(MIN(pnl), 0) as max_loss
                FROM trades
                WHERE status = 'CLOSED'
            """)
            
            closed_stats = cursor.fetchone()
            
            # Open positions stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as open_positions,
                    COALESCE(SUM(cost_basis), 0) as total_invested
                FROM positions
                WHERE status = 'OPEN'
            """)
            
            open_stats = cursor.fetchone()
            
            total_trades = closed_stats[0] or 0
            wins = closed_stats[1] or 0
            
            return {
                'total_trades': total_trades,
                'wins': wins,
                'losses': closed_stats[2] or 0,
                'win_rate': (wins / total_trades * 100) if total_trades > 0 else 0,
                'total_pnl': float(closed_stats[3]),
                'avg_pnl': float(closed_stats[4]),
                'max_win': float(closed_stats[5]),
                'max_loss': float(closed_stats[6]),
                'open_positions': open_stats[0] or 0,
                'total_invested': float(open_stats[1])
            }
            
        finally:
            cursor.close()
            conn.close()
