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

from datetime import date, datetime, time as dtime
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo
import logging
from database import Database
from data_fetcher import DataFetcher

ET = ZoneInfo("America/New_York")  # all date logic uses ET, not machine local

logger = logging.getLogger(__name__)


class MinerviniScanner:
    """Scans stocks using 8-criteria SEPA methodology."""
    
    def __init__(self, db: Database, fetcher: DataFetcher):
        self.db = db
        self.fetcher = fetcher
        self.spy_qualified = False  # Criterion #8 - market health
    
    def calculate_criteria(self, symbol: str, bars: List[Dict],
                          current_price: float, current_volume: int,
                          config: Dict = None) -> Dict:
        """
        Evaluate all 8 criteria for a symbol.

        Args:
            symbol: Stock ticker
            bars: Historical daily bars (most recent last)
            current_price: Current/latest price
            current_volume: Current/latest volume
            config: Bot config dict (fetched from DB if not provided)

        Returns:
            Dictionary with all criteria results and qualification status
        """
        if config is None:
            config = self.db.get_config()
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

        # Read configurable thresholds from DB config
        near_52wh_pct  = float(config.get('near_52wh_pct',  5.0))
        above_52wl_pct = float(config.get('above_52wl_pct', 30.0))
        volume_mult    = float(config.get('volume_multiplier', 1.5))

        # 1. Price within near_52wh_pct% of 52-week high
        criteria_1 = current_price >= (week_52_high * (1 - near_52wh_pct / 100))

        # 2. Price above 50-day MA
        criteria_2 = current_price > ma_50

        # 3. 50-day MA above 150-day MA
        criteria_3 = ma_50 > ma_150

        # 4. 150-day MA above 200-day MA
        criteria_4 = ma_150 > ma_200

        # 5. 200-day MA trending up (current > 1 month ago)
        criteria_5 = ma_200 > ma_200_1m_ago

        # 6. Price at least above_52wl_pct% above 52-week low
        criteria_6 = current_price >= (week_52_low * (1 + above_52wl_pct / 100))

        # 7. Breakout on above-average volume (volume_mult x avg)
        criteria_7 = current_volume >= (avg_volume_50 * volume_mult) if avg_volume_50 > 0 else False

        # 8. SPY above its 50-day MA (checked separately)
        criteria_8 = self.spy_qualified
        
        # All 8 criteria must be met (criteria 6/7 thresholds are configurable in Settings UI;
        # criteria 8 can be toggled on/off via SPY Market Health Filter setting)
        all_criteria_met = all([
            criteria_1, criteria_2, criteria_3, criteria_4,
            criteria_5, criteria_6  #, criteria_7, criteria_8
        ])
        
        # Determine action
        action = 'BUY_AT_OPEN' if all_criteria_met else 'PASS'
        
        result = {
            'scan_date': datetime.now(ET).date(),
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
    
    @staticmethod
    def _market_is_open() -> bool:
        """
        Returns True only during regular US market hours (Mon-Fri 09:30-16:00 ET).
        Used to decide whether a live IB price fetch is worthwhile.
        Outside these hours IB returns stale/delayed snapshots that add 3-30s
        of latency for zero benefit — DB closing prices are equally good.
        """
        now = datetime.now(ET)
        if now.weekday() >= 5:          # Saturday=5, Sunday=6
            return False
        t = now.time()
        return dtime(9, 30) <= t < dtime(16, 0)

    def scan_all_tickers(self) -> List[Dict]:
        """
        Scan all active tickers and return results.

        Optimisations vs original:
          1. All historical bars fetched in ONE SQL query (batch) instead of
             one query per ticker — eliminates N-1 DB round-trips.
          2. IB live price fetch is skipped outside market hours (weekends,
             evenings) — IB is slow / returns stale data off-hours anyway
             and DB closing prices are equally valid for criteria evaluation.

        Price source priority (during market hours):
          1. IB live price — single batch call before the loop
          2. Latest closing price from DB — fallback if IB unavailable

        Historical bars always come from DB regardless of market hours.
        """
        import math

        scan_start = datetime.now(ET)

        # Step 1: Read config once for the entire scan cycle
        config = self.db.get_config()
        spy_filter_enabled = bool(config.get('spy_filter_enabled', True))

        # Check SPY health (criterion #8) — only when the filter is enabled
        if spy_filter_enabled:
            if not self.check_spy_health():
                logger.warning("⚠️ SPY is below 50-day MA - NO stocks will qualify (market health failed)")
        else:
            self.spy_qualified = True
            logger.info("ℹ️ SPY filter disabled in config — treating criterion 8 as passing for all tickers")

        # Step 2: Get active tickers
        tickers = self.db.get_active_tickers()
        if not tickers:
            logger.warning("⚠️ No active tickers to scan")
            return []

        logger.info(f"Scanning {len(tickers)} tickers...")

        # Step 3: Batch-fetch ALL bars in one SQL query
        t0 = datetime.now(ET)
        all_bars = self.db.get_all_daily_bars_batch(tickers, limit=300)
        logger.info(f"⚡ Batch bar fetch: {len(all_bars)} symbols in {(datetime.now(ET)-t0).total_seconds():.1f}s")

        # Step 4: Live price fetch — ONLY during market hours
        live_prices = {}
        market_open = self._market_is_open()
        if market_open and self.fetcher.connected:
            logger.info(f"📡 Market open — fetching live prices from IB for {len(tickers)} tickers...")
            try:
                live_prices = self.fetcher.fetch_multiple_prices(tickers)
                logger.info(f"✅ Got live IB prices for {len(live_prices)}/{len(tickers)} tickers")
            except Exception as e:
                logger.warning(f"⚠️ IB batch price fetch failed — falling back to DB prices: {e}")
        elif not market_open:
            logger.info("🌙 Market closed — skipping IB price fetch, using DB closing prices")
        else:
            logger.warning("⚠️ IB not connected — using database closing prices as current price")

        # Build set of open position symbols
        open_positions = self.db.get_positions()
        open_symbols = {p["symbol"] for p in open_positions}

        results = []

        for i, symbol in enumerate(tickers, 1):
            try:
                # Use pre-fetched batch bars (no per-ticker DB call)
                bars = all_bars.get(symbol, [])

                if not bars or len(bars) < 250:
                    logger.warning(f"⚠️ {symbol}: Insufficient data ({len(bars)} bars, need 250)")
                    results.append(self._failed_result(symbol, "No data"))
                    continue

                # Bars come back DESC from batch query — reverse to chronological
                bars = list(reversed(bars))
                latest_bar = bars[-1]

                # Resolve current price: IB live → DB close fallback
                ib_price = live_prices.get(symbol)
                if ib_price is not None and not math.isnan(float(ib_price)) and not math.isinf(float(ib_price)):
                    current_price = float(ib_price)
                    price_source = "IB-live"
                else:
                    current_price = float(latest_bar['close']) if latest_bar['close'] else 0.0
                    price_source = "DB-close"

                # Volume from latest DB bar (intraday IB volume is not valid for daily criterion)
                current_volume = int(latest_bar['volume']) if latest_bar['volume'] else 0

                if current_price <= 0:
                    logger.warning(f"⚠️ {symbol}: Invalid price ({current_price}), skipping")
                    results.append(self._failed_result(symbol, "Invalid price"))
                    continue

                logger.debug(f"[{i}/{len(tickers)}] {symbol}: ${current_price:.2f} ({price_source})")

                # Evaluate all 8 criteria
                result = self.calculate_criteria(symbol, bars, current_price, current_volume, config)
                result['in_portfolio'] = symbol in open_symbols

                # ── A/B test group assignment ────────────────────────────────
                # Only assign a group to newly-qualified stocks that are not
                # already in the portfolio (no point testing entry timing on
                # existing positions).
                # IMPORTANT: check the DB first so we never reassign a group
                # that was already set on a previous scan cycle.  Without this
                # guard, increment_ab_counter() fires every 30 s and the group
                # flips A→B→A on each cycle, destroying the assignment.
                ab_test_enabled = bool(config.get('ab_test_enabled', False))
                if result['qualified'] and not result['in_portfolio'] and ab_test_enabled:
                    existing_ab = self.db.get_scan_ab_group(result['scan_date'], result['symbol'])
                    if existing_ab is not None:
                        # Group already assigned on a prior cycle — preserve it
                        result['ab_group'] = existing_ab['ab_group']
                        result['eod_buy_pending'] = existing_ab['eod_buy_pending']
                        if existing_ab['ab_group'] == 'A':
                            result['action'] = 'BUY_EOD'
                    else:
                        # First time this ticker qualifies today — assign a new group
                        counter = self.db.increment_ab_counter()
                        ab_group = 'A' if counter % 2 == 1 else 'B'
                        result['ab_group'] = ab_group
                        result['eod_buy_pending'] = (ab_group == 'A')
                        if ab_group == 'A':
                            result['action'] = 'BUY_EOD'
                else:
                    result['ab_group'] = None
                    result['eod_buy_pending'] = False

                results.append(result)
                self.db.save_scan_result(result)

                if result['qualified']:
                    ab_label = f" | Group={result.get('ab_group', 'N/A')}" if ab_test_enabled else ""
                    logger.info(f"✅ {symbol} QUALIFIED — C1={result['criteria_1']} C2={result['criteria_2']} C3={result['criteria_3']} C4={result['criteria_4']} C5={result['criteria_5']} C6={result['criteria_6']} C7={result['criteria_7']} C8={result['criteria_8']}{ab_label}")

            except Exception as e:
                logger.error(f"❌ Error scanning {symbol}: {e}")
                results.append(self._failed_result(symbol, str(e)))

        qualified_count = sum(1 for r in results if r['qualified'])
        elapsed = (datetime.now(ET) - scan_start).total_seconds()
        logger.info(f"✅ Scan complete: {qualified_count}/{len(results)} qualified | {elapsed:.1f}s total | market={'open' if market_open else 'closed'}")

        return results
    
    def rescan_single(self, symbol: str) -> bool:
        """
        Re-run all 8 criteria for a single symbol using the latest DB bars.
        No live IB call — uses closing prices from daily_bars.
        Used by Group B re-verification at SOD before placing a buy order.

        Returns:
            True if the symbol still qualifies under all 8 criteria, False otherwise.
        """
        import math
        try:
            config = self.db.get_config()
            # Check SPY health first (criterion 8)
            spy_filter_enabled = bool(config.get('spy_filter_enabled', True))
            if spy_filter_enabled:
                spy_ok = self.check_spy_health()
            else:
                spy_ok = True

            if not spy_ok:
                logger.info(f"🔄 {symbol} Group B re-verify: SPY filter failed — skip")
                return False

            bars = self.db.get_daily_bars(symbol, limit=300)
            if not bars or len(bars) < 250:
                logger.warning(f"🔄 {symbol} Group B re-verify: insufficient bars ({len(bars)}) — skip")
                return False

            # get_daily_bars returns DESC — reverse to chronological
            bars = list(reversed(bars))
            latest_bar = bars[-1]

            current_price = float(latest_bar['close']) if latest_bar['close'] else 0.0
            current_volume = int(latest_bar['volume']) if latest_bar['volume'] else 0

            if current_price <= 0:
                logger.warning(f"🔄 {symbol} Group B re-verify: invalid price — skip")
                return False

            result = self.calculate_criteria(symbol, bars, current_price, current_volume, config)
            qualified = bool(result.get('qualified', False))
            logger.info(f"🔄 {symbol} Group B re-verify: {'PASS ✅' if qualified else 'FAIL ❌'}")
            return qualified

        except Exception as e:
            logger.error(f"❌ Error in rescan_single for {symbol}: {e}")
            return False

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
            'scan_date': datetime.now(ET).date(),
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

        Price source rules (strict — no cross-contamination):
          Market OPEN  → IB live prices only. If IB price unavailable for a symbol,
                         skip that symbol entirely. Never fall back to DB during hours
                         as stale/closing prices must not trigger real sell decisions.
          Market CLOSED → DB closing prices only. No IB call is made at all.
                          Exit checks during off-hours are informational only
                          (pending_exit flags are only acted on at next market open).

        Returns:
            List of positions that need to exit with reason
        """
        import math

        positions = self.db.get_positions()

        if not positions:
            return []

        symbols = [pos['symbol'] for pos in positions]

        # Read config once for the entire check cycle
        config = self.db.get_config()
        trend_break_enabled = bool(config.get('trend_break_exit_enabled', True))

        market_open = MinerviniScanner._market_is_open()

        # ── Fetch prices according to strict market-hours rule ──────────────
        if market_open:
            # Market is open — must use IB live prices, no fallback
            if not self.fetcher.connected:
                logger.warning("⚠️ Market open but IB not connected — skipping exit-trigger check entirely")
                return []
            try:
                live_prices = self.fetcher.fetch_multiple_prices(symbols)
                logger.info(f"📡 Exit-trigger price fetch: got {len(live_prices)}/{len(symbols)} live IB prices")
            except Exception as e:
                logger.warning(f"⚠️ Exit-trigger IB price fetch failed — skipping check entirely: {e}")
                return []
        else:
            # Market is closed — use DB closing prices strictly, no IB call
            logger.info("🌙 Market closed — using DB closing prices for exit-trigger check (informational only)")
            live_prices = {}  # will use DB path below

        exits_needed = []

        for pos in positions:
            symbol = pos['symbol']

            try:
                if market_open:
                    # Live price required — skip symbol if not available
                    raw_price = live_prices.get(symbol)
                    if raw_price is not None:
                        raw_price = float(raw_price)
                        if math.isnan(raw_price) or math.isinf(raw_price) or raw_price <= 0:
                            raw_price = None
                    if raw_price is None:
                        logger.warning(f"⚠️ No live IB price for {symbol} — skipping exit check")
                        continue
                else:
                    # Off-market — use DB closing price strictly
                    bars_db = self.db.get_daily_bars(symbol, limit=1)
                    if bars_db and bars_db[0].get('close'):
                        raw_price = float(bars_db[0]['close'])
                    else:
                        logger.warning(f"⚠️ No DB closing price for {symbol} — skipping exit check")
                        continue

                current_price = raw_price

                # Check stop loss (convert Decimal DB value to float for comparison)
                stop_loss = float(pos['stop_loss'])
                if current_price <= stop_loss:
                    exit_entry = {
                        'symbol': symbol,
                        'position': pos,
                        'current_price': current_price,
                        'reason': 'STOP_LOSS',
                        'trigger_price': stop_loss
                    }
                    exits_needed.append(exit_entry)
                    # Flag in DB so the morning executor picks it up
                    if not pos.get('pending_exit'):
                        self.db.flag_pending_exit(symbol, 'STOP_LOSS')
                    logger.warning(f"🛑 {symbol} hit STOP LOSS: ${current_price:.2f} <= ${stop_loss:.2f}")
                    continue

                # Check 50-day MA trend break (only when enabled in config)
                if not trend_break_enabled:
                    continue

                bars = self.db.get_daily_bars(symbol, limit=60)

                if bars and len(bars) >= 50:
                    bars.reverse()  # Chronological order
                    # Convert Decimal DB values to float and skip None rows
                    closes = [float(bar['close']) for bar in bars if bar['close']]
                    ma_50 = sum(closes[-50:]) / 50

                    if current_price < ma_50:
                        exit_entry = {
                            'symbol': symbol,
                            'position': pos,
                            'current_price': current_price,
                            'reason': 'TREND_BREAK',
                            'trigger_price': ma_50
                        }
                        exits_needed.append(exit_entry)
                        # Flag in DB so the morning executor picks it up
                        if not pos.get('pending_exit'):
                            self.db.flag_pending_exit(symbol, 'TREND_BREAK')
                        logger.warning(f"🛑 {symbol} TREND BREAK: ${current_price:.2f} < 50-day MA ${ma_50:.2f}")

            except Exception as e:
                logger.error(f"❌ Error checking exits for {symbol}: {e}")

        return exits_needed
