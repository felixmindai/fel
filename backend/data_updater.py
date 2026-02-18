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

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
RATE_LIMIT_SLEEP = 0.5   # seconds between IB requests
MAX_FETCH_DAYS = 365     # cap for very stale / never-fetched tickers
PROGRESS_EVERY = 10      # broadcast progress every N tickers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def seconds_until_next_trigger(update_time_str: str) -> float:
    """
    Return the number of seconds until the next weekday trigger at
    `update_time_str` (HH:MM, 24-hour, Eastern Time).

    Handles DST transitions automatically via ZoneInfo.
    Skips Saturday and Sunday; if today is a weekday and the trigger has
    not yet passed, targets today; otherwise targets the next Mon–Fri.
    """
    try:
        hour, minute = (int(x) for x in update_time_str.split(':'))
    except Exception:
        logger.warning(f"Invalid update_time_str '{update_time_str}', defaulting to 17:00")
        hour, minute = 17, 0

    now_et = datetime.now(ET)
    candidate = now_et.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Step forward until we land on a future weekday trigger
    while True:
        # weekday() 0=Mon … 6=Sun
        if candidate.weekday() < 5 and candidate > now_et:
            break
        candidate += timedelta(days=1)
        candidate = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)

    delta = (candidate - now_et).total_seconds()
    return max(delta, 1.0)   # never negative


def compute_fetch_duration(symbol: str, db) -> Optional[str]:
    """
    Return the IB duration string that covers the gap since the last stored
    bar for `symbol`, or None if the symbol is already up to date.

    Examples: '15 D', '60 D', '1 Y'
    """
    latest: Optional[date] = db.get_latest_bar_date(symbol)

    if latest is None:
        return '1 Y'   # never fetched — bootstrap the full history

    today = date.today()
    gap_days = (today - latest).days

    if gap_days <= 0:
        return None    # already current — skip this ticker

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
        update_time = config.get('data_update_time', '17:00') or '17:00'
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
