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
from zoneinfo import ZoneInfo
import json
import logging
import os
from dotenv import load_dotenv

ET = ZoneInfo("America/New_York")  # all date logic uses ET, not machine local

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
                    entry_method VARCHAR(50) DEFAULT NULL,
                    in_portfolio BOOLEAN DEFAULT false,
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
            
            # Add entry_method column if it doesn't exist (migration)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='scan_results' AND column_name='entry_method'
                    ) THEN
                        ALTER TABLE scan_results ADD COLUMN entry_method VARCHAR(50) DEFAULT NULL;
                    ELSE
                        -- Set existing 'prev_close' values to NULL (use default instead)
                        UPDATE scan_results SET entry_method = NULL WHERE entry_method = 'prev_close';
                    END IF;
                END $$;
            """)

            # Add in_portfolio column if it doesn't exist (migration)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='scan_results' AND column_name='in_portfolio'
                    ) THEN
                        ALTER TABLE scan_results ADD COLUMN in_portfolio BOOLEAN DEFAULT false;
                    END IF;
                END $$;
            """)
            
            # Positions - open positions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    symbol VARCHAR(20) PRIMARY KEY,
                    entry_date DATE NOT NULL,
                    entry_price DECIMAL(12, 4) NOT NULL,
                    submitted_price DECIMAL(12, 4) DEFAULT NULL,
                    quantity INTEGER NOT NULL,
                    stop_loss DECIMAL(12, 4) NOT NULL,
                    cost_basis DECIMAL(12, 2) NOT NULL,
                    max_price DECIMAL(12, 4) DEFAULT 0,
                    max_gain_pct DECIMAL(10, 4) DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'OPEN',
                    trade_id INTEGER,
                    notes TEXT,
                    pending_exit BOOLEAN DEFAULT false,
                    exit_reason VARCHAR(100) DEFAULT NULL,
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
                    submitted_price DECIMAL(12, 4) DEFAULT NULL,
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
                    default_entry_method VARCHAR(50) DEFAULT 'prev_close',
                    near_52wh_pct DECIMAL(5, 2) DEFAULT 5.0,
                    above_52wl_pct DECIMAL(5, 2) DEFAULT 30.0,
                    volume_multiplier DECIMAL(5, 2) DEFAULT 1.5,
                    spy_filter_enabled BOOLEAN DEFAULT true,
                    trend_break_exit_enabled BOOLEAN DEFAULT true,
                    limit_order_premium_pct DECIMAL(5, 2) DEFAULT 1.0,
                    scanner_interval_seconds INTEGER DEFAULT 30,
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
            
            # Add default_entry_method column if it doesn't exist (migration)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='bot_config' AND column_name='default_entry_method'
                    ) THEN
                        ALTER TABLE bot_config ADD COLUMN default_entry_method VARCHAR(50) DEFAULT 'prev_close';
                    END IF;
                END $$;
            """)

            # Add data update tracking columns if they don't exist (migration)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='bot_config' AND column_name='last_data_update'
                    ) THEN
                        ALTER TABLE bot_config
                            ADD COLUMN last_data_update TIMESTAMP DEFAULT NULL,
                            ADD COLUMN data_update_status VARCHAR(20) DEFAULT 'idle',
                            ADD COLUMN data_update_error TEXT DEFAULT NULL;
                    END IF;
                END $$;
            """)

            # Add configurable update time column if it doesn't exist (migration)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='bot_config' AND column_name='data_update_time'
                    ) THEN
                        ALTER TABLE bot_config
                            ADD COLUMN data_update_time VARCHAR(5) DEFAULT '17:00';
                    END IF;
                END $$;
            """)

            # Add order execution time column if it doesn't exist (migration)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='bot_config' AND column_name='order_execution_time'
                    ) THEN
                        ALTER TABLE bot_config
                            ADD COLUMN order_execution_time VARCHAR(5) DEFAULT '09:30';
                    END IF;
                END $$;
            """)

            # Add buy qualification criteria thresholds if they don't exist (migration)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='bot_config' AND column_name='near_52wh_pct'
                    ) THEN
                        ALTER TABLE bot_config ADD COLUMN near_52wh_pct DECIMAL(5, 2) DEFAULT 5.0;
                    END IF;
                END $$;
            """)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='bot_config' AND column_name='above_52wl_pct'
                    ) THEN
                        ALTER TABLE bot_config ADD COLUMN above_52wl_pct DECIMAL(5, 2) DEFAULT 30.0;
                    END IF;
                END $$;
            """)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='bot_config' AND column_name='volume_multiplier'
                    ) THEN
                        ALTER TABLE bot_config ADD COLUMN volume_multiplier DECIMAL(5, 2) DEFAULT 1.5;
                    END IF;
                END $$;
            """)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='bot_config' AND column_name='spy_filter_enabled'
                    ) THEN
                        ALTER TABLE bot_config ADD COLUMN spy_filter_enabled BOOLEAN DEFAULT true;
                    END IF;
                END $$;
            """)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='bot_config' AND column_name='trend_break_exit_enabled'
                    ) THEN
                        ALTER TABLE bot_config ADD COLUMN trend_break_exit_enabled BOOLEAN DEFAULT true;
                    END IF;
                END $$;
            """)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='bot_config' AND column_name='limit_order_premium_pct'
                    ) THEN
                        ALTER TABLE bot_config ADD COLUMN limit_order_premium_pct DECIMAL(5, 2) DEFAULT 1.0;
                    END IF;
                END $$;
            """)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='bot_config' AND column_name='scanner_interval_seconds'
                    ) THEN
                        ALTER TABLE bot_config ADD COLUMN scanner_interval_seconds INTEGER DEFAULT 30;
                    END IF;
                END $$;
            """)

            # Add pending_exit and exit_reason columns to positions if they don't exist (migration)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='positions' AND column_name='pending_exit'
                    ) THEN
                        ALTER TABLE positions
                            ADD COLUMN pending_exit BOOLEAN DEFAULT false,
                            ADD COLUMN exit_reason VARCHAR(100) DEFAULT NULL;
                    END IF;
                END $$;
            """)

            # Add submitted_price to positions if it doesn't exist (migration)
            # submitted_price = the limit/prev_close price we sent to IB
            # entry_price     = the actual average fill price returned by IB
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='positions' AND column_name='submitted_price'
                    ) THEN
                        ALTER TABLE positions
                            ADD COLUMN submitted_price DECIMAL(12, 4) DEFAULT NULL;
                    END IF;
                END $$;
            """)

            # Add submitted_price to trades if it doesn't exist (migration)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='trades' AND column_name='submitted_price'
                    ) THEN
                        ALTER TABLE trades
                            ADD COLUMN submitted_price DECIMAL(12, 4) DEFAULT NULL;
                    END IF;
                END $$;
            """)

            # Migration: add stop_loss to trades table (preserves original stop at entry time)
            cursor.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='trades' AND column_name='stop_loss'
                    ) THEN
                        ALTER TABLE trades
                            ADD COLUMN stop_loss DECIMAL(12, 4) DEFAULT NULL;
                    END IF;
                END $$;
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
    
    def get_all_daily_bars_batch(self, symbols: List[str], limit: int = 300) -> Dict[str, List[Dict]]:
        """
        Fetch recent daily bars for ALL given symbols in a single SQL query.
        Returns a dict mapping symbol -> list of bars (descending date order,
        same layout as get_daily_bars so existing callers need no changes).

        This replaces N individual get_daily_bars() calls in the scanner loop
        with one round-trip, cutting scan time significantly.
        """
        if not symbols:
            return {}

        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Use a window function to pick the most-recent `limit` rows per symbol
            cursor.execute("""
                SELECT symbol, date, open, high, low, close, volume
                FROM (
                    SELECT symbol, date, open, high, low, close, volume,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM daily_bars
                    WHERE symbol = ANY(%s)
                ) ranked
                WHERE rn <= %s
                ORDER BY symbol, date DESC
            """, (list(symbols), limit))

            rows = cursor.fetchall()

            # Group into per-symbol lists (already DESC ordered)
            result: Dict[str, List[Dict]] = {s: [] for s in symbols}
            for row in rows:
                sym = row['symbol']
                if sym in result:
                    result[sym].append({
                        'date':   row['date'],
                        'open':   row['open'],
                        'high':   row['high'],
                        'low':    row['low'],
                        'close':  row['close'],
                        'volume': row['volume'],
                    })
            return result

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
                    qualified, action, in_portfolio
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                    in_portfolio = EXCLUDED.in_portfolio,
                    created_at = CURRENT_TIMESTAMP
            """, (
                result['scan_date'], result['symbol'], result['price'],
                result['week_52_high'], result['week_52_low'],
                result['ma_50'], result['ma_150'], result['ma_200'], result['ma_200_1m_ago'],
                result['volume'], result['avg_volume_50'],
                result['criteria_1'], result['criteria_2'], result['criteria_3'],
                result['criteria_4'], result['criteria_5'], result['criteria_6'],
                result['criteria_7'], result['criteria_8'],
                result['qualified'], result['action'],
                result.get('in_portfolio', False)
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
                SELECT
                    sr.*,
                    sr.criteria_1_within_5pct_52w_high   AS criteria_1,
                    sr.criteria_2_above_50ma              AS criteria_2,
                    sr.criteria_3_50ma_above_150ma        AS criteria_3,
                    sr.criteria_4_150ma_above_200ma       AS criteria_4,
                    sr.criteria_5_200ma_trending_up       AS criteria_5,
                    sr.criteria_6_above_30pct_52w_low     AS criteria_6,
                    sr.criteria_7_breakout_volume         AS criteria_7,
                    sr.criteria_8_spy_above_50ma          AS criteria_8,
                    COALESCE(sr.entry_method, bc.default_entry_method, 'prev_close') as effective_entry_method,
                    bc.default_entry_method,
                    -- Always derive in_portfolio live from positions table so the flag
                    -- is accurate even across restarts / edge cases
                    (EXISTS (
                        SELECT 1 FROM positions p
                        WHERE p.symbol = sr.symbol AND p.status = 'OPEN'
                    )) AS in_portfolio
                FROM scan_results sr
                CROSS JOIN bot_config bc
                WHERE sr.scan_date = (SELECT MAX(scan_date) FROM scan_results)
                ORDER BY sr.qualified DESC, sr.symbol
            """)
            
            results = [dict(row) for row in cursor.fetchall()]
            
            # Clean up - replace entry_method with effective_entry_method
            for result in results:
                effective = result['effective_entry_method']
                default = result.get('default_entry_method')
                # A symbol has a manually-set entry method only when the DB column
                # is not NULL (i.e. different from the config default).
                raw_entry = result.get('entry_method')  # still the original DB value here
                result['manually_set'] = raw_entry is not None and raw_entry != default
                result['entry_method'] = effective
                del result['effective_entry_method']
            
            return results
            
        finally:
            cursor.close()
            conn.close()
    
    def update_scan_override(self, symbol: str, override: bool) -> bool:
        """Update override status for a symbol in today's scan results."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            today = datetime.now(ET).date()
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
    
    def update_scan_entry_method(self, symbol: str, entry_method: str) -> bool:
        """Update entry method for a symbol in today's scan results."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            today = datetime.now(ET).date()
            cursor.execute("""
                UPDATE scan_results 
                SET entry_method = %s
                WHERE symbol = %s AND scan_date = %s
            """, (entry_method, symbol, today))
            
            if cursor.rowcount > 0:
                conn.commit()
                logger.info(f"✅ Updated entry method for {symbol}: {entry_method}")
                return True
            else:
                logger.warning(f"⚠️ No scan result found for {symbol} on {today}")
                return False
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error updating entry method for {symbol}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def update_scan_result_portfolio_flag(self, symbol: str, in_portfolio: bool) -> bool:
        """Set or clear the in_portfolio flag on the most recent scan result for a symbol."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE scan_results
                SET in_portfolio = %s
                WHERE symbol = %s
                  AND scan_date = (SELECT MAX(scan_date) FROM scan_results WHERE symbol = %s)
            """, (in_portfolio, symbol, symbol))
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"✅ Set in_portfolio={in_portfolio} for {symbol}")
                return True
            else:
                logger.warning(f"⚠️ No scan result found to update in_portfolio for {symbol}")
                return False
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error updating in_portfolio for {symbol}: {e}")
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
                    symbol, entry_date, entry_price, submitted_price, quantity, stop_loss,
                    cost_basis, max_price, max_gain_pct, status, trade_id, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET
                    entry_price = EXCLUDED.entry_price,
                    submitted_price = EXCLUDED.submitted_price,
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
                position.get('submitted_price'),
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
        """Get all open positions enriched with last known price from scan_results.

        Joins against the latest scan_results row for each symbol to populate:
          - last_price      : most recent scanned price (IB-live during hours, DB-close otherwise)
          - price_scan_date : the date of that scan row (so UI can flag staleness)
          - price_scan_time : the created_at timestamp of that scan row
          - current_value   : last_price × quantity  (None if no scan price)
          - pnl             : current_value - cost_basis  (None if no scan price)
          - pnl_pct         : pnl / cost_basis × 100      (None if no scan price)

        No live IB call is made — returns instantly.
        """
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute("""
                SELECT
                    p.*,
                    sr.price                        AS last_price,
                    sr.scan_date                    AS price_scan_date,
                    sr.created_at                   AS price_scan_time,
                    CASE WHEN sr.price IS NOT NULL
                         THEN ROUND(sr.price * p.quantity, 2) END  AS current_value,
                    CASE WHEN sr.price IS NOT NULL
                         THEN ROUND(sr.price * p.quantity - p.cost_basis, 2) END AS pnl,
                    CASE WHEN sr.price IS NOT NULL AND p.cost_basis > 0
                         THEN ROUND(
                             (sr.price * p.quantity - p.cost_basis) / p.cost_basis * 100,
                             4
                         ) END AS pnl_pct
                FROM positions p
                LEFT JOIN LATERAL (
                    SELECT price, scan_date, created_at
                    FROM scan_results
                    WHERE symbol = p.symbol
                    ORDER BY scan_date DESC, created_at DESC
                    LIMIT 1
                ) sr ON true
                WHERE p.status = 'OPEN'
                ORDER BY p.entry_date
            """)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()
    
    def get_closed_positions(self) -> List[Dict]:
        """Get all closed trades with full entry/exit details, ordered most-recent first."""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute("""
                SELECT
                    id,
                    symbol,
                    entry_date,
                    exit_date,
                    entry_price,
                    submitted_price,
                    exit_price,
                    quantity,
                    cost_basis,
                    proceeds,
                    pnl,
                    pnl_pct,
                    exit_reason,
                    stop_loss,
                    status,
                    created_at
                FROM trades
                WHERE status = 'CLOSED'
                ORDER BY exit_date DESC, created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def reopen_position(self, trade_id: int, stop_loss: float) -> Dict:
        """Revert a mistakenly-closed trade back to OPEN status.

        Clears all exit fields on the trade row and re-inserts a position record.
        Uses the stop_loss stored in the trade row (preserved at close time) so the
        original value is always restored regardless of config changes since entry.
        Falls back to the caller-supplied stop_loss only if the trade row has NULL
        (i.e. it predates the stop_loss persistence migration).

        Returns the trade row so the caller has symbol/entry details for logging.
        """
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # 1. Fetch the closed trade to get entry details
            cursor.execute("SELECT * FROM trades WHERE id = %s AND status = 'CLOSED'", (trade_id,))
            trade = cursor.fetchone()
            if not trade:
                return {}
            trade = dict(trade)

            # Prefer the stop_loss stored on the trade row; fall back to caller value
            # for trades that predate the stop_loss persistence migration (NULL in DB).
            restored_stop_loss = float(trade['stop_loss']) if trade.get('stop_loss') else stop_loss

            # 2. Clear exit fields on the trade row; set status back to OPEN
            cursor.execute("""
                UPDATE trades
                SET exit_date   = NULL,
                    exit_price  = NULL,
                    proceeds    = NULL,
                    pnl         = NULL,
                    pnl_pct     = NULL,
                    exit_reason = NULL,
                    stop_loss   = NULL,
                    status      = 'OPEN'
                WHERE id = %s
            """, (trade_id,))

            # 3. Re-insert position row (ON CONFLICT handles the rare case where it still exists)
            cursor.execute("""
                INSERT INTO positions
                    (symbol, entry_date, entry_price, submitted_price,
                     quantity, stop_loss, cost_basis, trade_id, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'OPEN')
                ON CONFLICT (symbol) DO UPDATE
                    SET entry_date      = EXCLUDED.entry_date,
                        entry_price     = EXCLUDED.entry_price,
                        submitted_price = EXCLUDED.submitted_price,
                        quantity        = EXCLUDED.quantity,
                        stop_loss       = EXCLUDED.stop_loss,
                        cost_basis      = EXCLUDED.cost_basis,
                        trade_id        = EXCLUDED.trade_id,
                        status          = 'OPEN',
                        pending_exit    = false,
                        exit_reason     = NULL,
                        last_updated    = CURRENT_TIMESTAMP
            """, (
                trade['symbol'],
                trade['entry_date'],
                trade['entry_price'],
                trade.get('submitted_price'),
                trade['quantity'],
                restored_stop_loss,
                trade['cost_basis'],
                trade_id,
            ))

            conn.commit()
            logger.info(f"✅ Reopened trade #{trade_id} ({trade['symbol']})")
            return trade
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error reopening trade #{trade_id}: {e}")
            raise
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
    
    def flag_pending_exit(self, symbol: str, exit_reason: str) -> bool:
        """Flag a position as pending exit at next market open."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE positions
                SET pending_exit = true,
                    exit_reason = %s,
                    last_updated = CURRENT_TIMESTAMP
                WHERE symbol = %s AND status = 'OPEN'
            """, (exit_reason, symbol.upper()))
            conn.commit()
            logger.info(f"✅ Flagged {symbol} for exit: {exit_reason}")
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error flagging pending exit for {symbol}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_pending_exit_positions(self) -> List[Dict]:
        """Get all open positions flagged for exit at next market open."""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute("""
                SELECT * FROM positions
                WHERE status = 'OPEN' AND pending_exit = true
                ORDER BY entry_date
            """)
            return [dict(row) for row in cursor.fetchall()]
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
                    symbol, entry_date, entry_price, submitted_price, quantity, cost_basis, status
                ) VALUES (%s, %s, %s, %s, %s, %s, 'OPEN')
                RETURNING id
            """, (
                trade['symbol'], trade['entry_date'], trade['entry_price'],
                trade.get('submitted_price'),
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
                    proceeds: float, pnl: float, pnl_pct: float, reason: str,
                    stop_loss: float = None) -> bool:
        """Close a trade, preserving the original stop_loss for safe reopening."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE trades
                SET exit_date   = %s,
                    exit_price  = %s,
                    proceeds    = %s,
                    pnl         = %s,
                    pnl_pct     = %s,
                    exit_reason = %s,
                    stop_loss   = COALESCE(%s, stop_loss),
                    status      = 'CLOSED'
                WHERE id = %s
            """, (exit_date, exit_price, proceeds, pnl, pnl_pct, reason, stop_loss, trade_id))
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
                SET stop_loss_pct              = %s,
                    max_positions              = %s,
                    position_size_usd          = %s,
                    paper_trading              = %s,
                    auto_execute               = %s,
                    default_entry_method       = %s,
                    data_update_time           = %s,
                    order_execution_time       = %s,
                    near_52wh_pct              = %s,
                    above_52wl_pct             = %s,
                    volume_multiplier          = %s,
                    spy_filter_enabled         = %s,
                    trend_break_exit_enabled   = %s,
                    limit_order_premium_pct    = %s,
                    scanner_interval_seconds   = %s,
                    updated_at                 = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (
                config.get('stop_loss_pct'),
                config.get('max_positions'),
                config.get('position_size_usd'),
                config.get('paper_trading'),
                config.get('auto_execute'),
                config.get('default_entry_method', 'prev_close'),
                config.get('data_update_time'),
                config.get('order_execution_time'),
                config.get('near_52wh_pct', 5.0),
                config.get('above_52wl_pct', 30.0),
                config.get('volume_multiplier', 1.5),
                config.get('spy_filter_enabled', True),
                config.get('trend_break_exit_enabled', True),
                config.get('limit_order_premium_pct', 1.0),
                config.get('scanner_interval_seconds', 30),
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

    def get_data_update_status(self) -> Dict:
        """Get last data update time, status, error, and configured update time."""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute("""
                SELECT last_data_update, data_update_status, data_update_error, data_update_time
                FROM bot_config WHERE id = 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else {
                'last_data_update': None,
                'data_update_status': 'idle',
                'data_update_error': None,
                'data_update_time': None
            }
        finally:
            cursor.close()
            conn.close()

    def set_data_update_status(self, status: str, error: str = None) -> bool:
        """Update data update status, optionally clearing or setting error and timestamp."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            if status == 'success':
                cursor.execute("""
                    UPDATE bot_config
                    SET data_update_status = %s,
                        last_data_update = CURRENT_TIMESTAMP,
                        data_update_error = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (status,))
            else:
                cursor.execute("""
                    UPDATE bot_config
                    SET data_update_status = %s,
                        data_update_error = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (status, error))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error updating data update status: {e}")
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
                'total_pnl': float(closed_stats[3] or 0),
                'avg_pnl': float(closed_stats[4] or 0),
                'max_win': float(closed_stats[5] or 0),
                'max_loss': float(closed_stats[6] or 0),
                'open_positions': open_stats[0] or 0,
                'total_invested': float(open_stats[1] or 0)
            }
            
        finally:
            cursor.close()
            conn.close()
