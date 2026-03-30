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

- **Exchange instantiation:** Subclasses provide a `_make_exchange()` method that returns a configured PMXT exchange instance.
- **Async bridging:** PMXT is synchronous. Calls to `fetch_markets()` are run via `asyncio.run_in_executor(None, ...)` so the event loop is not blocked.
- **Sport querying:** Iterates over `["nba", "nhl", "mlb"]`, calling `exchange.fetch_markets(query=sport)` for each.
- **Mapping:** Converts PMXT market/outcome objects to `OddsRecord` (see Data Mapping section).
- **Error handling:** Wraps the entire `fetch_odds()` body in try/except; logs a warning and returns `[]` on any failure.

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
| `event_name` | `normalize_event_name(market title)` |
| `market` | `"moneyline"` (binary win/loss markets only) |
| `outcome` | `"home"` for first outcome, `"away"` for second |
| `decimal_odds` | `round(1.0 / outcome.price, 4)` |
| `event_start` | market expiry/end date |
| `participant` | outcome label from PMXT |
| `event_url` | market URL if available, else exchange homepage |
| `scraped_at` | `datetime.now(timezone.utc)` |

**Price filters (same as existing Polymarket scraper):**
- Skip outcomes with `price <= 0.01` or `price >= 0.99`
- Skip outcomes yielding `decimal_odds <= 1.0`

**Team name parsing:** PMXT provides structured outcome labels — no regex parsing needed (unlike the existing Polymarket scraper which parses raw question strings).

## Authentication

| Exchange | Auth required | Env vars |
|---|---|---|
| Kalshi | Yes (API + private key) | `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY` |
| Limitless | No | — |
| Probable | No | — |
| Myriad | No | — |
| Opinion | No | — |

If Kalshi env vars are missing, `KalshiScraper` logs a warning and returns `[]`.

## Registration

In `main.py` (wherever scrapers are instantiated), add the five new scrapers with `browser=None` — same as the existing Polymarket scraper since PMXT manages its own HTTP transport.

## Error Handling

- Any exception from PMXT (network error, auth failure, sidecar not running) is caught in `fetch_odds()`, logged as a warning, and returns `[]`
- Individual sport query failures are caught per-sport; other sports continue
- The app never crashes due to a PMXT exchange failure

## Files Changed

| File | Change |
|---|---|
| `scrapers/pmxt_base.py` | New — shared base class |
| `scrapers/kalshi.py` | New — KalshiScraper |
| `scrapers/limitless.py` | New — LimitlessScraper |
| `scrapers/probable.py` | New — ProbableScraper |
| `scrapers/myriad.py` | New — MyriadScraper |
| `scrapers/opinion.py` | New — OpinionScraper |
| `main.py` | Register 5 new scrapers |
| `requirements.txt` | Add `pmxt` |
