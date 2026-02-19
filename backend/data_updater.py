"""
Data Auto-Updater for Minervini Trading Bot
============================================

Handles scheduled and on-demand fetching of fresh OHLCV bars from IB Gateway.

Key design points:
- Pure asyncio scheduling — no external scheduler dependency
- Dynamic gap detection: checks each ticker's latest bar date and fetches
  exactly the missing days (+ 5-day buffer for weekends/holidays, capped 1 Y)
- Trigger time is read from DB each loop iteration so UI changes take effect
  without a restart
- DB-backed concurrency guard prevents overlapping runs
- Progress broadcast over WebSocket every 10 tickers
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    pass  # BotState imported at runtime inside functions to avoid circular import

# order_executor is a sibling module in the same backend directory — safe to import at module level
from order_executor import run_order_execution

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
RATE_LIMIT_SLEEP = 0.5   # seconds between IB requests
MAX_FETCH_DAYS = 365     # cap for very stale / never-fetched tickers
PROGRESS_EVERY = 10      # broadcast progress every N tickers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def seconds_until_next_trigger(update_time_str: str, grace_minutes: int = 0) -> float:
    """
    Return the number of seconds until the next weekday trigger at
    `update_time_str` (HH:MM, 24-hour, Eastern Time).

    Handles DST transitions automatically via ZoneInfo.
    Skips Saturday and Sunday; if today is a weekday and the trigger has
    not yet passed, targets today; otherwise targets the next Mon–Fri.

    grace_minutes: if > 0, a trigger that passed within this many minutes ago
    on a weekday is treated as "just now" and returns 1 second (fire immediately).
    Use this for the order execution scheduler so a restart within the grace window
    still fires rather than skipping to tomorrow.
    """
    try:
        hour, minute = (int(x) for x in update_time_str.split(':'))
    except Exception:
        raise ValueError(
            f"Invalid time string '{update_time_str}' — expected HH:MM (e.g. '09:30'). "
            f"Fix the value in Settings and restart."
        )

    now_et = datetime.now(ET)
    candidate = now_et.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Grace window: if the trigger passed recently today on a weekday, fire now
    if grace_minutes > 0 and candidate.weekday() < 5:
        seconds_since = (now_et - candidate).total_seconds()
        if 0 < seconds_since <= grace_minutes * 60:
            logger.info(
                f"Trigger time {update_time_str} passed {seconds_since:.0f}s ago "
                f"(within {grace_minutes}m grace window) — firing immediately"
            )
            return 1.0

    # Step forward until we land on a future weekday trigger
    while True:
        # weekday() 0=Mon … 6=Sun
        if candidate.weekday() < 5 and candidate > now_et:
            break
        candidate += timedelta(days=1)
        candidate = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)

    delta = (candidate - now_et).total_seconds()
    return max(delta, 1.0)   # never negative


def _last_completed_bar_date() -> date:
    """
    Return the date of the most recent *completed* trading day.

    IB returns bars for dates up to and including today while the market is
    still open (partial bar). We treat the last *completed* bar as:
      - Yesterday, if today is a weekday (Mon–Fri)
      - Last Friday, if today is Saturday or Sunday
    This prevents re-fetching the same partial/incomplete bar every time the
    user clicks "Update Now" during market hours.
    """
    today = datetime.now(ET).date()   # always use ET date, not machine local
    weekday = today.weekday()  # 0=Mon … 6=Sun
    if weekday == 5:           # Saturday → last completed bar was Friday
        return today - timedelta(days=1)
    if weekday == 6:           # Sunday → last completed bar was Friday
        return today - timedelta(days=2)
    # Weekday: last completed bar is yesterday
    return today - timedelta(days=1)


def compute_fetch_duration(symbol: str, db) -> Optional[str]:
    """
    Return the IB duration string that covers the gap since the last stored
    bar for `symbol`, or None if the symbol is already up to date.

    Examples: '15 D', '60 D', '1 Y'
    """
    latest: Optional[date] = db.get_latest_bar_date(symbol)

    if latest is None:
        return '1 Y'   # never fetched — bootstrap the full history

    last_completed = _last_completed_bar_date()
    gap_days = (last_completed - latest).days

    if gap_days <= 0:
        return None    # already current — last completed bar is in the DB

    # Add a 5-day buffer to account for weekends and holidays, cap at 1 year
    fetch_days = min(gap_days + 5, MAX_FETCH_DAYS)
    if fetch_days >= MAX_FETCH_DAYS:
        return '1 Y'
    return f'{fetch_days} D'


async def _broadcast_update(bot_state, message: dict) -> None:
    """Send a JSON message to all connected WebSocket clients."""
    payload = json.dumps(message)
    dead: list = []
    for ws in list(getattr(bot_state, 'websocket_clients', set())):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        bot_state.websocket_clients.discard(ws)


# ---------------------------------------------------------------------------
# Core update function
# ---------------------------------------------------------------------------

async def run_data_update(bot_state) -> None:
    """
    Fetch missing OHLCV bars for all active tickers.

    Designed to be safe to call concurrently (the DB 'running' guard prevents
    overlap). Fire-and-forget via asyncio.create_task is the expected usage.
    """
    db = bot_state.db
    fetcher = bot_state.fetcher

    # --- guard: prevent overlapping runs ---
    current_status = db.get_data_update_status()
    if current_status.get('data_update_status') == 'running':
        logger.info("Data update already in progress — skipping")
        return

    # --- guard: IB connectivity ---
    if not bot_state.ib_connected:
        logger.warning("IB not connected; attempting reconnect before data update")
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, fetcher.connect)
            bot_state.ib_connected = True
        except Exception as e:
            logger.error(f"Reconnect failed: {e}")
            db.set_data_update_status('failed', error=f'IB not connected: {e}')
            await _broadcast_update(bot_state, {
                'type': 'data_update_complete',
                'data': {'status': 'failed', 'error': f'IB not connected: {e}'}
            })
            return

    tickers = db.get_active_tickers()
    if not tickers:
        logger.info("No active tickers — skipping data update")
        return

    total = len(tickers)
    logger.info(f"Starting data update for {total} tickers")

    db.set_data_update_status('running')
    await _broadcast_update(bot_state, {
        'type': 'data_update_started',
        'data': {'total': total}
    })

    done = 0
    skipped = 0
    errors = 0

    try:
        for symbol in tickers:
            duration = compute_fetch_duration(symbol, db)

            if duration is None:
                skipped += 1
                done += 1
                # Broadcast progress at the normal cadence even for skipped ones
                if done % PROGRESS_EVERY == 0:
                    await _broadcast_update(bot_state, {
                        'type': 'data_update_progress',
                        'data': {'done': done, 'total': total, 'current_symbol': symbol}
                    })
                continue

            try:
                loop = asyncio.get_event_loop()
                bars = await loop.run_in_executor(
                    None,
                    lambda s=symbol, d=duration: fetcher.fetch_historical_bars(s, duration=d)
                )
                if bars:
                    db.save_daily_bars(symbol, bars)
            except Exception as e:
                errors += 1
                logger.error(f"Error fetching bars for {symbol}: {e}")

            done += 1

            if done % PROGRESS_EVERY == 0:
                await _broadcast_update(bot_state, {
                    'type': 'data_update_progress',
                    'data': {'done': done, 'total': total, 'current_symbol': symbol}
                })

            await asyncio.sleep(RATE_LIMIT_SLEEP)

        db.set_data_update_status('success')
        logger.info(
            f"Data update complete — {total} tickers processed "
            f"({skipped} already current, {errors} errors)"
        )
        await _broadcast_update(bot_state, {
            'type': 'data_update_complete',
            'data': {
                'status': 'success',
                'total': total,
                'skipped': skipped,
                'errors': errors
            }
        })

    except Exception as e:
        logger.error(f"Data update failed: {e}")
        db.set_data_update_status('failed', error=str(e))
        await _broadcast_update(bot_state, {
            'type': 'data_update_complete',
            'data': {'status': 'failed', 'error': str(e)}
        })


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------

async def data_update_scheduler_loop(bot_state) -> None:
    """
    Long-running asyncio task. Sleeps until the configured weekday trigger
    time (ET), runs the data update, then repeats.

    Reads `data_update_time` from the DB at the top of each iteration so
    that changes made in the Settings UI take effect on the next cycle
    without requiring a restart.
    """
    logger.info("Data update scheduler started")

    while True:
        config = bot_state.db.get_config()
        update_time = config.get('data_update_time') or ''
        if not update_time:
            logger.error("❌ data_update_time is not set in config — cannot schedule data update. Set it in Settings.")
            await asyncio.sleep(60)
            continue
        wait = seconds_until_next_trigger(update_time)
        logger.info(
            f"Next data update scheduled in {wait / 3600:.1f}h "
            f"(at {update_time} ET on next weekday)"
        )

        await asyncio.sleep(wait)

        try:
            await run_data_update(bot_state)
        except Exception as e:
            logger.error(f"Scheduled data update raised an unexpected error: {e}")
            bot_state.db.set_data_update_status('failed', error=str(e))

        # Brief buffer so a clock jitter can't re-trigger within the same minute
        await asyncio.sleep(120)


# ---------------------------------------------------------------------------
# Market-open order execution scheduler
# ---------------------------------------------------------------------------

async def market_open_scheduler_loop(bot_state) -> None:
    """
    Long-running asyncio task. Sleeps until the configured order_execution_time
    (set in Settings UI, weekdays only), then runs buy + exit order execution.

    Reads `order_execution_time` from the DB at the top of each iteration so
    that changes made in the Settings UI take effect on the next cycle without
    requiring a restart.
    """
    logger.info("Market-open order execution scheduler started")

    last_execution_date = None  # track date of last fire to prevent same-day re-fires on restart

    while True:
        config = bot_state.db.get_config()
        exec_time = config.get("order_execution_time") or ''
        if not exec_time:
            logger.error("❌ order_execution_time is not set in config — cannot schedule order execution. Set it in Settings.")
            await asyncio.sleep(60)
            continue
        today = datetime.now(ET).date()

        # 10-minute grace window: if backend restarted within 10 min after the
        # scheduled time, fire immediately — but only if we haven't already
        # fired today (prevents repeated fires on rapid restarts)
        if last_execution_date == today:
            # Already ran today — skip grace window, wait for tomorrow's trigger
            wait = seconds_until_next_trigger(exec_time, grace_minutes=0)
        else:
            wait = seconds_until_next_trigger(exec_time, grace_minutes=10)

        if wait > 2:
            logger.info(
                f"Next order execution scheduled in {wait / 3600:.1f}h "
                f"(at {exec_time} ET on next weekday)"
            )

        await asyncio.sleep(wait)

        try:
            await run_order_execution(bot_state)
            last_execution_date = datetime.now(ET).date()
        except Exception as e:
            logger.error(f"Market-open order execution raised an unexpected error: {e}")

        # Buffer to prevent double-fire from clock jitter
        await asyncio.sleep(120)
