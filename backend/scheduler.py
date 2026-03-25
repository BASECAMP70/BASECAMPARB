import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import config
from calculator import detect_arbs, diff_opportunities
from serializers import serialize_opportunity
from scrapers.bet365 import Bet365Scraper
# from scrapers.bet99 import Bet99Scraper  # suppressed
from scrapers.betway import BetwayScraper
from scrapers.playalberta import PlayAlbertaScraper
from scrapers.sportsinteraction import SportsInteractionScraper
from notifier import notify_new_opportunities

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None
_playwright = None
_browser = None
_scrapers = []


async def start_scheduler(store, ws_manager):
    global _scheduler, _playwright, _browser, _scrapers

    # Attempt to launch a browser. Try msedge channel first (always present on
    # Windows 11 and avoids SxS/VC++ issues with the bundled Chromium), then
    # fall back to plain Chromium. If both fail the API still runs without scrapers.
    try:
        from playwright.async_api import async_playwright
        _playwright = await async_playwright().start()
        for channel, kwargs in [('msedge', {'channel': 'msedge'}), ('chromium', {})]:
            try:
                _browser = await _playwright.chromium.launch(headless=True, **kwargs)
                logger.info("Browser launched via %s", channel)
                break
            except Exception as browser_exc:
                logger.debug("Browser channel %s failed: %s", channel, browser_exc)
        else:
            raise RuntimeError("No usable browser found (tried msedge and chromium)")
        scraper_classes = [
            PlayAlbertaScraper,
            Bet365Scraper,
            SportsInteractionScraper,
            BetwayScraper,
            # Bet99Scraper,  # suppressed
        ]
        _scrapers = [cls(_browser) for cls in scraper_classes]
        logger.info("Playwright browser launched — %d scrapers ready", len(_scrapers))
    except Exception as exc:
        logger.warning("Playwright/Chromium unavailable (%s: %s) — scrapers disabled, API still running",
                       type(exc).__name__, exc)
        _scrapers = []

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _run_cycle,
        trigger=IntervalTrigger(seconds=config.SCRAPE_INTERVAL_SECONDS),
        args=[store, ws_manager],
        max_instances=1,
        misfire_grace_time=10,
    )
    _scheduler.start()
    logger.info("Scheduler started — scraping every %ds", config.SCRAPE_INTERVAL_SECONDS)


async def stop_scheduler():
    global _scheduler, _browser, _playwright
    if _scheduler:
        _scheduler.shutdown(wait=False)
    if _browser:
        await _browser.close()
    if _playwright:
        await _playwright.stop()


_email_paused: bool = False


def pause_email() -> None:
    global _email_paused
    _email_paused = True


def resume_email() -> None:
    global _email_paused
    _email_paused = False


def email_is_paused() -> bool:
    return _email_paused


def pause_scraping() -> bool:
    """Pause the scrape job.  Returns True if paused, False if already paused."""
    if _scheduler is None:
        return False
    jobs = _scheduler.get_jobs()
    if not jobs:
        return False
    job = jobs[0]
    if job.next_run_time is None:
        return False  # already paused
    job.pause()
    logger.info("Scraping paused")
    return True


def resume_scraping() -> bool:
    """Resume the scrape job.  Returns True if resumed, False if already running."""
    if _scheduler is None:
        return False
    jobs = _scheduler.get_jobs()
    if not jobs:
        return False
    job = jobs[0]
    if job.next_run_time is not None:
        return False  # already running
    job.resume()
    logger.info("Scraping resumed")
    return True


def scraping_is_running() -> bool:
    """Return True when the scrape job is active (not paused)."""
    if _scheduler is None:
        return False
    jobs = _scheduler.get_jobs()
    if not jobs:
        return False
    return jobs[0].next_run_time is not None


async def _run_cycle(store, ws_manager):
    start = datetime.now(timezone.utc)
    logger.info("Scrape cycle starting")

    # Run all scrapers concurrently
    results = await asyncio.gather(
        *[s.fetch_odds() for s in _scrapers],
        return_exceptions=True,
    )

    books_ok = 0
    books_error = 0

    for scraper, result in zip(_scrapers, results):
        if isinstance(result, Exception):
            books_error += 1
            error_msg = f"{type(result).__name__}: {result}"
            logger.error("Scraper %s failed: %s", scraper.BOOK_NAME, error_msg)
            store.update_book(scraper.BOOK_NAME, None, error_msg)
        else:
            books_ok += 1
            store.update_book(scraper.BOOK_NAME, result, None)
            await ws_manager.broadcast({
                "type": "odds_updated",
                "book": scraper.BOOK_NAME,
                "status": "ok",
                "record_count": len(result),
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })

    # Evict very old records
    store.evict_stale()

    # Detect arbs
    fresh_records = store.get_fresh_records()
    new_opps_list = detect_arbs(fresh_records, min_margin=config.MIN_ARB_MARGIN)
    new_opps_map = {o.id: o for o in new_opps_list}

    prev_opps = store.get_opportunities()
    new, updated, expired_ids = diff_opportunities(prev_opps, new_opps_map)

    # Preserve detected_at for opportunities that aren't new
    for opp in updated:
        if opp.id in prev_opps:
            opp.detected_at = prev_opps[opp.id].detected_at

    store.update_opportunities(new_opps_map)

    # Email + push WS events for new opportunities
    if new and not _email_paused:
        await notify_new_opportunities(new)

    for opp in new:
        await ws_manager.broadcast({"type": "new_opportunity", "data": serialize_opportunity(opp)})

    for opp in updated:
        await ws_manager.broadcast({"type": "opportunity_updated", "data": serialize_opportunity(opp)})

    for id_ in expired_ids:
        await ws_manager.broadcast({"type": "opportunity_expired", "id": id_})

    duration = (datetime.now(timezone.utc) - start).total_seconds()
    await ws_manager.broadcast({
        "type": "scrape_cycle_complete",
        "duration_s": round(duration, 1),
        "opportunity_count": len(new_opps_map),
        "books_ok": books_ok,
        "books_error": books_error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    logger.info("Cycle complete in %.1fs — %d opps, %d ok, %d error",
                duration, len(new_opps_map), books_ok, books_error)
