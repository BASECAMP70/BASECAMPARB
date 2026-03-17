# Alberta Sports Betting Arbitrage Finder — Design Spec
**Date:** 2026-03-17
**Status:** Approved

---

## Overview

A real-time web dashboard that scrapes odds from Alberta-legal online sportsbooks every ~45 seconds, detects arbitrage opportunities across books, and presents them in a browser UI with inline stake calculation and audio/visual alerts.

---

## Goals

- Detect arbitrage opportunities across Alberta-licensed sportsbooks in near real-time
- Show exact stakes per outcome given a user-supplied bankroll
- Alert the user visually and audibly when new opportunities appear
- Only target sportsbooks where Canadians (Alberta residents) are legally permitted to bet

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   React Dashboard                    │
│  (odds table, arb alerts, stake calculator, sounds) │
└────────────────────┬────────────────────────────────┘
                     │ WebSocket (push) + REST (fetch)
┌────────────────────▼────────────────────────────────┐
│              FastAPI Backend                         │
│  - /api/opportunities  (current arbs)               │
│  - /api/odds           (raw odds snapshot)          │
│  - /api/books          (scraper health)             │
│  - ws://...            (live push on new arb)       │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│           Scraper Orchestrator (async)               │
│  - Runs every 45s via APScheduler (IntervalTrigger) │
│  - Single shared Playwright browser, one context    │
│    per scraper (isolated cookies/storage)           │
│  - Concurrent scrapers via asyncio.gather(          │
│      return_exceptions=True)                        │
│  - Feeds results into Arbitrage Calculator          │
└────────────┬──────────────┬──────────────┬──────────┘
             │              │              │
       PlayAlberta      BetMGM AB      FanDuel AB   ...
```

**Key data flow:** Scrapers run concurrently every 45s → odds stored in memory → arb calculator runs → new/expired opportunities pushed via WebSocket → dashboard updates instantly.

---

## Target Sportsbooks (Alberta-Licensed)

| Book | Odds Page URL Pattern | Notes |
|------|----------------------|-------|
| PlayAlberta | `playalberta.ca/sports` | Provincial AGLC site, DOM-rendered odds |
| BetMGM AB | `betmgm.ca/en/sports` | Dynamic SPA, odds in DOM after JS render |
| FanDuel AB | `fanduel.com/en-CA/sports` | Dynamic SPA |
| Bet365 | `bet365.ca` | Heavy anti-bot, stealth mode required |
| Sports Interaction | `sportsinteraction.com/sports` | Simpler structure |
| Betway AB | `betway.ca/en/sport` | Dynamic |

All target pages are publicly accessible without login. Scrapers navigate to the main sports/odds listing page and extract all visible pre-game moneyline and totals markets.

---

## Scraper Layer

### Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

@dataclass
class OddsRecord:
    book: str              # e.g. "betmgm"
    sport: str             # canonical: "nhl", "nfl", "nba", "mlb", "mls", "soccer"
    event_name: str        # canonical normalized name, e.g. "Edmonton Oilers vs Calgary Flames"
    event_start: datetime  # UTC kickoff/puck-drop time
    market: str            # canonical: "moneyline", "totals", "spread"
    outcome: str           # canonical: "home", "away", "over", "under", "draw"
    decimal_odds: float
    scraped_at: datetime   # UTC

class OddsScraper(ABC):
    def __init__(self, browser: playwright.async_api.Browser):
        self.browser = browser

    @abstractmethod
    async def fetch_odds(self) -> list[OddsRecord]:
        """Navigate to book's odds page and return all available pre-game records."""
```

### Playwright Concurrency Model

- A single `playwright.chromium` browser instance is launched at app startup and shared across all scrapers.
- Each scraper creates its own `browser.new_context()` at the start of each scrape cycle and closes it afterward. This isolates cookies and session state between books.
- All scrapers run concurrently via `asyncio.gather(*[s.fetch_odds() for s in scrapers], return_exceptions=True)`.
- Browser runs **headless**.

### Anti-Bot Strategy

- `playwright-stealth` applied to every new browser context.
- Random inter-action delays drawn from a uniform distribution: **0.8–2.5 seconds**.
- User agent rotated per scraper per cycle from a hardcoded list of 10 real desktop Chrome UA strings.
- No proxy rotation in v1.

### Scraper Failure Handling

`asyncio.gather(return_exceptions=True)` is used so one failing scraper does not abort others. For each result:
- If an exception is returned: log the error, mark the book as `status="error"` in the in-memory book status store, **retain the last successful OddsRecords** for that book (stale data is acceptable for one cycle).
- If a scraper returns successfully: replace that book's records in the store, mark `status="ok"`, update `last_scraped_at`.

### OddsRecord Staleness and Eviction

- Each book's records in the in-memory store are tagged with a `scraped_at` timestamp.
- Records older than **3 minutes** (4 failed cycles) are considered stale and **excluded from arb calculation**.
- Records older than **10 minutes** are **evicted** from the store entirely.
- This prevents a crashed book's old lines from participating in detected arb opportunities.

### Scraper Implementation Approach

Each scraper is developed through iterative site inspection. The general pattern for a Playwright scraper:

```python
async def fetch_odds(self) -> list[OddsRecord]:
    context = await self.browser.new_context(user_agent=random.choice(UA_LIST))
    await stealth_async(context)
    page = await context.new_page()
    try:
        await page.goto(self.ODDS_URL, wait_until="networkidle", timeout=30_000)
        await page.wait_for_selector(self.ODDS_CONTAINER_SELECTOR, timeout=15_000)
        await asyncio.sleep(random.uniform(0.8, 2.5))
        # site-specific extraction logic
        return records
    finally:
        await context.close()
```

Each scraper module documents its own `ODDS_URL`, `ODDS_CONTAINER_SELECTOR`, and extraction logic as inline comments discovered during development. These cannot be pre-specified without live site inspection.

---

### Event Name Normalization

**Team lookup table:** A hardcoded `data/teams.json` file maps raw scraped token variations to canonical team names. Schema:

```json
{
  "teams": {
    "EDM": "Edmonton Oilers",
    "Edmonton": "Edmonton Oilers",
    "Oilers": "Edmonton Oilers",
    "CGY": "Calgary Flames",
    "Calgary": "Calgary Flames",
    "Flames": "Calgary Flames"
  }
}
```

Keys are the raw tokens that appear in sportsbook event names. Values are the canonical full team names. The file is maintained manually as new variations are discovered. If a token is not found in the lookup, it is used as-is (no error).

**Normalization steps:**
1. Strip leading/trailing whitespace, lowercase.
2. Replace " at ", " @ ", " v ", " vs. " with " vs ".
3. Split on " vs " to get two team tokens.
4. Look each token up in the team lookup table; if not found, use as-is.
5. Canonical event name: `"{team_A} vs {team_B}"` (alphabetical order of canonical names).

**Event matching across books:** Two `OddsRecord`s are considered the same event if:
- Their canonical `event_name` matches exactly (after normalization), **OR**
- Their fuzzy similarity score (RapidFuzz `token_sort_ratio`) ≥ **85**, AND
- Their `event_start` times are within **60 minutes** of each other.

### Market and Outcome Normalization

Each scraper maps the book's raw market/outcome labels to canonical values before returning `OddsRecord`s:

| Book raw | Canonical market | Canonical outcome |
|----------|-----------------|-------------------|
| "Moneyline", "Match Winner", "1X2" | "moneyline" | "home", "away", "draw" |
| "Totals", "Over/Under" | "totals" | "over", "under" |
| "Spread", "Puck Line", "Run Line" | "spread" | "home", "away" |

Each scraper module is responsible for its own mapping. Unrecognized markets are skipped with a warning log.

---

## Arbitrage Detection

### Prerequisite: Cross-Book Only

An opportunity is only valid if each outcome comes from a **different book**. Same-book combinations are excluded.

### Two-Way Market

Applies to: `moneyline` (home/away only, e.g. NHL, NBA, NFL), `totals` (over/under), `spread` (home/away).

```
arb_sum = (1/odds_A) + (1/odds_B)
if arb_sum < 1.0 and (1 - arb_sum) >= 0.005:
    margin = 1 - arb_sum  # e.g. 0.018 = 1.8%
```

Required: the two outcomes must come from **different books**.

### Three-Way Market

Applies to: `moneyline` markets with a draw outcome (e.g. soccer/MLS — home/draw/away). Canonical outcomes: `"home"`, `"draw"`, `"away"`.

```
arb_sum = (1/odds_home) + (1/odds_draw) + (1/odds_away)
if arb_sum < 1.0 and (1 - arb_sum) >= 0.005:
    margin = 1 - arb_sum
```

Required: **each of the three outcomes must come from a different book** (no two outcomes from the same book). If only two books offer all three outcomes, the best odds for the third outcome are taken from whichever of those two books offers the higher price for it — as long as no single book covers more than one outcome in the arb.

### Algorithm (per cycle)

1. Filter all `OddsRecord`s to exclude records older than 3 minutes.
2. Group records by `(sport, canonical_event_name, market)`.
3. For each group: find the best (highest) `decimal_odds` per `outcome` across all books. If any outcome's best odds come from only one book, it is still valid — but the arb check ensures the outcomes used come from different books.
4. For each outcome combination: verify outcomes are from different books.
5. Calculate `arb_sum`. If `< 1.0` and margin ≥ 0.5%, create an `Opportunity`.
6. Assign each opportunity a stable ID: `sha256(sport + event_name + market)[:12]`.
7. Diff against previous opportunity set: detect newly appeared and newly expired IDs.

### Opportunity Identity and Deduplication

An opportunity is considered **the same** across cycles if its ID (based on sport + event_name + market) is unchanged. If odds update but the arb still exists, it is treated as an **update** (not new) — the WebSocket sends `opportunity_updated`, not `new_opportunity`.

### Opportunity Expiry

An opportunity is expired (and `opportunity_expired` WS event emitted) when **any** of the following are true on a re-scrape:
1. The arb_sum recalculated from current (non-stale) odds is ≥ 1.0 — the arb no longer exists.
2. One or more of the contributing odds records has become stale (>3 min old) and no fresher substitute from any other book keeps the arb valid.
3. The `event_start` time has passed — the game has started.

### Opportunity Data Model

```python
@dataclass
class Opportunity:
    id: str                     # sha256-based stable ID
    sport: str
    event_name: str
    event_start: datetime
    market: str
    margin: float               # e.g. 0.018 for 1.8%
    arb_sum: float
    outcomes: list[OpportunityLeg]  # one per outcome
    detected_at: datetime
    updated_at: datetime

@dataclass
class OpportunityLeg:
    outcome: str        # "home", "away", etc.
    book: str
    decimal_odds: float
    recommended_stake: float  # calculated at $100 bankroll default; frontend recalculates
```

---

## Stake Calculator

### Generalized Formula (N outcomes)

```python
def calculate_stakes(bankroll: float, legs: list[OpportunityLeg]) -> list[float]:
    implied = [1 / leg.decimal_odds for leg in legs]
    arb_sum = sum(implied)
    return [bankroll * imp / arb_sum for imp in implied]
```

This works for both 2-way and 3-way markets.

### Rounding

Stakes are displayed rounded to **2 decimal places** (nearest cent). No floor/ceil — raw float rounded. The spec does not enforce minimum bet sizes; this is left to the user's discretion.

---

## Backend API

### Project Structure

```
backend/
├── main.py                 # FastAPI app, lifespan startup/shutdown
├── scheduler.py            # APScheduler setup + scrape cycle orchestration
├── scrapers/
│   ├── base.py             # OddsScraper ABC + OddsRecord dataclass
│   ├── playalberta.py
│   ├── betmgm.py
│   ├── fanduel.py
│   ├── bet365.py
│   ├── sportsinteraction.py
│   └── betway.py
├── calculator.py           # Arb detection + stake math + Opportunity dataclass
├── store.py                # In-memory store: odds + opportunities + book status
├── normalizer.py           # Team name + market/outcome normalization
├── ws.py                   # WebSocket connection manager
└── data/
    └── teams.json          # Team name lookup table
```

### In-Memory Store (`store.py`)

```python
class Store:
    odds: dict[str, list[OddsRecord]]       # keyed by book name
    opportunities: dict[str, Opportunity]   # keyed by opportunity.id
    book_status: dict[str, BookStatus]      # keyed by book name

@dataclass
class BookStatus:
    name: str
    status: str          # "ok" | "error" | "stale"
    last_scraped_at: datetime | None
    record_count: int
    last_error: str | None
```

### CORS

FastAPI is configured with `CORSMiddleware` allowing `http://localhost:5173` (Vite dev server) in development.

### APScheduler Configuration

```python
scheduler.add_job(
    run_scrape_cycle,
    trigger=IntervalTrigger(seconds=45),
    max_instances=1,          # skip cycle if previous is still running
    misfire_grace_time=10,    # if delayed up to 10s, still run; otherwise skip
)
```

`max_instances=1` ensures a slow cycle does not overlap with the next trigger.

### Endpoints

#### `GET /api/opportunities`

Returns all current arb opportunities, sorted by `margin` descending.

```json
{
  "opportunities": [
    {
      "id": "a3f9bc1d2e4f",
      "sport": "nhl",
      "event_name": "Edmonton Oilers vs Calgary Flames",
      "event_start": "2026-03-17T23:00:00Z",
      "market": "moneyline",
      "margin": 0.018,
      "arb_sum": 0.982,
      "detected_at": "2026-03-17T19:42:11Z",
      "updated_at": "2026-03-17T19:43:01Z",
      "outcomes": [
        {
          "outcome": "home",
          "book": "betmgm",
          "decimal_odds": 2.10,
          "recommended_stake": 47.62
        },
        {
          "outcome": "away",
          "book": "fanduel",
          "decimal_odds": 2.20,
          "recommended_stake": 52.38
        }
      ]
    }
  ]
}
```

#### `GET /api/odds`

Returns current raw odds records per book (for debugging/inspection), filtered to non-stale records only.

```json
{
  "books": {
    "betmgm": {
      "record_count": 142,
      "scraped_at": "2026-03-17T19:43:00Z",
      "records": [ /* array of OddsRecord objects */ ]
    }
  }
}
```

#### `GET /api/books`

```json
{
  "books": [
    {
      "name": "betmgm",
      "status": "ok",
      "last_scraped_at": "2026-03-17T19:43:00Z",
      "record_count": 142,
      "last_error": null
    },
    {
      "name": "bet365",
      "status": "error",
      "last_scraped_at": "2026-03-17T19:40:00Z",
      "record_count": 0,
      "last_error": "TimeoutError: page did not load within 30s"
    }
  ]
}
```

#### `WS /ws`

WebSocket messages (JSON, one per send). All timestamps are ISO 8601 UTC strings.

```json
// New opportunity detected (first time this ID is seen)
{
  "type": "new_opportunity",
  "data": { /* full Opportunity object — same shape as item in GET /api/opportunities */ }
}

// Existing opportunity's odds changed but arb still valid
{
  "type": "opportunity_updated",
  "data": { /* full Opportunity object with updated decimal_odds and recommended_stake values */ }
}

// Opportunity is no longer valid (arb gone, stale, or event started)
{
  "type": "opportunity_expired",
  "id": "a3f9bc1d2e4f"
}

// A book's scrape completed successfully this cycle
// Fires once per book per cycle, immediately after that book's scraper returns
{
  "type": "odds_updated",
  "book": "betmgm",
  "status": "ok",
  "record_count": 142,
  "scraped_at": "2026-03-17T19:43:00Z"
}

// Emitted once after all scrapers complete and arb detection finishes for a cycle
{
  "type": "scrape_cycle_complete",
  "duration_s": 38,
  "opportunity_count": 3,
  "books_ok": 5,
  "books_error": 1,
  "timestamp": "2026-03-17T19:43:01Z"
}
```

---

## Frontend Dashboard

### Project Structure

```
frontend/
├── src/
│   ├── App.jsx
│   ├── components/
│   │   ├── OpportunitiesTable.jsx   # Main arb table with expandable rows
│   │   ├── StakeCalculator.jsx      # Bankroll input + per-outcome stakes display
│   │   ├── BookStatusBar.jsx        # Per-book health indicators
│   │   └── AlertSound.jsx           # Audio chime + yellow flash trigger
│   ├── hooks/
│   │   ├── useWebSocket.js          # WS connection with exponential backoff reconnect
│   │   └── useOpportunities.js      # Opportunity state: map keyed by id
│   └── api.js                       # REST fetch helpers (initial load)
```

### Bankroll Input

The bankroll amount is a **global input** displayed at the top of the page. All rows in the OpportunitiesTable reflect the same bankroll value. When the user changes it, all stake displays update reactively. Default value: `$100`.

### StakeCalculator Component

Integrated inline within each expanded row of OpportunitiesTable. It reads the global bankroll from context and displays:
- Stake per outcome (book + amount)
- Guaranteed profit (dollar amount + %)
- Recalculates on every bankroll change

### BookStatusBar

Displays one badge per book. Data sourced from WebSocket `odds_updated` messages (updated live) and initial `GET /api/books` fetch on load.

Badge states:
- `ok` — green, shows time since last scrape (e.g. "BetMGM · 12s ago")
- `error` — red, shows book name + error indicator
- `stale` — yellow, last scrape > 3 min ago

### WebSocket Reconnect Strategy (useWebSocket)

On disconnect:
1. Wait 1s, attempt reconnect.
2. On failure: exponential backoff — 1s, 2s, 4s, 8s, up to max 30s.
3. No maximum retry count — keep trying indefinitely.
4. On reconnect: re-fetch `GET /api/opportunities` to sync state.

### Alert Behaviour

- `new_opportunity` message → row flashes yellow CSS animation for 3 seconds → new row pinned to top of table for 10 seconds before sorting normalizes.
- Chime: synthesized via Web Audio API (`OscillatorNode`, 880Hz, 100ms, triangle wave, fade out). No audio file required.
- Sound toggle button in header (🔔 / 🔕). Default: on.

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  ARB FINDER — Alberta       Bankroll: [$100    ]   🔔      │
│  [BetMGM ✓ 12s] [FanDuel ✓ 8s] [Bet365 ✗ err] ...         │
├─────────────────────────────────────────────────────────────┤
│  Sport │ Event                  │ Market │ Profit │ Books   │
│────────┼────────────────────────┼────────┼────────┼─────────│
│  🏒 NHL│ Edmonton vs Calgary    │ ML     │ +1.8%  │ [▼]    │
│        │  home: BetMGM 2.10  → stake $47.62                │
│        │  away: FanDuel 2.20 → stake $52.38                │
│        │  Guaranteed profit: $1.80                          │
│────────┼────────────────────────┼────────┼────────┼─────────│
│  ⚽ MLS│ ...                    │ ...    │ +0.9%  │ [▼]    │
└─────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | Python | 3.11+ |
| Web framework | FastAPI + Uvicorn | latest |
| Browser automation | Playwright (async) | latest |
| Anti-bot | playwright-stealth | latest |
| Scheduling | APScheduler | 3.x |
| Fuzzy matching | RapidFuzz | latest |
| Frontend | React + Vite | React 18, Vite 5 |
| Styling | Plain CSS | — |

---

## Running the App Locally

### Prerequisites

- Python 3.11+
- Node.js 18+ (for Vite/React)

### Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium     # installs Chromium browser binary
uvicorn main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev                     # starts Vite dev server on http://localhost:5173
```

### Environment / Config

A `backend/.env` file (not committed) controls:
```
SCRAPE_INTERVAL_SECONDS=45
MIN_ARB_MARGIN=0.005
ODDS_STALE_SECONDS=180
ODDS_EVICT_SECONDS=600
CORS_ORIGIN=http://localhost:5173
```

---

## Out of Scope (v1)

- User accounts or authentication
- Historical opportunity tracking / logging to disk
- Email or push notification delivery
- The Odds API integration
- Provinces outside Alberta
- Mobile-optimized layout
- Proxy rotation
- Minimum bet size enforcement in stake calculator
