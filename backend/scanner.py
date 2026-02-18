"""
Minervini Scanner - 8-Criteria SEPA Methodology
================================================

Scans stocks for breakout opportunities using Mark Minervini's criteria:

1. Price within 5% of 52-week high
2. Price above 50-day MA
3. 50-day MA above 150-day MA
4. 150-day MA above 200-day MA
5. 200-day MA trending up (vs 1 month ago)
6. Price at least 30% above 52-week low
7. Breakout on above-average volume (1.5x)
8. SPY above its 50-day MA (market health)
"""

from datetime import date, datetime
from typing import List, Dict, Optional
import logging
from database import Database
from data_fetcher import DataFetcher

logger = logging.getLogger(__name__)


class MinerviniScanner:
    """Scans stocks using 8-criteria SEPA methodology."""
    
    def __init__(self, db: Database, fetcher: DataFetcher):
        self.db = db
        self.fetcher = fetcher
        self.spy_qualified = False  # Criterion #8 - market health
    
    def calculate_criteria(self, symbol: str, bars: List[Dict], 
                          current_price: float, current_volume: int) -> Dict:
        """
        Evaluate all 8 criteria for a symbol.
        
        Args:
            symbol: Stock ticker
            bars: Historical daily bars (most recent last)
            current_price: Current/latest price
            current_volume: Current/latest volume
            
        Returns:
            Dictionary with all criteria results and qualification status
        """
        if len(bars) < 250:
            logger.warning(f"⚠️ {symbol}: Insufficient data ({len(bars)} bars, need 250)")
            return self._failed_result(symbol, "Insufficient data")
        
        # Extract closes and volumes - convert Decimals to floats
        closes = [float(bar['close']) for bar in bars if bar['close']]
        volumes = [int(bar['volume']) for bar in bars if bar['volume']]
        
        # Calculate 52-week high/low (last 250 trading days) - convert to float
        recent_250 = bars[-250:]
        week_52_high = float(max([bar['high'] for bar in recent_250 if bar['high']]))
        week_52_low = float(min([bar['low'] for bar in recent_250 if bar['low']]))
        
        # Calculate moving averages
        ma_50 = self._calculate_sma(closes, 50)
        ma_150 = self._calculate_sma(closes, 150)
        ma_200 = self._calculate_sma(closes, 200)
        
        # 200-day MA from 22 trading days ago (approximately 1 month)
        if len(closes) >= 222:  # 200 + 22
            closes_22_days_ago = closes[:-22]
            ma_200_1m_ago = self._calculate_sma(closes_22_days_ago, 200)
        else:
            ma_200_1m_ago = None
        
        # Average volume (last 50 days)
        avg_volume_50 = int(sum(volumes[-50:]) / len(volumes[-50:])) if len(volumes) >= 50 else 0
        
        # Check for None values
        if None in [ma_50, ma_150, ma_200, ma_200_1m_ago]:
            return self._failed_result(symbol, "Could not calculate MAs")
        
        # ========== EVALUATE 8 CRITERIA ==========
        
        # 1. Price within 5% of 52-week high
        criteria_1 = current_price >= (week_52_high * 0.95)
        
        # 2. Price above 50-day MA
        criteria_2 = current_price > ma_50
        
        # 3. 50-day MA above 150-day MA
        criteria_3 = ma_50 > ma_150
        
        # 4. 150-day MA above 200-day MA
        criteria_4 = ma_150 > ma_200
        
        # 5. 200-day MA trending up (current > 1 month ago)
        criteria_5 = ma_200 > ma_200_1m_ago
        
        # 6. Price at least 30% above 52-week low
        criteria_6 = current_price >= (week_52_low * 1.30)
        
        # 7. Breakout on above-average volume (1.5x)
        criteria_7 = current_volume >= (avg_volume_50 * 1.5) if avg_volume_50 > 0 else False

        # 8. SPY above its 50-day MA (checked separately)
        criteria_8 = self.spy_qualified
        
        # ALL 8 must be True
        all_criteria_met = all([
            criteria_1, criteria_2, criteria_3, criteria_4,
            criteria_5, criteria_6, criteria_7, criteria_8
        ])
        
        # Determine action
        action = 'BUY_AT_OPEN' if all_criteria_met else 'PASS'
        
        result = {
            'scan_date': date.today(),
            'symbol': symbol,
            'price': current_price,
            'week_52_high': week_52_high,
            'week_52_low': week_52_low,
            'ma_50': ma_50,
            'ma_150': ma_150,
            'ma_200': ma_200,
            'ma_200_1m_ago': ma_200_1m_ago,
            'volume': current_volume,
            'avg_volume_50': avg_volume_50,
            'criteria_1': criteria_1,
            'criteria_2': criteria_2,
            'criteria_3': criteria_3,
            'criteria_4': criteria_4,
            'criteria_5': criteria_5,
            'criteria_6': criteria_6,
            'criteria_7': criteria_7,
            'criteria_8': criteria_8,
            'qualified': all_criteria_met,
            'action': action
        }
        
        return result
    
    def check_spy_health(self) -> bool:
        """
        Check criterion #8: SPY above its 50-day MA.
        This is the market health filter.
        
        Returns:
            True if SPY is above 50-day MA, False otherwise
        """
        try:
            logger.info("Checking SPY market health...")
            
            # Get SPY historical data from DATABASE (not IB)
            spy_bars = self.db.get_daily_bars('SPY', limit=60)
            
            if not spy_bars or len(spy_bars) < 50:
                logger.warning(f"⚠️ Insufficient SPY data in database ({len(spy_bars) if spy_bars else 0} bars)")
                self.spy_qualified = False
                return False
            
            # Reverse to chronological order (oldest to newest)
            spy_bars.reverse()
            
            # Use latest close as current price - convert Decimal to float
            spy_price = float(spy_bars[-1]['close']) if spy_bars[-1]['close'] else 0.0
            
            if spy_price == 0:
                logger.warning("⚠️ SPY price is 0 - assuming market unhealthy")
                self.spy_qualified = False
                return False
            
            # Calculate SPY 50-day MA - convert all Decimals to floats
            spy_closes = [float(bar['close']) for bar in spy_bars if bar['close']]
            spy_ma_50 = self._calculate_sma(spy_closes, 50)
            
            if spy_ma_50 is None:
                logger.warning("⚠️ Could not calculate SPY 50-day MA")
                self.spy_qualified = False
                return False
            
            # Check if SPY is above its 50-day MA
            self.spy_qualified = spy_price > spy_ma_50
            
            status = "✅ HEALTHY" if self.spy_qualified else "❌ UNHEALTHY"
            logger.info(f"SPY: ${spy_price:.2f} | 50-day MA: ${spy_ma_50:.2f} | Market: {status}")
            
            return self.spy_qualified
            
        except Exception as e:
            logger.error(f"❌ Error checking SPY health: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.spy_qualified = False
            return False
    
    def scan_all_tickers(self) -> List[Dict]:
        """
        Scan all active tickers and return results.

        Price source priority:
          1. IB live price (fetched in a single batch call before the loop)
          2. Latest closing price from the database (fallback if IB unavailable)

        Historical bars (used for MA / 52-week calculations) always come from
        the database — fetching 250+ bars per ticker from IB live would be
        extremely slow and is unnecessary.

        Returns:
            List of scan results for all tickers
        """
        # Step 1: Check SPY health first (criterion #8)
        if not self.check_spy_health():
            logger.warning("⚠️ SPY is below 50-day MA - NO stocks will qualify (market health failed)")

        # Step 2: Get active tickers
        tickers = self.db.get_active_tickers()

        if not tickers:
            logger.warning("⚠️ No active tickers to scan")
            return []

        logger.info(f"Scanning {len(tickers)} tickers...")

        # Step 3: Batch-fetch all live prices from IB in one call.
        # This is far faster than fetching per-symbol (one round-trip vs 90+).
        live_prices = {}
        if self.fetcher.connected:
            logger.info(f"📡 Fetching live prices from IB for {len(tickers)} tickers...")
            try:
                live_prices = self.fetcher.fetch_multiple_prices(tickers)
                logger.info(f"✅ Got live IB prices for {len(live_prices)}/{len(tickers)} tickers")
            except Exception as e:
                logger.warning(f"⚠️ IB batch price fetch failed — will fall back to DB prices: {e}")
        else:
            logger.warning("⚠️ IB not connected — using database closing prices as current price")

        results = []

        for i, symbol in enumerate(tickers, 1):
            try:
                logger.info(f"[{i}/{len(tickers)}] Scanning {symbol}...")

                # Get historical bars from database (needed for MA / 52-week calcs)
                bars = self.db.get_daily_bars(symbol, limit=300)

                if not bars or len(bars) < 250:
                    logger.warning(f"⚠️ {symbol}: Insufficient historical data in database ({len(bars) if bars else 0} bars)")
                    results.append(self._failed_result(symbol, "No data"))
                    continue

                # Reverse to get chronological order (oldest to newest)
                bars.reverse()

                latest_bar = bars[-1]

                # Use IB live price when available, otherwise fall back to DB close.
                # Guard against nan/inf which IB can return for illiquid/halted symbols.
                import math
                ib_price = live_prices.get(symbol)
                if ib_price is not None and not math.isnan(float(ib_price)) and not math.isinf(float(ib_price)):
                    current_price = float(ib_price)
                    price_source = "IB-live"
                else:
                    current_price = float(latest_bar['close']) if latest_bar['close'] else 0.0
                    price_source = "DB-close"

                # Volume still comes from the latest DB bar (IB intraday volume
                # is not meaningful for the daily-volume breakout criterion)
                current_volume = int(latest_bar['volume']) if latest_bar['volume'] else 0

                if current_price == 0:
                    logger.warning(f"⚠️ {symbol}: Price is 0, skipping")
                    results.append(self._failed_result(symbol, "Invalid price"))
                    continue

                logger.info(f"{symbol}: Price=${current_price:.2f} ({price_source}), Volume={current_volume:,}")

                # Calculate criteria
                result = self.calculate_criteria(symbol, bars, current_price, current_volume)
                results.append(result)

                # Save to database
                self.db.save_scan_result(result)

                # Log if qualified
                if result['qualified']:
                    logger.info(f"✅ {symbol} QUALIFIED - All 8 criteria met!")

            except Exception as e:
                logger.error(f"❌ Error scanning {symbol}: {e}")
                results.append(self._failed_result(symbol, str(e)))

        # Summary
        qualified_count = sum(1 for r in results if r['qualified'])
        logger.info(f"✅ Scan complete: {qualified_count}/{len(results)} stocks qualified")

        return results
    
    def get_qualified_stocks(self, results: List[Dict]) -> List[str]:
        """Get list of symbols that qualified."""
        return [r['symbol'] for r in results if r['qualified']]
    
    def _calculate_sma(self, values: List[float], period: int) -> Optional[float]:
        """Calculate Simple Moving Average."""
        if len(values) < period:
            return None
        return sum(values[-period:]) / period
    
    def _failed_result(self, symbol: str, reason: str) -> Dict:
        """Create a failed scan result."""
        return {
            'scan_date': date.today(),
            'symbol': symbol,
            'price': 0,
            'week_52_high': 0,
            'week_52_low': 0,
            'ma_50': 0,
            'ma_150': 0,
            'ma_200': 0,
            'ma_200_1m_ago': 0,
            'volume': 0,
            'avg_volume_50': 0,
            'criteria_1': False,
            'criteria_2': False,
            'criteria_3': False,
            'criteria_4': False,
            'criteria_5': False,
            'criteria_6': False,
            'criteria_7': False,
            'criteria_8': False,
            'qualified': False,
            'action': f'FAIL: {reason}'
        }


class PositionMonitor:
    """Monitors open positions for exit triggers."""
    
    def __init__(self, db: Database, fetcher: DataFetcher):
        self.db = db
        self.fetcher = fetcher
    
    def check_exit_triggers(self) -> List[Dict]:
        """
        Check all open positions for exit triggers:
        1. Stop loss hit (price <= stop_loss)
        2. Trend break (price < 50-day MA)
        
        Returns:
            List of positions that need to exit with reason
        """
        positions = self.db.get_positions()
        
        if not positions:
            return []
        
        exits_needed = []
        
        for pos in positions:
            symbol = pos['symbol']
            
            try:
                import math
                # Get current price
                raw_price = self.fetcher.fetch_current_price(symbol)

                # Guard against None, zero, nan, inf (IB can return these for halted symbols)
                if not raw_price:
                    logger.warning(f"⚠️ Could not fetch price for {symbol}")
                    continue
                raw_price = float(raw_price)
                if math.isnan(raw_price) or math.isinf(raw_price) or raw_price <= 0:
                    logger.warning(f"⚠️ Invalid price for {symbol}: {raw_price}")
                    continue
                current_price = raw_price

                # Check stop loss (convert Decimal DB value to float for comparison)
                stop_loss = float(pos['stop_loss'])
                if current_price <= stop_loss:
                    exits_needed.append({
                        'symbol': symbol,
                        'position': pos,
                        'current_price': current_price,
                        'reason': 'STOP_LOSS',
                        'trigger_price': stop_loss
                    })
                    logger.warning(f"🛑 {symbol} hit STOP LOSS: ${current_price:.2f} <= ${stop_loss:.2f}")
                    continue

                # Check 50-day MA break
                bars = self.db.get_daily_bars(symbol, limit=60)

                if bars and len(bars) >= 50:
                    bars.reverse()  # Chronological order
                    # Convert Decimal DB values to float and skip None rows
                    closes = [float(bar['close']) for bar in bars if bar['close']]
                    ma_50 = sum(closes[-50:]) / 50

                    if current_price < ma_50:
                        exits_needed.append({
                            'symbol': symbol,
                            'position': pos,
                            'current_price': current_price,
                            'reason': 'TREND_BREAK',
                            'trigger_price': ma_50
                        })
                        logger.warning(f"🛑 {symbol} TREND BREAK: ${current_price:.2f} < 50-day MA ${ma_50:.2f}")
                
            except Exception as e:
                logger.error(f"❌ Error checking exits for {symbol}: {e}")
        
        return exits_needed
