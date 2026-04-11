# PMXT Integration Design

**Date:** 2026-03-30
**Status:** Approved

## Overview

Integrate the [PMXT](https://github.com/pmxt-dev/pmxt) unified prediction market SDK as an additional odds source alongside the existing scrapers. PMXT provides a single Python API for Kalshi, Limitless, Probable, Myriad, and Opinion prediction markets.

The existing hand-rolled Polymarket scraper (`scrapers/polymarket.py`) is kept as-is. PMXT runs alongside it.

## Scope

Add five new scrapers:
- `KalshiScraper` — Kalshi (requires API key + private key)
- `LimitlessScraper` — Limitless (no auth required for reads)
- `ProbableScraper` — Probable (no auth required for reads)
- `MyriadScraper` — Myriad (no auth required for reads)
- `OpinionScraper` — Opinion (no auth required for reads)

Sports queried: NBA, NHL, MLB (same as existing Polymarket scraper).

## Architecture

### `scrapers/pmxt_base.py` — Shared base class

A `PmxtScraper` abstract class inheriting from `OddsScraper` containing all shared logic:

- **Exchange instantiation:** Each `fetch_odds()` call creates a fresh exchange instance via `_make_exchange()` to avoid any thread-safety issues with shared state in PMXT's Node.js sidecar. Subclasses implement `_make_exchange()`.
- **Async bridging:** PMXT is synchronous. Each `fetch_markets()` call is dispatched via `asyncio.run_in_executor(None, ...)` so the event loop is not blocked.
- **Sport querying:** Iterates over `["nba", "nhl", "mlb"]`. Each sport query runs in its own inner try/except so a failure on one sport does not prevent the others from running.
- **Mapping:** Converts PMXT market/outcome objects to `OddsRecord` (see Data Mapping section).
- **Error handling:** An outer try/except wraps exchange instantiation; returns `[]` with a warning if setup fails. Per-sport errors are caught in the inner loop.

### Thin subclasses (one file each)

Each subclass sets `BOOK_NAME` and implements `_make_exchange()`:

```
scrapers/kalshi.py     — KalshiScraper    BOOK_NAME="kalshi"
scrapers/limitless.py  — LimitlessScraper BOOK_NAME="limitless"
scrapers/probable.py   — ProbableScraper  BOOK_NAME="probable"
scrapers/myriad.py     — MyriadScraper    BOOK_NAME="myriad"
scrapers/opinion.py    — OpinionScraper   BOOK_NAME="opinion"
```

### Installation requirement

PMXT's Python SDK requires a Node.js sidecar:

```bash
pip install pmxt
npm install -g pmxtjs
```

Both must be installed on the host machine.

## Data Mapping

PMXT outcome prices are probabilities in the range 0.0–1.0. Mapping to `OddsRecord`:

| OddsRecord field | Source |
|---|---|
| `book` | `BOOK_NAME` |
| `sport` | query key (`"nba"`, `"nhl"`, `"mlb"`) |
| `event_name` | `normalize_event_name(f"{outcome_a.label} vs {outcome_b.label}")` — constructed from the two outcome labels, not the market title |
| `market` | `"moneyline"` (binary win/loss markets only) |
| `outcome` | `"home"` / `"away"` determined by alphabetical sort of resolved team names (matches how `normalize_event_name` sorts teams — see below) |
| `decimal_odds` | `round(1.0 / outcome.price, 4)` |
| `event_start` | `market.end_date` (PMXT field); fall back to `scraped_at` if absent |
| `participant` | `normalize_participant(outcome.label)` |
| `event_url` | market URL if available, else exchange homepage |
| `scraped_at` | `datetime.now(timezone.utc)` |

**Home/away assignment:** `normalize_event_name` sorts teams alphabetically; the canonical event name is always `"A vs B"` where A < B. To be consistent, resolve both outcome labels via `normalize_participant()`, sort them alphabetically, and assign `"home"` to the first (A) and `"away"` to the second (B). This guarantees that `outcome` values are consistent with the canonical event name across all prediction market sources.

**Market filter:** Only process markets with exactly 2 outcomes (`len(market.outcomes) == 2`). Skip any market with a different outcome count (props, multi-leg, etc.).

**Price filters:**
- Skip outcomes with `price <= 0.01` or `price >= 0.99`
- Skip outcomes yielding `decimal_odds <= 1.0`

## Authentication

| Exchange | Auth required | Env vars |
|---|---|---|
| Kalshi | Yes (API + private key) | `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY` |
| Limitless | No | — |
| Probable | No | — |
| Myriad | No | — |
| Opinion | No | — |

If Kalshi env vars are missing, `KalshiScraper` logs a warning and returns `[]`. The PMXT SDK handles Kalshi's request signing internally — pass `api_key` and `private_key` as strings to `pmxt.Kalshi()`; do not implement manual signing.

## Registration

PMXT scrapers are registered in `scheduler.py` (`start_scheduler()`), **outside** the Playwright try/except block. They do not need a browser instance and must not be disabled when Playwright fails to launch. Add them to a separate `_browser_free_scrapers` list that is instantiated unconditionally, then merged into `_scrapers` after the Playwright block.

Note: `PolymarketScraper` is currently inside the Playwright try block despite not needing a browser. It should be moved to the same browser-free list as part of this change.

## Error Handling

Two-level structure:
1. **Outer try/except** — wraps exchange instantiation (`_make_exchange()`). Any failure here (missing env vars, sidecar not running) logs a warning and returns `[]` immediately.
2. **Inner per-sport try/except** — wraps each `fetch_markets(query=sport)` call. A failure on one sport logs a warning and continues to the next sport.

The app never crashes due to a PMXT exchange failure.

## Files Changed

| File | Change |
|---|---|
| `scrapers/pmxt_base.py` | New — shared base class |
| `scrapers/kalshi.py` | New — KalshiScraper |
| `scrapers/limitless.py` | New — LimitlessScraper |
| `scrapers/probable.py` | New — ProbableScraper |
| `scrapers/myriad.py` | New — MyriadScraper |
| `scrapers/opinion.py` | New — OpinionScraper |
| `scheduler.py` | Register 5 new scrapers outside Playwright block; move PolymarketScraper there too |
| `requirements.txt` | Add `pmxt` |
