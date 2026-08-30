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
from scrapers.bet99 import Bet99Scraper
from scrapers.betway import BetwayScraper
from scrapers.playalberta import PlayAlbertaScraper
from scrapers.polymarket import PolymarketScraper
from scrapers.sportsinteraction import SportsInteractionScraper
from scrapers.kalshi import KalshiScraper
from scrapers.limitless import LimitlessScraper
from scrapers.probable import ProbableScraper
from scrapers.myriad import MyriadScraper
from scrapers.opinion import OpinionScraper
from notifier import notify_new_opportunities

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None
_playwright = None
_browser = None
_scrapers = []


async def start_scheduler(store, ws_manager):
    global _scheduler, _playwright, _browser, _scrapers

    # Browser-free scrapers — always active
    _browser_free_scrapers = [
        BetwayScraper(None),
        # Bet99Scraper(None),  # disabled
        PolymarketScraper(None),
        KalshiScraper(None),
        LimitlessScraper(None),
        ProbableScraper(None),
        MyriadScraper(None),
        OpinionScraper(None),
    ]
    _scrapers = _browser_free_scrapers
    logger.info("Running browser-free scrapers only (%d scrapers)", len(_scrapers))

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


_email_paused: bool = True
_disabled_scrapers: set = set()


def disable_scraper(name: str) -> None:
    _disabled_scrapers.add(name)


def enable_scraper(name: str) -> None:
    _disabled_scrapers.discard(name)


def get_scraper_states() -> dict:
    """Return {book_name: enabled} for all registered scrapers."""
    return {s.BOOK_NAME: s.BOOK_NAME not in _disabled_scrapers for s in _scrapers}


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


async def _relaunch_browser():
    """Relaunch the shared Playwright browser and update browser scrapers."""
    global _browser, _playwright, _scrapers
    logger.info("Browser disconnected — relaunching")
    try:
        if _browser:
            try:
                await _browser.close()
            except Exception:
                pass
        for channel, kwargs in [('msedge', {'channel': 'msedge'}), ('chromium', {})]:
            try:
                _browser = await _playwright.chromium.launch(headless=True, **kwargs)
                logger.info("Browser relaunched via %s", channel)
                break
            except Exception as e:
                logger.debug("Browser relaunch channel %s failed: %s", channel, e)
        else:
            logger.error("Browser relaunch failed — browser scrapers will stay offline")
            _browser = None
            for scraper in _scrapers:
                if scraper.browser is not None:
                    scraper.browser = None
            return
        for scraper in _scrapers:
            if scraper.browser is not None:
                scraper.browser = _browser
    except Exception as exc:
        logger.error("Browser relaunch error: %s", exc)


async def _run_cycle(store, ws_manager):
    try:
        await _run_cycle_inner(store, ws_manager)
    except Exception as exc:
        logger.error("Unhandled exception in scrape cycle: %s: %s", type(exc).__name__, exc, exc_info=True)


async def _run_cycle_inner(store, ws_manager):
    start = datetime.now(timezone.utc)
    logger.info("Scrape cycle starting")

    # Run all enabled scrapers concurrently
    active = [s for s in _scrapers if s.BOOK_NAME not in _disabled_scrapers]
    results = await asyncio.gather(
        *[s.fetch_odds() for s in active],
        return_exceptions=True,
    )

    # Detect browser crash via is_connected() — reliable once the process is truly dead
    if _browser is not None:
        try:
            connected = _browser.is_connected()
        except Exception:
            connected = False
        if not connected:
            await _relaunch_browser()

    books_ok = 0
    books_error = 0

    for scraper, result in zip(active, results):
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


async def recalculate_opportunities(store, ws_manager):
    """Immediately recompute arbs from current store state and push WS diffs.
    Called when a scraper is disabled so stale arbs are expired right away."""
    fresh_records = store.get_fresh_records()
    new_opps_list = detect_arbs(fresh_records, min_margin=config.MIN_ARB_MARGIN)
    new_opps_map = {o.id: o for o in new_opps_list}

    prev_opps = store.get_opportunities()
    new, updated, expired_ids = diff_opportunities(prev_opps, new_opps_map)

    for opp in updated:
        if opp.id in prev_opps:
            opp.detected_at = prev_opps[opp.id].detected_at

    store.update_opportunities(new_opps_map)

    for opp in new:
        await ws_manager.broadcast({"type": "new_opportunity", "data": serialize_opportunity(opp)})
    for opp in updated:
        await ws_manager.broadcast({"type": "opportunity_updated", "data": serialize_opportunity(opp)})
    for id_ in expired_ids:
        await ws_manager.broadcast({"type": "opportunity_expired", "id": id_})
