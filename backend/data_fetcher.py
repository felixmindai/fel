"""
Data Fetcher - IBKR Historical Data
====================================

Fetches historical daily bars from Interactive Brokers for:
- Initial bootstrap (1 year of data)
- Daily updates (latest bar)
- Real-time market data for scanning
"""

from ib_insync import IB, Stock, util
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import asyncio
import logging
import os
from dotenv import load_dotenv
import nest_asyncio

nest_asyncio.apply()
load_dotenv()

logger = logging.getLogger(__name__)


class DataFetcher:
    """Fetches historical and real-time data from Interactive Brokers."""
    
    def __init__(self):
        self.ib = IB()
        self.connected = False
        
        self.host = os.getenv('IB_HOST', '127.0.0.1')
        self.port = int(os.getenv('IB_PORT', '7497'))
        self.client_id = int(os.getenv('IB_CLIENT_ID', '1'))
        
    def connect(self) -> bool:
        """Connect to Interactive Brokers."""
        try:
            if not self.connected:
                self.ib.connect(self.host, self.port, clientId=self.client_id)
                self.ib.reqMarketDataType(3)  # Delayed market data (free)
                self.connected = True
                logger.info(f"✅ Connected to IB at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to IB: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Interactive Brokers."""
        if self.connected:
            self.ib.disconnect()
            self.connected = False
            logger.info("Disconnected from IB")
    
    def fetch_historical_bars(self, symbol: str, duration: str = '1 Y', 
                             bar_size: str = '1 day') -> List[Dict]:
        """
        Fetch historical bars for a symbol.
        
        Args:
            symbol: Stock ticker
            duration: How far back (e.g., '1 Y', '6 M', '30 D')
            bar_size: Bar size (e.g., '1 day', '1 hour')
            
        Returns:
            List of bars with date, open, high, low, close, volume
        """
        if not self.connected:
            if not self.connect():
                return []
        
        try:
            # Qualify the contract
            contract = Stock(symbol, 'SMART', 'USD')
            qualified = self.ib.qualifyContracts(contract)
            
            if not qualified:
                logger.warning(f"⚠️ Could not qualify contract for {symbol}")
                return []
            
            contract = qualified[0]
            
            # Request historical data
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow='TRADES',
                useRTH=True,  # Regular trading hours only
                formatDate=1
            )
            
            if not bars:
                logger.warning(f"⚠️ No historical data for {symbol}")
                return []
            
            # Convert to dict format
            result = []
            for bar in bars:
                result.append({
                    'date': bar.date.date() if hasattr(bar.date, 'date') else bar.date,
                    'open': float(bar.open),
                    'high': float(bar.high),
                    'low': float(bar.low),
                    'close': float(bar.close),
                    'volume': int(bar.volume)
                })
            
            logger.info(f"✅ Fetched {len(result)} bars for {symbol}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error fetching data for {symbol}: {e}")
            return []
    
    def fetch_current_price(self, symbol: str) -> Optional[float]:
        """Get current market price for a symbol."""
        if not self.connected:
            if not self.connect():
                return None
        
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            qualified = self.ib.qualifyContracts(contract)
            
            if not qualified:
                return None
            
            contract = qualified[0]
            
            # Request market data
            ticker = self.ib.reqMktData(contract, '', False, False)
            self.ib.sleep(2)  # Wait for data
            
            # Try to get the last traded price
            price = ticker.last if ticker.last else ticker.close
            
            # Cancel market data subscription
            self.ib.cancelMktData(contract)
            
            return float(price) if price else None
            
        except Exception as e:
            logger.error(f"❌ Error fetching price for {symbol}: {e}")
            return None
    
    def fetch_multiple_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Fetch current prices for multiple symbols efficiently.
        
        Args:
            symbols: List of ticker symbols
            
        Returns:
            Dictionary mapping symbol to current price
        """
        if not self.connected:
            if not self.connect():
                return {}
        
        prices = {}
        
        try:
            # Qualify all contracts
            contracts = [Stock(symbol, 'SMART', 'USD') for symbol in symbols]
            qualified = self.ib.qualifyContracts(*contracts)
            
            if not qualified:
                logger.warning("⚠️ No contracts qualified")
                return {}
            
            # Request market data for all
            tickers = []
            for contract in qualified:
                ticker = self.ib.reqMktData(contract, '', False, False)
                tickers.append((contract.symbol, ticker))
            
            # Wait for data to populate
            self.ib.sleep(3)
            
            # Extract prices
            for symbol, ticker in tickers:
                price = ticker.last if ticker.last else ticker.close
                if price:
                    prices[symbol] = float(price)
                
                # Cancel subscription
                self.ib.cancelMktData(ticker.contract)
            
            logger.info(f"✅ Fetched prices for {len(prices)}/{len(symbols)} symbols")
            return prices
            
        except Exception as e:
            logger.error(f"❌ Error fetching multiple prices: {e}")
            return prices
    
    def fetch_company_details(self, symbol: str) -> Dict:
        """Fetch company name and sector."""
        if not self.connected:
            if not self.connect():
                return {'name': symbol, 'sector': ''}
        
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            qualified = self.ib.qualifyContracts(contract)
            
            if not qualified:
                return {'name': symbol, 'sector': ''}
            
            contract = qualified[0]
            
            # Request contract details
            details = self.ib.reqContractDetails(contract)
            
            if details:
                detail = details[0]
                return {
                    'name': detail.longName if hasattr(detail, 'longName') else symbol,
                    'sector': detail.industry if hasattr(detail, 'industry') else ''
                }
            
            return {'name': symbol, 'sector': ''}
            
        except Exception as e:
            logger.error(f"❌ Error fetching details for {symbol}: {e}")
            return {'name': symbol, 'sector': ''}
    
    def get_52_week_range(self, bars: List[Dict]) -> tuple:
        """
        Calculate 52-week high and low from bars.
        
        Args:
            bars: List of daily bars (at least 252 trading days for 1 year)
            
        Returns:
            Tuple of (52_week_high, 52_week_low)
        """
        if not bars or len(bars) < 252:
            logger.warning(f"⚠️ Insufficient data for 52-week range (need 252, got {len(bars)})")
            # Use what we have
            if not bars:
                return (0, 0)
        
        # Get last 252 bars (1 year)
        recent_bars = bars[-252:] if len(bars) >= 252 else bars
        
        highs = [bar['high'] for bar in recent_bars]
        lows = [bar['low'] for bar in recent_bars]
        
        return (max(highs), min(lows))
    
    def calculate_moving_average(self, bars: List[Dict], period: int) -> Optional[float]:
        """
        Calculate simple moving average from bars.
        
        Args:
            bars: List of daily bars (most recent last)
            period: MA period (e.g., 50, 150, 200)
            
        Returns:
            Moving average value or None if insufficient data
        """
        if len(bars) < period:
            return None
        
        # Get last 'period' closes
        closes = [bar['close'] for bar in bars[-period:]]
        
        return sum(closes) / len(closes)
    
    def calculate_average_volume(self, bars: List[Dict], period: int = 50) -> Optional[int]:
        """Calculate average volume over period."""
        if len(bars) < period:
            return None
        
        volumes = [bar['volume'] for bar in bars[-period:]]
        return int(sum(volumes) / len(volumes))


# ============================================================================
# ASYNC WRAPPER FOR USE IN FASTAPI
# ============================================================================

class AsyncDataFetcher:
    """Async wrapper for DataFetcher to use in FastAPI."""
    
    def __init__(self):
        self.fetcher = DataFetcher()
    
    async def connect(self) -> bool:
        """Async connect."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.fetcher.connect
        )
    
    async def disconnect(self):
        """Async disconnect."""
        await asyncio.get_event_loop().run_in_executor(
            None, self.fetcher.disconnect
        )
    
    async def fetch_historical_bars(self, symbol: str, duration: str = '1 Y') -> List[Dict]:
        """Async fetch historical bars."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.fetcher.fetch_historical_bars, symbol, duration
        )
    
    async def fetch_current_price(self, symbol: str) -> Optional[float]:
        """Async fetch current price."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.fetcher.fetch_current_price, symbol
        )
    
    async def fetch_multiple_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Async fetch multiple prices."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.fetcher.fetch_multiple_prices, symbols
        )
