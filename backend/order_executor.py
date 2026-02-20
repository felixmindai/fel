"""
Order Executor for Minervini Trading Bot
=========================================

Handles automatic buy and sell execution at market open.

Buy logic (called at configured order_execution_time, set in Settings UI):
  - Queries today's scan_results for qualified=true, override=false stocks
  - Skips symbols already in an open position
  - Skips if max_positions is already reached
  - Calculates quantity: floor(position_size_usd / entry_price), minimum 1
  - Resolves entry price per entry_method:
      market_open  -> fetch live real-time price from IB at execution time
      prev_close   -> use previous day's closing price from DB
      limit_1pct   -> 1% above previous day's closing price from DB
  - Places IB order (paper port 7496 or live port 7497 as configured in .env)
  - Records position + trade in DB after successful IB order placement

Sell logic (also called at order_execution_time):
  - Queries positions where pending_exit=true (flagged by PositionMonitor)
  - Fetches live price from IB — skips symbol entirely if no live price available
  - Places IB market sell order + closes position + trade in DB

Both buy and sell broadcast WebSocket messages when executed.
"""

import asyncio
import json
import logging
import math
from datetime import datetime, date as date_type
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    pass  # BotState imported at runtime inside functions to avoid circular import

ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WebSocket broadcast helper (mirrors data_updater._broadcast_update)
# ---------------------------------------------------------------------------

async def _broadcast(bot_state, message: dict) -> None:
    """Send a JSON message to all connected WebSocket clients."""
    payload = json.dumps(message)
    dead = []
    for ws in list(getattr(bot_state, "websocket_clients", set())):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        bot_state.websocket_clients.discard(ws)


# ---------------------------------------------------------------------------
# Entry price resolver
# ---------------------------------------------------------------------------

def _resolve_entry_price(entry_method: str, prev_close: float, live_price: float | None,
                         limit_premium_pct: float = 1.0) -> float | None:
    """
    Return the entry price to use based on entry_method.

    Args:
        entry_method:       'market_open' | 'prev_close' | 'limit_1pct'
        prev_close:         Previous day's closing price from DB
        live_price:         Real-time price fetched from IB (may be None if IB unavailable)
        limit_premium_pct:  % above prev_close for limit_1pct method (from config, default 1.0)

    Returns:
        Resolved price, or None if prev_close is also unavailable.

    Fallback behaviour:
        market_open — uses IB live price when available; falls back to prev_close
        and logs a warning when IB real-time data is not subscribed or unavailable.
        This requires an IB real-time data subscription for accurate fills in
        production; delayed/unavailable data silently degrades to prev_close.
    """
    if entry_method == "market_open":
        if live_price and not math.isnan(live_price) and live_price > 0:
            return live_price
        # Fall back to prev_close rather than skipping the trade entirely
        if prev_close and prev_close > 0:
            logger.warning(
                f"market_open: IB live price unavailable (real-time subscription required) "
                f"— falling back to prev_close (${prev_close:.2f})"
            )
            return prev_close
        return None

    if entry_method == "limit_1pct":
        return round(prev_close * (1 + limit_premium_pct / 100), 4)

    # Default: prev_close
    return prev_close


# ---------------------------------------------------------------------------
# Buy execution
# ---------------------------------------------------------------------------

async def execute_pending_buys(bot_state) -> list:
    """
    SOD buy executor — runs at the configured order_execution_time (default ~09:45 ET).

    When A/B test is OFF (default): executes all of today's qualified candidates
    (same behaviour as before).

    When A/B test is ON: executes only Group B candidates from YESTERDAY's scan.
    Group B candidates are re-verified with a full fresh criteria check before buying.
    Candidates that fail re-verify or gap up > 10% are skipped with a reason stored
    in scan_results.sod_skip_reason.

    Returns list of dicts describing each executed buy (for logging / WS broadcast).
    """
    db = bot_state.db
    fetcher = bot_state.fetcher
    config = db.get_config()
    ab_test_enabled = bool(config.get("ab_test_enabled", False))

    if not config.get("auto_execute"):
        logger.info("Auto-execute is OFF — skipping SOD buy execution")
        return []

    today = datetime.now(ET).date()
    max_positions = int(config.get("max_positions") or 16)
    position_size_usd = float(config.get("position_size_usd") or 10000)
    stop_loss_pct = float(config.get("stop_loss_pct") or 8.0)
    paper_trading = bool(config.get("paper_trading", True))
    default_entry_method = config.get("default_entry_method") or "prev_close"
    limit_premium_pct = float(config.get("limit_order_premium_pct") or 1.0)

    # Current open positions
    open_positions = db.get_positions()
    open_symbols = {p["symbol"] for p in open_positions}
    current_count = len(open_positions)

    if current_count >= max_positions:
        logger.info(f"Portfolio full ({current_count}/{max_positions}) — no SOD buys today")
        return []

    if ab_test_enabled:
        # A/B mode: Group B candidates from yesterday's scan, re-verified fresh
        from datetime import timedelta
        yesterday = today - timedelta(days=1)
        raw_candidates = db.get_sod_group_b_candidates(yesterday)
        logger.info(f"🅱️ A/B SOD: found {len(raw_candidates)} Group B candidates from {yesterday}")
        candidates = []
        for r in raw_candidates:
            if r.get("symbol") not in open_symbols:
                candidates.append(r)
    else:
        # Normal mode: today's qualified, non-overridden scan results (all groups)
        scan_results = db.get_latest_scan_results()
        candidates = []
        for r in scan_results:
            # Normalize scan_date
            scan_date = r.get("scan_date")
            if isinstance(scan_date, str):
                try:
                    scan_date = date_type.fromisoformat(scan_date)
                except (ValueError, TypeError):
                    scan_date = None
            if (
                r.get("qualified")
                and not r.get("override")
                and r.get("symbol") not in open_symbols
                and scan_date == today
            ):
                candidates.append(r)

    if not candidates:
        logger.info("No qualified candidates to buy today")
        return []

    # Batch-fetch live prices once for all candidates (needed for market_open method)
    candidate_symbols = [r["symbol"] for r in candidates]
    live_prices: dict = {}
    if fetcher.connected:
        try:
            loop = asyncio.get_event_loop()
            live_prices = await loop.run_in_executor(
                None,
                lambda: fetcher.fetch_multiple_prices(candidate_symbols)
            )
            logger.info(f"Fetched live open prices for {len(live_prices)}/{len(candidate_symbols)} symbols")
        except Exception as e:
            logger.warning(f"Live price fetch failed during buy execution: {e}")
    else:
        logger.warning("IB not connected — market_open candidates will be skipped")

    executed = []

    for result in candidates:
        if current_count >= max_positions:
            logger.info(f"Max positions reached ({max_positions}) — stopping buy loop")
            break

        symbol = result["symbol"]
        scan_date = result.get("scan_date")
        entry_method = result.get("entry_method") or default_entry_method
        prev_close = float(result.get("price") or 0)

        if prev_close <= 0:
            logger.warning(f"{symbol}: prev_close price is 0 — skipping")
            continue

        live_price = live_prices.get(symbol)
        if live_price:
            live_price = float(live_price)
            if math.isnan(live_price) or math.isinf(live_price) or live_price <= 0:
                live_price = None

        # ── Group B SOD re-verification ──────────────────────────────────────
        # For Group B candidates, run a full fresh criteria check before buying.
        # Also skip if the overnight gap-up is > 10% (paying too high a premium).
        if ab_test_enabled and result.get("ab_group") == "B":
            scanner = getattr(bot_state, "scanner", None)
            if scanner is None:
                logger.warning(f"{symbol}: scanner not available for Group B re-verify — skipping")
                db.mark_sod_skip(symbol, scan_date, "NO_SCANNER")
                continue
            loop = asyncio.get_event_loop()
            still_qualifies = await loop.run_in_executor(None, lambda s=symbol: scanner.rescan_single(s))
            if not still_qualifies:
                logger.info(f"🅱️ {symbol}: Group B re-verify FAILED — skipping (CRITERIA_FAILED)")
                db.mark_sod_skip(symbol, scan_date, "CRITERIA_FAILED")
                continue
            # Gap-up guard: if live price is >10% above yesterday's close, skip
            GAP_UP_THRESHOLD = 1.10
            if live_price and prev_close and live_price > prev_close * GAP_UP_THRESHOLD:
                gap_pct = ((live_price - prev_close) / prev_close) * 100
                logger.warning(
                    f"🅱️ {symbol}: Group B gap-up too large (+{gap_pct:.1f}%) — skipping (GAP_UP_EXCESSIVE)"
                )
                db.mark_sod_skip(symbol, scan_date, "GAP_UP_EXCESSIVE")
                continue
            # Group B always uses market_open for entry
            entry_method = "market_open"
            logger.info(f"🅱️ {symbol}: Group B re-verify PASSED — proceeding with market_open buy")

        entry_price = _resolve_entry_price(entry_method, prev_close, live_price, limit_premium_pct)
        if entry_price is None or entry_price <= 0:
            logger.warning(f"{symbol}: Could not resolve entry price (method={entry_method}) — skipping")
            continue

        quantity = max(1, int(position_size_usd / entry_price))
        cost_basis = round(entry_price * quantity, 2)
        stop_loss = round(entry_price * (1 - stop_loss_pct / 100), 4)
        entry_date = today

        try:
            # ----------------------------------------------------------------
            # PLACE IB ORDER
            # Paper vs live is determined by the IB port in .env (7496=paper,
            # 7497=live TWS). The API call is identical either way.
            # ----------------------------------------------------------------
            ib_order = None
            if fetcher.connected:
                loop = asyncio.get_event_loop()
                if entry_method == "market_open":
                    ib_order = await loop.run_in_executor(
                        None,
                        lambda s=symbol, q=quantity: fetcher.place_market_order(s, q, "BUY")
                    )
                else:
                    # prev_close or limit_1pct — both use a limit order
                    ib_order = await loop.run_in_executor(
                        None,
                        lambda s=symbol, q=quantity, p=entry_price: fetcher.place_limit_order(s, q, "BUY", p)
                    )

                if ib_order is None:
                    logger.error(f"IB order placement failed for {symbol} — skipping DB record")
                    continue
            else:
                logger.warning(f"IB not connected — skipping {symbol} buy (cannot place order)")
                continue

            # ----------------------------------------------------------------
            # RECORD IN DB (always — regardless of paper/live mode)
            # entry_price   = actual IB fill price (avg_fill_price from poll)
            # submitted_price = the limit/prev_close price we originally sent
            #
            # avg_fill_price comes back as 0.0 if the order polled out without
            # a fill confirmation (e.g. limit not yet filled); fall back to
            # entry_price so we still record something meaningful.
            # ----------------------------------------------------------------
            submitted_price = entry_price  # what we sent IB (limit or prev_close)
            raw_fill = ib_order.get("avg_fill_price") or 0.0
            if raw_fill and raw_fill > 0:
                filled_price = float(raw_fill)
                logger.info(
                    f"  {symbol}: IB confirmed fill @ ${filled_price:.4f} "
                    f"(submitted ${submitted_price:.4f})"
                )
            else:
                filled_price = submitted_price
                logger.warning(
                    f"  {symbol}: No fill confirmation from IB — "
                    f"recording submitted price ${submitted_price:.4f} as entry price"
                )
            actual_cost_basis = round(filled_price * quantity, 2)

            trade = {
                "symbol": symbol,
                "entry_date": entry_date,
                "entry_price": filled_price,       # actual fill
                "submitted_price": submitted_price, # what we asked IB to fill at
                "quantity": quantity,
                "cost_basis": actual_cost_basis,
            }
            trade_id = db.create_trade(trade)
            if trade_id is None:
                logger.error(f"Failed to create trade record for {symbol}")
                continue

            pos = {
                "symbol": symbol,
                "entry_date": entry_date,
                "entry_price": filled_price,       # actual fill
                "submitted_price": submitted_price, # for audit / display
                "quantity": quantity,
                "stop_loss": round(filled_price * (1 - stop_loss_pct / 100), 4),
                "cost_basis": actual_cost_basis,
                "trade_id": trade_id,
            }
            if not db.save_position(pos):
                logger.error(f"Failed to save position for {symbol}")
                continue

            # Mark this symbol as in-portfolio in scan_results so the
            # first frontend fetch already has the correct flag (no flash)
            db.update_scan_result_portfolio_flag(symbol, True)

            current_count += 1
            mode = "PAPER" if paper_trading else "LIVE"
            logger.info(
                f"✅ [{mode}] BUY {symbol}: {quantity} shares "
                f"@ fill=${filled_price:.2f} (submitted=${submitted_price:.2f}, "
                f"method={entry_method}, stop=${pos['stop_loss']:.2f}, "
                f"ib_order_id={ib_order.get('order_id')})"
            )

            executed.append({
                "symbol": symbol,
                "quantity": quantity,
                "entry_price": filled_price,
                "submitted_price": submitted_price,
                "entry_method": entry_method,
                "stop_loss": pos["stop_loss"],
                "cost_basis": actual_cost_basis,
                "ib_order_id": ib_order.get("order_id"),
                "ib_status": ib_order.get("status"),
                "mode": mode,
            })

        except Exception as e:
            logger.error(f"❌ Error executing buy for {symbol}: {e}")

    return executed


# ---------------------------------------------------------------------------
# Sell execution
# ---------------------------------------------------------------------------


async def execute_eod_buys(bot_state) -> list:
    """
    EOD buy executor — runs at the configured eod_order_execution_time (default ~15:50 ET).
    Only active when ab_test_enabled = true.

    Picks up all Group A candidates flagged with eod_buy_pending=true,
    buys them immediately using live IB market price, then clears the flag.

    Returns list of dicts describing each executed buy (for logging / WS broadcast).
    """
    db = bot_state.db
    fetcher = bot_state.fetcher
    config = db.get_config()

    if not config.get("auto_execute"):
        logger.info("Auto-execute is OFF — skipping EOD buy execution")
        return []

    if not config.get("ab_test_enabled"):
        logger.info("A/B test is OFF — skipping EOD buy execution")
        return []

    max_positions = int(config.get("max_positions") or 16)
    position_size_usd = float(config.get("position_size_usd") or 10000)
    stop_loss_pct = float(config.get("stop_loss_pct") or 8.0)
    paper_trading = bool(config.get("paper_trading", True))

    open_positions = db.get_positions()
    open_symbols = {p["symbol"] for p in open_positions}
    current_count = len(open_positions)

    if current_count >= max_positions:
        logger.info(f"Portfolio full ({current_count}/{max_positions}) — no EOD buys")
        return []

    candidates = [c for c in db.get_eod_buy_candidates() if c.get("symbol") not in open_symbols]
    if not candidates:
        logger.info("No Group A EOD candidates to buy")
        return []

    # Batch-fetch live prices — EOD buys always use market_open (live IB price)
    candidate_symbols = [r["symbol"] for r in candidates]
    live_prices: dict = {}
    if fetcher.connected:
        try:
            loop = asyncio.get_event_loop()
            live_prices = await loop.run_in_executor(
                None,
                lambda: fetcher.fetch_multiple_prices(candidate_symbols)
            )
            logger.info(f"📡 EOD: fetched live prices for {len(live_prices)}/{len(candidate_symbols)} symbols")
        except Exception as e:
            logger.warning(f"EOD live price fetch failed: {e}")
    else:
        logger.warning("IB not connected — cannot execute EOD buys")
        return []

    executed = []
    today = datetime.now(ET).date()

    for result in candidates:
        if current_count >= max_positions:
            break

        symbol = result["symbol"]
        scan_date = result.get("scan_date")
        prev_close = float(result.get("price") or 0)

        live_price = live_prices.get(symbol)
        if live_price:
            live_price = float(live_price)
            if math.isnan(live_price) or math.isinf(live_price) or live_price <= 0:
                live_price = None

        # EOD buys always use live market price
        entry_price = live_price
        if not entry_price or entry_price <= 0:
            if prev_close > 0:
                entry_price = prev_close
                logger.warning(f"🅰️ {symbol}: no live price — falling back to prev_close ${prev_close:.2f}")
            else:
                logger.warning(f"🅰️ {symbol}: no price available — skipping EOD buy")
                continue

        quantity = max(1, int(position_size_usd / entry_price))
        actual_cost_basis = round(entry_price * quantity, 2)
        entry_date = today

        try:
            ib_order = None
            if fetcher.connected:
                loop = asyncio.get_event_loop()
                ib_order = await loop.run_in_executor(
                    None,
                    lambda s=symbol, q=quantity: fetcher.place_market_order(s, q, "BUY")
                )
                if ib_order is None:
                    logger.error(f"🅰️ {symbol}: IB EOD order placement failed — skipping")
                    continue
            else:
                logger.warning(f"🅰️ {symbol}: IB not connected — skipping EOD buy")
                continue

            submitted_price = entry_price
            raw_fill = ib_order.get("avg_fill_price") or 0.0
            filled_price = float(raw_fill) if raw_fill and raw_fill > 0 else submitted_price
            actual_cost_basis = round(filled_price * quantity, 2)
            stop_loss_price = round(filled_price * (1 - stop_loss_pct / 100), 4)

            trade = {
                "symbol": symbol,
                "entry_date": entry_date,
                "entry_price": filled_price,
                "submitted_price": submitted_price,
                "quantity": quantity,
                "cost_basis": actual_cost_basis,
            }
            trade_id = db.create_trade(trade)
            if trade_id is None:
                logger.error(f"🅰️ {symbol}: Failed to create trade record")
                continue

            pos = {
                "symbol": symbol,
                "entry_date": entry_date,
                "entry_price": filled_price,
                "submitted_price": submitted_price,
                "quantity": quantity,
                "stop_loss": stop_loss_price,
                "cost_basis": actual_cost_basis,
                "trade_id": trade_id,
            }
            if not db.save_position(pos):
                logger.error(f"🅰️ {symbol}: Failed to save position")
                continue

            db.update_scan_result_portfolio_flag(symbol, True)
            db.clear_eod_buy_pending(symbol, scan_date)

            current_count += 1
            mode = "PAPER" if paper_trading else "LIVE"
            logger.info(
                f"✅ 🅰️ [{mode}] EOD BUY {symbol}: {quantity} shares "
                f"@ fill=${filled_price:.2f} (stop=${stop_loss_price:.2f}, "
                f"ib_order_id={ib_order.get('order_id')})"
            )

            executed.append({
                "symbol": symbol,
                "quantity": quantity,
                "entry_price": filled_price,
                "submitted_price": submitted_price,
                "entry_method": "market_open_eod",
                "stop_loss": stop_loss_price,
                "cost_basis": actual_cost_basis,
                "ib_order_id": ib_order.get("order_id"),
                "ib_status": ib_order.get("status"),
                "mode": mode,
                "ab_group": "A",
            })

        except Exception as e:
            logger.error(f"❌ Error executing EOD buy for {symbol}: {e}")

    return executed


# ---------------------------------------------------------------------------

async def execute_pending_exits(bot_state) -> list:
    """
    Execute sell orders for all positions flagged pending_exit=true.

    Returns list of dicts describing each executed exit.
    """
    db = bot_state.db
    fetcher = bot_state.fetcher
    config = db.get_config()

    if not config.get("auto_execute"):
        logger.info("Auto-execute is OFF — skipping exit execution")
        return []

    paper_trading = bool(config.get("paper_trading", True))

    # Positions flagged for exit
    pending = db.get_pending_exit_positions()

    if not pending:
        logger.info("No pending exits today")
        return []

    # Batch-fetch live prices for all pending exits
    exit_symbols = [p["symbol"] for p in pending]
    live_prices: dict = {}
    if fetcher.connected:
        try:
            loop = asyncio.get_event_loop()
            live_prices = await loop.run_in_executor(
                None,
                lambda: fetcher.fetch_multiple_prices(exit_symbols)
            )
            logger.info(f"Fetched live exit prices for {len(live_prices)}/{len(exit_symbols)} symbols")
        except Exception as e:
            logger.warning(f"Live price fetch failed during exit execution: {e}")

    executed = []

    for pos in pending:
        symbol = pos["symbol"]

        # Resolve exit price: MUST be a live IB price — no stale DB fallback allowed.
        # Using a stale close price for an automated sell could execute at a
        # significantly wrong price. If IB live price is unavailable, skip entirely.
        raw = live_prices.get(symbol)
        if raw:
            raw = float(raw)
            exit_price = raw if (not math.isnan(raw) and not math.isinf(raw) and raw > 0) else None
        else:
            exit_price = None

        if exit_price is None:
            logger.error(
                f"⛔ {symbol}: No live IB price available — skipping automated sell. "
                f"Position remains open. Will retry on next execution cycle."
            )
            continue

        quantity = int(pos["quantity"])
        cost_basis = float(pos["cost_basis"])
        trade_id = pos.get("trade_id")
        exit_reason = pos.get("exit_reason") or "MANUAL_CLOSE"
        proceeds = round(exit_price * quantity, 2)
        pnl = round(proceeds - cost_basis, 2)
        pnl_pct = round((pnl / cost_basis) * 100, 4) if cost_basis else 0
        exit_date = datetime.now(ET).date()

        try:
            # ----------------------------------------------------------------
            # PLACE IB SELL ORDER (market order — exits are always market)
            # Paper vs live is determined by the IB port in .env.
            # ----------------------------------------------------------------
            ib_order = None
            if fetcher.connected:
                loop = asyncio.get_event_loop()
                ib_order = await loop.run_in_executor(
                    None,
                    lambda s=symbol, q=quantity: fetcher.place_market_order(s, q, "SELL")
                )
                if ib_order is None:
                    logger.error(f"IB sell order placement failed for {symbol} — skipping DB close")
                    continue
            else:
                logger.warning(f"IB not connected — skipping {symbol} exit (cannot place order)")
                continue

            # ----------------------------------------------------------------
            # CLOSE IN DB (always — regardless of paper/live mode)
            # Use IB's confirmed avg fill price; fall back to resolved exit_price
            # ----------------------------------------------------------------
            raw_exit_fill = ib_order.get("avg_fill_price") or 0.0
            if raw_exit_fill and raw_exit_fill > 0:
                filled_exit_price = float(raw_exit_fill)
                logger.info(
                    f"  {symbol}: IB confirmed sell fill @ ${filled_exit_price:.4f} "
                    f"(submitted market order, resolved price=${exit_price:.4f})"
                )
            else:
                filled_exit_price = exit_price
                logger.warning(
                    f"  {symbol}: No sell fill confirmation from IB — "
                    f"recording resolved price ${exit_price:.4f} as exit price"
                )
            if not filled_exit_price or filled_exit_price <= 0:
                filled_exit_price = exit_price
            actual_proceeds = round(filled_exit_price * quantity, 2)
            actual_pnl = round(actual_proceeds - cost_basis, 2)
            actual_pnl_pct = round((actual_pnl / cost_basis) * 100, 4) if cost_basis else 0

            if trade_id:
                db.close_trade(trade_id, exit_date, filled_exit_price,
                               actual_proceeds, actual_pnl, actual_pnl_pct, exit_reason,
                               stop_loss=float(pos['stop_loss']) if pos.get('stop_loss') else None)
            db.close_position(symbol)

            # Clear in_portfolio flag so the scanner tab reflects the exit immediately
            db.update_scan_result_portfolio_flag(symbol, False)

            mode = "PAPER" if paper_trading else "LIVE"
            logger.info(
                f"✅ [{mode}] SELL {symbol}: {quantity} shares @ ${filled_exit_price:.2f} "
                f"| P&L: ${actual_pnl:.2f} ({actual_pnl_pct:.2f}%) "
                f"| reason={exit_reason} ib_order_id={ib_order.get('order_id')}"
            )

            executed.append({
                "symbol": symbol,
                "quantity": quantity,
                "exit_price": filled_exit_price,
                "exit_reason": exit_reason,
                "pnl": actual_pnl,
                "pnl_pct": actual_pnl_pct,
                "ib_order_id": ib_order.get("order_id"),
                "ib_status": ib_order.get("status"),
                "mode": mode,
            })

        except Exception as e:
            logger.error(f"❌ Error executing exit for {symbol}: {e}")

    return executed


# ---------------------------------------------------------------------------
# Combined execution entry point
# ---------------------------------------------------------------------------

async def run_order_execution(bot_state) -> None:
    """
    Execute all pending buys and exits for the current session.
    Called by the market-open scheduler.
    Broadcasts WebSocket events for executed orders.
    """
    config = bot_state.db.get_config()
    if not config.get("auto_execute"):
        logger.info("Auto-execute is OFF — order execution skipped")
        return

    logger.info("🔔 Market open order execution starting...")
    bot_state.execution_running = True
    started_at = datetime.now(ET)

    try:
        # --- Exits first (free up capacity before buying) ---
        exits = await execute_pending_exits(bot_state)
        if exits:
            await _broadcast(bot_state, {
                "type": "orders_executed",
                "order_type": "exits",
                "timestamp": datetime.now(ET).isoformat(),
                "orders": exits,
            })
            logger.info(f"✅ Executed {len(exits)} exit order(s)")
        else:
            logger.info("No exits executed")

        # --- Then buys ---
        buys = await execute_pending_buys(bot_state)
        if buys:
            await _broadcast(bot_state, {
                "type": "orders_executed",
                "order_type": "buys",
                "timestamp": datetime.now(ET).isoformat(),
                "orders": buys,
            })
            logger.info(f"✅ Executed {len(buys)} buy order(s)")
        else:
            logger.info("No buys executed")

        finished_at = datetime.now(ET)
        bot_state.last_execution = {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "buys": len(buys),
            "exits": len(exits),
            "status": "completed",
        }
        logger.info("🔔 Market open order execution complete")

    except Exception as e:
        logger.error(f"❌ Order execution failed: {e}")
        bot_state.last_execution = {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(ET).isoformat(),
            "buys": 0,
            "exits": 0,
            "status": "error",
            "error": str(e),
        }
        raise

    finally:
        bot_state.execution_running = False


async def run_eod_execution(bot_state) -> None:
    """
    EOD buy execution for Group A candidates.
    Called by the eod_scheduler_loop in data_updater.py.
    Only runs when ab_test_enabled = true.
    """
    config = bot_state.db.get_config()
    if not config.get("auto_execute"):
        logger.info("Auto-execute is OFF — EOD execution skipped")
        return
    if not config.get("ab_test_enabled"):
        logger.info("A/B test is OFF — EOD execution skipped")
        return

    logger.info("🔔 EOD Group A buy execution starting...")
    bot_state.execution_running = True
    started_at = datetime.now(ET)

    try:
        buys = await execute_eod_buys(bot_state)
        if buys:
            await _broadcast(bot_state, {
                "type": "orders_executed",
                "order_type": "buys",
                "timestamp": datetime.now(ET).isoformat(),
                "orders": buys,
            })
            logger.info(f"✅ EOD: executed {len(buys)} Group A buy order(s)")
        else:
            logger.info("EOD: no Group A buys executed")

        bot_state.last_execution = {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(ET).isoformat(),
            "buys": len(buys),
            "exits": 0,
            "status": "completed",
        }
        logger.info("🔔 EOD Group A buy execution complete")

    except Exception as e:
        logger.error(f"❌ EOD execution failed: {e}")
        bot_state.last_execution = {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(ET).isoformat(),
            "buys": 0,
            "exits": 0,
            "status": "error",
            "error": str(e),
        }
        raise

    finally:
        bot_state.execution_running = False
