import asyncio
import sys
from contextlib import asynccontextmanager

# On Windows, asyncio defaults to SelectorEventLoop which cannot spawn subprocesses.
# Playwright requires subprocess creation, so we must use ProactorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from calculator import Opportunity
from scheduler import (
    start_scheduler, stop_scheduler,
    pause_scraping, resume_scraping, scraping_is_running,
    pause_email, resume_email, email_is_paused,
)
from serializers import serialize_opportunity
from store import Store
from ws import WebSocketManager

store = Store(
    stale_seconds=config.ODDS_STALE_SECONDS,
    evict_seconds=config.ODDS_EVICT_SECONDS,
)
ws_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_scheduler(store, ws_manager)
    yield
    await stop_scheduler()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.CORS_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/opportunities")
def get_opportunities():
    opps = sorted(store.get_opportunities().values(), key=lambda o: o.margin, reverse=True)
    return {"opportunities": [serialize_opportunity(o) for o in opps]}


@app.get("/api/odds")
def get_odds():
    result = {}
    for book, records in store._odds.items():
        fresh = [r for r in records
                 if (datetime.now(timezone.utc) - r.scraped_at).total_seconds()
                 < config.ODDS_STALE_SECONDS]
        result[book] = {
            "record_count": len(fresh),
            "scraped_at": records[0].scraped_at.isoformat() if records else None,
            "records": [
                {
                    "book": r.book, "sport": r.sport, "event_name": r.event_name,
                    "market": r.market, "outcome": r.outcome,
                    "decimal_odds": r.decimal_odds, "participant": r.participant,
                    "scraped_at": r.scraped_at.isoformat(),
                }
                for r in fresh
            ],
        }
    return {"books": result}


@app.get("/api/books")
def get_books():
    statuses = store.get_book_status()
    return {
        "books": [
            {
                "name": s.name,
                "status": s.status,
                "last_scraped_at": s.last_scraped_at.isoformat() if s.last_scraped_at else None,
                "record_count": s.record_count,
                "last_error": s.last_error,
            }
            for s in statuses.values()
        ]
    }


# ── Scraper control ──────────────────────────────────────────────────────────

@app.get("/api/scraper/status")
def scraper_status():
    running = scraping_is_running()
    return {"running": running}


@app.post("/api/scraper/start")
async def scraper_start():
    resume_scraping()
    running = scraping_is_running()
    await ws_manager.broadcast({"type": "scraper_state", "running": running})
    return {"running": running}


@app.post("/api/scraper/stop")
async def scraper_stop():
    pause_scraping()
    running = scraping_is_running()
    await ws_manager.broadcast({"type": "scraper_state", "running": running})
    return {"running": running}


# ── Email notification control ───────────────────────────────────────────────

@app.get("/api/email/status")
def email_status():
    return {"paused": email_is_paused()}


@app.post("/api/email/pause")
async def email_pause():
    pause_email()
    await ws_manager.broadcast({"type": "email_state", "paused": True})
    return {"paused": True}


@app.post("/api/email/resume")
async def email_resume():
    resume_email()
    await ws_manager.broadcast({"type": "email_state", "paused": False})
    return {"paused": False}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive; we only push, don't expect messages
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
