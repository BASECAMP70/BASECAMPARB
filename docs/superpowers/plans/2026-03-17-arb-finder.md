# Alberta Arb Finder Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real-time web dashboard that scrapes Alberta-legal sportsbooks every 45s, detects arbitrage opportunities, and displays them with live stake calculations and audio/visual alerts.

**Architecture:** Python FastAPI backend with Playwright scrapers (one context per book per cycle, concurrent via asyncio.gather), in-memory store, WebSocket push. React 18 + Vite frontend consumes REST on load then receives live updates over WebSocket.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Playwright (async), playwright-stealth, APScheduler 3.x, RapidFuzz, React 18, Vite 5, plain CSS.

**Spec:** `docs/superpowers/specs/2026-03-17-arb-finder-design.md`

---

## File Map

```
backend/
├── requirements.txt
├── .env.example
├── main.py                      # FastAPI app, lifespan, CORS, mounts routes + WS
├── config.py                    # Reads .env via os.getenv with defaults
├── store.py                     # Store, BookStatus — in-memory state
├── normalizer.py                # normalize_event_name(), normalize_market_outcome()
├── calculator.py                # Opportunity, OpportunityLeg, detect_arbs(), calculate_stakes()
├── serializers.py               # _serialize_opportunity() — avoids circular import
├── scheduler.py                 # APScheduler setup, run_scrape_cycle()
├── ws.py                        # WebSocketManager (broadcast helpers)
├── scrapers/
│   ├── __init__.py
│   ├── base.py                  # OddsScraper ABC, OddsRecord dataclass, UA_LIST
│   ├── playalberta.py
│   ├── betmgm.py
│   ├── fanduel.py
│   ├── bet365.py
│   ├── sportsinteraction.py
│   └── betway.py
└── data/
    └── teams.json

tests/
├── test_normalizer.py
├── test_calculator.py
└── test_store.py

frontend/
├── package.json
├── vite.config.js
└── src/
    ├── App.jsx                  # Root layout, BankrollContext, assembles all components
    ├── App.css
    ├── api.js                   # fetchOpportunities(), fetchBooks()
    ├── hooks/
    │   ├── useWebSocket.js      # WS with exponential backoff reconnect
    │   └── useOpportunities.js  # Opportunity map state, applies WS events
    └── components/
        ├── BookStatusBar.jsx    # Per-book health badges
        ├── OpportunitiesTable.jsx  # Expandable arb rows, yellow flash
        ├── StakeCalculator.jsx  # Inline stake display per expanded row
        └── AlertSound.jsx       # Web Audio API chime + sound toggle
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/data/teams.json`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/scrapers backend/data tests frontend/src/components frontend/src/hooks
touch backend/scrapers/__init__.py
```

- [ ] **Step 2: Create `backend/requirements.txt`**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
playwright==1.44.0
playwright-stealth==1.0.6
apscheduler==3.10.4
rapidfuzz==3.9.0
python-dotenv==1.0.1
pytest==8.2.0
pytest-asyncio==0.23.6
httpx==0.27.0
```

- [ ] **Step 3: Create `backend/.env.example`**

```
SCRAPE_INTERVAL_SECONDS=45
MIN_ARB_MARGIN=0.005
ODDS_STALE_SECONDS=180
ODDS_EVICT_SECONDS=600
CORS_ORIGIN=http://localhost:5173
```

Copy to `backend/.env` (not committed).

- [ ] **Step 4: Create `backend/data/teams.json`**

```json
{
  "teams": {
    "EDM": "Edmonton Oilers",
    "Edmonton": "Edmonton Oilers",
    "Oilers": "Edmonton Oilers",
    "CGY": "Calgary Flames",
    "Calgary": "Calgary Flames",
    "Flames": "Calgary Flames",
    "TOR": "Toronto Maple Leafs",
    "Toronto": "Toronto Maple Leafs",
    "VAN": "Vancouver Canucks",
    "Vancouver": "Vancouver Canucks",
    "Canucks": "Vancouver Canucks",
    "WPG": "Winnipeg Jets",
    "Winnipeg": "Winnipeg Jets",
    "Jets": "Winnipeg Jets",
    "MTL": "Montreal Canadiens",
    "Montreal": "Montreal Canadiens",
    "OTT": "Ottawa Senators",
    "Ottawa": "Ottawa Senators"
  }
}
```

- [ ] **Step 5: Install backend dependencies**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Expected: no errors. `playwright install chromium` downloads ~150MB Chromium binary.

- [ ] **Step 6: Create frontend Vite project**

```bash
cd frontend
npm create vite@latest . -- --template react
npm install
```

Expected: `frontend/src/App.jsx`, `frontend/vite.config.js`, etc. created.

- [ ] **Step 7: Initialize git and commit scaffold**

```bash
cd /c/Users/scott/ARB
git init
echo "backend/.venv/" >> .gitignore
echo "backend/.env" >> .gitignore
echo "node_modules/" >> .gitignore
echo ".superpowers/" >> .gitignore
git add .
git commit -m "chore: initial project scaffold"
```

---

## Task 2: Core Data Models

**Files:**
- Create: `backend/scrapers/base.py`
- Create: `backend/config.py`

- [ ] **Step 1: Create `backend/config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

SCRAPE_INTERVAL_SECONDS = int(os.getenv("SCRAPE_INTERVAL_SECONDS", "45"))
MIN_ARB_MARGIN = float(os.getenv("MIN_ARB_MARGIN", "0.005"))
ODDS_STALE_SECONDS = int(os.getenv("ODDS_STALE_SECONDS", "180"))
ODDS_EVICT_SECONDS = int(os.getenv("ODDS_EVICT_SECONDS", "600"))
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "http://localhost:5173")
```

- [ ] **Step 2: Create `backend/scrapers/base.py`**

```python
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]


@dataclass
class OddsRecord:
    book: str           # e.g. "betmgm"
    sport: str          # canonical: "nhl", "nfl", "nba", "mlb", "mls", "soccer"
    event_name: str     # canonical normalized name
    event_start: datetime   # UTC
    market: str         # canonical: "moneyline", "totals", "spread"
    outcome: str        # canonical: "home", "away", "over", "under", "draw"
    decimal_odds: float
    scraped_at: datetime    # UTC


class OddsScraper(ABC):
    BOOK_NAME: str = ""         # override in subclass, e.g. "betmgm"
    ODDS_URL: str = ""          # override in subclass
    ODDS_CONTAINER_SELECTOR: str = ""  # override in subclass

    def __init__(self, browser):
        self.browser = browser

    @abstractmethod
    async def fetch_odds(self) -> list[OddsRecord]:
        """Navigate to book's odds page and return all available pre-game records."""
```

- [ ] **Step 3: Commit**

```bash
git add backend/scrapers/base.py backend/config.py
git commit -m "feat: core data models and config"
```

---

## Task 3: Normalizer

**Files:**
- Create: `backend/normalizer.py`
- Create: `tests/test_normalizer.py`

- [ ] **Step 1: Write failing tests in `tests/test_normalizer.py`**

```python
import pytest
from normalizer import normalize_event_name, normalize_market_outcome

def test_normalize_basic_vs():
    assert normalize_event_name("Edmonton Oilers vs Calgary Flames") == \
        "Calgary Flames vs Edmonton Oilers"

def test_normalize_at_separator():
    assert normalize_event_name("Calgary Flames at Edmonton Oilers") == \
        "Calgary Flames vs Edmonton Oilers"

def test_normalize_at_symbol():
    assert normalize_event_name("CGY @ EDM") == \
        "Calgary Flames vs Edmonton Oilers"

def test_normalize_unknown_team():
    result = normalize_event_name("Team A vs Team B")
    assert result == "team a vs team b"

def test_normalize_alphabetical_order():
    a = normalize_event_name("Winnipeg Jets vs Edmonton Oilers")
    b = normalize_event_name("Edmonton Oilers vs Winnipeg Jets")
    assert a == b

def test_normalize_market_moneyline():
    market, outcome = normalize_market_outcome("Match Winner", "Home")
    assert market == "moneyline"
    assert outcome == "home"

def test_normalize_market_1x2():
    market, outcome = normalize_market_outcome("1X2", "Draw")
    assert market == "moneyline"
    assert outcome == "draw"

def test_normalize_market_totals():
    market, outcome = normalize_market_outcome("Over/Under", "Over")
    assert market == "totals"
    assert outcome == "over"

def test_normalize_market_puck_line():
    market, outcome = normalize_market_outcome("Puck Line", "Away")
    assert market == "spread"
    assert outcome == "away"

def test_normalize_market_unknown_returns_none():
    result = normalize_market_outcome("Futures", "Winner")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
source .venv/bin/activate
cd ..
pytest tests/test_normalizer.py -v
```

Expected: `ModuleNotFoundError: No module named 'normalizer'`

- [ ] **Step 3: Create `backend/normalizer.py`**

```python
import json
import re
from pathlib import Path

_TEAMS_PATH = Path(__file__).parent / "data" / "teams.json"
_teams: dict[str, str] = {}


def _load_teams() -> dict[str, str]:
    global _teams
    if not _teams:
        data = json.loads(_TEAMS_PATH.read_text())
        _teams = data["teams"]
    return _teams


_MARKET_MAP: dict[str, str] = {
    "moneyline": "moneyline",
    "match winner": "moneyline",
    "1x2": "moneyline",
    "totals": "totals",
    "over/under": "totals",
    "spread": "spread",
    "puck line": "spread",
    "run line": "spread",
}

_OUTCOME_MAP: dict[str, str] = {
    "home": "home",
    "away": "away",
    "draw": "draw",
    "over": "over",
    "under": "under",
    "1": "home",
    "2": "away",
    "x": "draw",
}


def normalize_event_name(raw: str) -> str:
    """Return canonical event name: 'Team A vs Team B' in alphabetical order."""
    teams = _load_teams()
    s = raw.strip().lower()
    # Normalize separators
    s = re.sub(r"\s+at\s+", " vs ", s)
    s = re.sub(r"\s+@\s+", " vs ", s)
    s = re.sub(r"\s+v\s+", " vs ", s)
    s = re.sub(r"\s+vs\.\s+", " vs ", s)
    parts = s.split(" vs ", 1)
    if len(parts) != 2:
        return s  # can't parse, return as-is
    token_a = parts[0].strip()
    token_b = parts[1].strip()
    # Look up each token — try original case first, then normalized
    raw_parts = raw.strip()
    raw_sep = re.split(r"\s+(?:at|@|vs?\.?)\s+", raw_parts, maxsplit=1)
    if len(raw_sep) == 2:
        raw_a, raw_b = raw_sep[0].strip(), raw_sep[1].strip()
        team_a = teams.get(raw_a, teams.get(token_a, token_a))
        team_b = teams.get(raw_b, teams.get(token_b, token_b))
    else:
        team_a = teams.get(token_a, token_a)
        team_b = teams.get(token_b, token_b)
    # Alphabetical order
    pair = sorted([team_a, team_b])
    return f"{pair[0]} vs {pair[1]}"


def normalize_market_outcome(raw_market: str, raw_outcome: str) -> tuple[str, str] | None:
    """Return (canonical_market, canonical_outcome) or None if unrecognized."""
    market = _MARKET_MAP.get(raw_market.strip().lower())
    if market is None:
        return None
    outcome = _OUTCOME_MAP.get(raw_outcome.strip().lower())
    if outcome is None:
        return None
    return market, outcome
```

- [ ] **Step 4: Run tests from project root with PYTHONPATH set**

```bash
cd /c/Users/scott/ARB
PYTHONPATH=backend pytest tests/test_normalizer.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/normalizer.py tests/test_normalizer.py
git commit -m "feat: event and market normalizer with tests"
```

---

## Task 4: In-Memory Store

**Files:**
- Create: `backend/store.py`
- Create: `tests/test_store.py`

- [ ] **Step 1: Write failing tests in `tests/test_store.py`**

```python
import pytest
from datetime import datetime, timezone, timedelta
from scrapers.base import OddsRecord
from store import Store, BookStatus


def make_record(book="betmgm", scraped_at=None):
    return OddsRecord(
        book=book,
        sport="nhl",
        event_name="Calgary Flames vs Edmonton Oilers",
        event_start=datetime(2026, 3, 17, 23, 0, tzinfo=timezone.utc),
        market="moneyline",
        outcome="home",
        decimal_odds=2.10,
        scraped_at=scraped_at or datetime.now(timezone.utc),
    )


def test_update_and_get_records():
    store = Store()
    records = [make_record("betmgm")]
    store.update_book("betmgm", records, None)
    assert store.get_records("betmgm") == records


def test_stale_records_excluded():
    store = Store(stale_seconds=180, evict_seconds=600)
    old = make_record("betmgm", scraped_at=datetime.now(timezone.utc) - timedelta(seconds=200))
    store.update_book("betmgm", [old], None)
    fresh = store.get_fresh_records()
    assert fresh == []


def test_fresh_records_included():
    store = Store(stale_seconds=180, evict_seconds=600)
    rec = make_record("betmgm")
    store.update_book("betmgm", [rec], None)
    assert store.get_fresh_records() == [rec]


def test_eviction():
    store = Store(stale_seconds=180, evict_seconds=600)
    old = make_record("betmgm", scraped_at=datetime.now(timezone.utc) - timedelta(seconds=700))
    store.update_book("betmgm", [old], None)
    store.evict_stale()
    assert store.get_records("betmgm") == []


def test_book_status_ok():
    store = Store()
    store.update_book("betmgm", [make_record()], None)
    status = store.get_book_status()
    assert status["betmgm"].status == "ok"
    assert status["betmgm"].record_count == 1


def test_book_status_error():
    store = Store()
    store.update_book("bet365", [], "TimeoutError")
    status = store.get_book_status()
    assert status["bet365"].status == "error"
    assert status["bet365"].last_error == "TimeoutError"


def test_retain_records_on_error():
    store = Store()
    rec = make_record("betmgm")
    store.update_book("betmgm", [rec], None)
    # Simulate failed cycle — pass error, no new records
    store.update_book("betmgm", None, "Timeout")
    # Old records retained
    assert store.get_records("betmgm") == [rec]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=backend pytest tests/test_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'store'`

- [ ] **Step 3: Create `backend/store.py`**

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from scrapers.base import OddsRecord
from calculator import Opportunity


@dataclass
class BookStatus:
    name: str
    status: str                  # "ok" | "error" | "stale"
    last_scraped_at: datetime | None = None
    record_count: int = 0
    last_error: str | None = None


class Store:
    def __init__(self, stale_seconds: int = 180, evict_seconds: int = 600):
        self._stale_seconds = stale_seconds
        self._evict_seconds = evict_seconds
        self._odds: dict[str, list[OddsRecord]] = {}
        self._opportunities: dict[str, Opportunity] = {}
        self._book_status: dict[str, BookStatus] = {}

    def update_book(self, book: str, records: list[OddsRecord] | None, error: str | None):
        """Update store after a scrape attempt. Pass error=None on success."""
        now = datetime.now(timezone.utc)
        if error is not None:
            prev = self._book_status.get(book)
            self._book_status[book] = BookStatus(
                name=book,
                status="error",
                last_scraped_at=prev.last_scraped_at if prev else None,
                record_count=len(self._odds.get(book, [])),
                last_error=error,
            )
            # Retain existing records — do not overwrite
        else:
            self._odds[book] = records or []
            self._book_status[book] = BookStatus(
                name=book,
                status="ok",
                last_scraped_at=now,
                record_count=len(records or []),
                last_error=None,
            )

    def get_records(self, book: str) -> list[OddsRecord]:
        return self._odds.get(book, [])

    def get_fresh_records(self) -> list[OddsRecord]:
        """Return all records not older than stale_seconds."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._stale_seconds)
        result = []
        for records in self._odds.values():
            result.extend(r for r in records if r.scraped_at >= cutoff)
        return result

    def evict_stale(self):
        """Remove records older than evict_seconds from the store."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._evict_seconds)
        for book in list(self._odds.keys()):
            self._odds[book] = [r for r in self._odds[book] if r.scraped_at >= cutoff]

    def update_opportunities(self, opportunities: dict[str, Opportunity]):
        self._opportunities = opportunities

    def get_opportunities(self) -> dict[str, Opportunity]:
        return self._opportunities

    def get_book_status(self) -> dict[str, BookStatus]:
        # Mark books as stale if last scrape > stale_seconds ago
        now = datetime.now(timezone.utc)
        result = {}
        for book, status in self._book_status.items():
            s = status
            if (
                status.status == "ok"
                and status.last_scraped_at
                and (now - status.last_scraped_at).total_seconds() > self._stale_seconds
            ):
                s = BookStatus(
                    name=status.name,
                    status="stale",
                    last_scraped_at=status.last_scraped_at,
                    record_count=status.record_count,
                    last_error=None,
                )
            result[book] = s
        return result
```

Note: `store.py` imports from `calculator.py` (Opportunity). Create a stub for now — we'll fill it in Task 5.

- [ ] **Step 4: Create stub `backend/calculator.py` (enough for import)**

```python
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class OpportunityLeg:
    outcome: str
    book: str
    decimal_odds: float
    recommended_stake: float


@dataclass
class Opportunity:
    id: str
    sport: str
    event_name: str
    event_start: datetime
    market: str
    margin: float
    arb_sum: float
    outcomes: list[OpportunityLeg]
    detected_at: datetime
    updated_at: datetime
```

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=backend pytest tests/test_store.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/store.py backend/calculator.py tests/test_store.py
git commit -m "feat: in-memory store with staleness/eviction and tests"
```

---

## Task 5: Arbitrage Calculator

**Files:**
- Modify: `backend/calculator.py` (replace stub with full implementation)
- Create: `tests/test_calculator.py`

- [ ] **Step 1: Write failing tests in `tests/test_calculator.py`**

```python
import pytest
from datetime import datetime, timezone
from scrapers.base import OddsRecord
from calculator import detect_arbs, calculate_stakes, Opportunity


def make_record(book, outcome, odds, market="moneyline"):
    return OddsRecord(
        book=book,
        sport="nhl",
        event_name="Calgary Flames vs Edmonton Oilers",
        event_start=datetime(2026, 3, 18, 1, 0, tzinfo=timezone.utc),
        market=market,
        outcome=outcome,
        decimal_odds=odds,
        scraped_at=datetime.now(timezone.utc),
    )


def test_two_way_arb_detected():
    records = [
        make_record("betmgm", "home", 2.10),
        make_record("fanduel", "away", 2.20),
    ]
    opps = detect_arbs(records, min_margin=0.005)
    assert len(opps) == 1
    assert opps[0].margin == pytest.approx(1 - (1/2.10 + 1/2.20), abs=1e-6)


def test_no_arb_when_sum_too_high():
    records = [
        make_record("betmgm", "home", 1.90),
        make_record("fanduel", "away", 1.90),
    ]
    opps = detect_arbs(records, min_margin=0.005)
    assert opps == []


def test_same_book_excluded():
    records = [
        make_record("betmgm", "home", 2.10),
        make_record("betmgm", "away", 2.20),  # same book — not valid arb
    ]
    opps = detect_arbs(records, min_margin=0.005)
    assert opps == []


def test_three_way_arb_detected():
    records = [
        make_record("betmgm", "home", 3.20, market="moneyline"),
        make_record("fanduel", "draw", 4.00, market="moneyline"),
        make_record("bet365", "away", 3.30, market="moneyline"),
    ]
    opps = detect_arbs(records, min_margin=0.005)
    assert len(opps) == 1


def test_three_way_same_book_excluded():
    # Only 2 books — home and draw from betmgm, away from fanduel
    records = [
        make_record("betmgm", "home", 3.20),
        make_record("betmgm", "draw", 4.00),
        make_record("fanduel", "away", 3.30),
    ]
    opps = detect_arbs(records, min_margin=0.005)
    assert opps == []


def test_calculate_stakes_two_way():
    from calculator import OpportunityLeg
    legs = [
        OpportunityLeg(outcome="home", book="betmgm", decimal_odds=2.10, recommended_stake=0),
        OpportunityLeg(outcome="away", book="fanduel", decimal_odds=2.20, recommended_stake=0),
    ]
    stakes = calculate_stakes(100.0, legs)
    assert len(stakes) == 2
    assert sum(stakes) == pytest.approx(100.0, abs=0.01)
    # Each return should be approximately equal
    assert stakes[0] * 2.10 == pytest.approx(stakes[1] * 2.20, rel=0.01)


def test_opportunity_id_stable():
    records = [
        make_record("betmgm", "home", 2.10),
        make_record("fanduel", "away", 2.20),
    ]
    opps1 = detect_arbs(records, min_margin=0.005)
    opps2 = detect_arbs(records, min_margin=0.005)
    assert opps1[0].id == opps2[0].id


def test_below_min_margin_excluded():
    # arb_sum = 0.997 → margin = 0.003 < 0.005 threshold
    records = [
        make_record("betmgm", "home", 2.02),
        make_record("fanduel", "away", 2.02),
    ]
    opps = detect_arbs(records, min_margin=0.005)
    assert opps == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=backend pytest tests/test_calculator.py -v
```

Expected: most tests fail (stub calculator has no detect_arbs).

- [ ] **Step 3: Replace `backend/calculator.py` with full implementation**

```python
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations, product

from scrapers.base import OddsRecord


@dataclass
class OpportunityLeg:
    outcome: str
    book: str
    decimal_odds: float
    recommended_stake: float


@dataclass
class Opportunity:
    id: str
    sport: str
    event_name: str
    event_start: datetime
    market: str
    margin: float
    arb_sum: float
    outcomes: list[OpportunityLeg]
    detected_at: datetime
    updated_at: datetime


def _make_id(sport: str, event_name: str, market: str) -> str:
    raw = f"{sport}:{event_name}:{market}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def calculate_stakes(bankroll: float, legs: list[OpportunityLeg]) -> list[float]:
    """Return stake per leg so each returns bankroll + profit."""
    implied = [1 / leg.decimal_odds for leg in legs]
    arb_sum = sum(implied)
    return [round(bankroll * imp / arb_sum, 2) for imp in implied]


def detect_arbs(records: list[OddsRecord], min_margin: float = 0.005) -> list[Opportunity]:
    """Detect cross-book arb opportunities in a list of OddsRecords."""
    now = datetime.now(timezone.utc)

    # Group by (sport, event_name, market)
    groups: dict[tuple, list[OddsRecord]] = {}
    for r in records:
        key = (r.sport, r.event_name, r.market)
        groups.setdefault(key, []).append(r)

    opportunities = []

    for (sport, event_name, market), group in groups.items():
        # Determine expected outcomes for this market
        if market == "moneyline":
            # Check if draw outcome exists → 3-way; else 2-way
            has_draw = any(r.outcome == "draw" for r in group)
            expected_outcomes = ["home", "draw", "away"] if has_draw else ["home", "away"]
        elif market == "totals":
            expected_outcomes = ["over", "under"]
        elif market == "spread":
            expected_outcomes = ["home", "away"]
        else:
            continue

        # Best odds per outcome per book
        # best_per_outcome[outcome] = list of (book, odds)
        best_per_outcome: dict[str, list[tuple[str, float]]] = {}
        for r in group:
            if r.outcome not in expected_outcomes:
                continue
            entry = best_per_outcome.setdefault(r.outcome, [])
            entry.append((r.book, r.decimal_odds))

        # Ensure all expected outcomes have at least one record
        if not all(o in best_per_outcome for o in expected_outcomes):
            continue

        # Sort each outcome's options by odds descending
        for outcome in expected_outcomes:
            best_per_outcome[outcome].sort(key=lambda x: x[1], reverse=True)

        # Try combinations: for each outcome, pick from available (book, odds)
        # Generate candidate leg sets where all books are different
        outcome_options = [best_per_outcome[o] for o in expected_outcomes]

        for combo in product(*outcome_options):
            # combo: ((book, odds), (book, odds), ...)
            books = [c[0] for c in combo]
            if len(set(books)) < len(books):
                continue  # duplicate book — skip

            odds_vals = [c[1] for c in combo]
            arb_sum = sum(1 / o for o in odds_vals)
            margin = 1 - arb_sum

            if arb_sum < 1.0 and margin >= min_margin:
                # Find event_start from first matching record
                event_start = next(
                    r.event_start for r in group if r.outcome == expected_outcomes[0]
                )

                # Build legs (stakes calculated at $100 bankroll default)
                legs = [
                    OpportunityLeg(
                        outcome=expected_outcomes[i],
                        book=combo[i][0],
                        decimal_odds=combo[i][1],
                        recommended_stake=0.0,
                    )
                    for i in range(len(expected_outcomes))
                ]
                stakes = calculate_stakes(100.0, legs)
                for leg, stake in zip(legs, stakes):
                    leg.recommended_stake = stake

                opp = Opportunity(
                    id=_make_id(sport, event_name, market),
                    sport=sport,
                    event_name=event_name,
                    event_start=event_start,
                    market=market,
                    margin=margin,
                    arb_sum=arb_sum,
                    outcomes=legs,
                    detected_at=now,
                    updated_at=now,
                )
                opportunities.append(opp)
                break  # take the best valid combo for this market group

    return opportunities


def diff_opportunities(
    prev: dict[str, Opportunity],
    curr: dict[str, Opportunity],
) -> tuple[list[Opportunity], list[Opportunity], list[str]]:
    """Return (new, updated, expired_ids)."""
    new = [o for id_, o in curr.items() if id_ not in prev]
    updated = [
        o for id_, o in curr.items()
        if id_ in prev and (
            o.margin != prev[id_].margin or
            any(l.decimal_odds != pl.decimal_odds
                for l, pl in zip(o.outcomes, prev[id_].outcomes))
        )
    ]
    expired_ids = [id_ for id_ in prev if id_ not in curr]
    return new, updated, expired_ids
```

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=backend pytest tests/test_calculator.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/calculator.py tests/test_calculator.py
git commit -m "feat: arbitrage calculator with 2-way and 3-way detection"
```

---

## Task 6: WebSocket Manager

**Files:**
- Create: `backend/ws.py`

No unit tests needed — just wiring. Verified via integration in Task 9.

- [ ] **Step 1: Create `backend/ws.py`**

```python
import json
from dataclasses import asdict
from datetime import datetime
from fastapi import WebSocket


def _serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._connections = [c for c in self._connections if c is not ws]

    async def broadcast(self, message: dict):
        payload = json.dumps(message, default=_serialize)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
```

- [ ] **Step 2: Commit**

```bash
git add backend/ws.py
git commit -m "feat: websocket manager with broadcast"
```

---

## Task 7: FastAPI App + API Endpoints

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: Create `backend/main.py`**

```python
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import config
from calculator import Opportunity
from scheduler import start_scheduler, stop_scheduler
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
    allow_methods=["GET"],
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
                    "decimal_odds": r.decimal_odds,
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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive; we only push, don't expect messages
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
```

- [ ] **Step 2: Create `backend/serializers.py`** (avoids circular import between main.py and scheduler.py)

```python
from calculator import Opportunity


def serialize_opportunity(o: Opportunity) -> dict:
    return {
        "id": o.id,
        "sport": o.sport,
        "event_name": o.event_name,
        "event_start": o.event_start.isoformat(),
        "market": o.market,
        "margin": o.margin,
        "arb_sum": o.arb_sum,
        "detected_at": o.detected_at.isoformat(),
        "updated_at": o.updated_at.isoformat(),
        "outcomes": [
            {
                "outcome": leg.outcome,
                "book": leg.book,
                "decimal_odds": leg.decimal_odds,
                "recommended_stake": leg.recommended_stake,
            }
            for leg in o.outcomes
        ],
    }
```

- [ ] **Step 3: Create stub `backend/scheduler.py`** (just enough to import)

```python
async def start_scheduler(store, ws_manager):
    pass  # filled in Task 8

async def stop_scheduler():
    pass
```

- [ ] **Step 3: Verify app starts**

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --port 8000
```

Expected: `Application startup complete.` with no errors. Ctrl+C to stop.

- [ ] **Step 4: Commit**

```bash
git add backend/main.py backend/scheduler.py
git commit -m "feat: fastapi app with REST endpoints and websocket"
```

---

## Task 8: Scheduler + Scrape Cycle

**Files:**
- Modify: `backend/scheduler.py`

- [ ] **Step 1: Replace `backend/scheduler.py` with full implementation**

```python
import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import config
from calculator import detect_arbs, diff_opportunities
from serializers import serialize_opportunity
from scrapers.betmgm import BetMGMScraper
from scrapers.bet365 import Bet365Scraper
from scrapers.betway import BetwayScraper
from scrapers.fanduel import FanDuelScraper
from scrapers.playalberta import PlayAlbertaScraper
from scrapers.sportsinteraction import SportsInteractionScraper

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_playwright = None
_browser = None
_scrapers = []


async def start_scheduler(store, ws_manager):
    global _scheduler, _playwright, _browser, _scrapers

    from playwright.async_api import async_playwright
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(headless=True)

    scraper_classes = [
        PlayAlbertaScraper,
        BetMGMScraper,
        FanDuelScraper,
        Bet365Scraper,
        SportsInteractionScraper,
        BetwayScraper,
    ]
    _scrapers = [cls(_browser) for cls in scraper_classes]

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

    # Push WS events
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/scheduler.py
git commit -m "feat: scrape cycle orchestration with APScheduler"
```

---

## Task 9: Scraper Base Pattern + PlayAlberta

**Files:**
- Create: `backend/scrapers/playalberta.py`
- Pattern applies to all subsequent scrapers

**Note:** Scrapers require live site inspection to determine selectors. Each scraper follows the same structural pattern — only `ODDS_URL`, `ODDS_CONTAINER_SELECTOR`, and the extraction block differ. The pattern is established here; Tasks 10–14 fill in site-specific details.

- [ ] **Step 1: Create `backend/scrapers/playalberta.py` with inspection stub**

```python
"""
PlayAlberta scraper.

DEVELOPMENT NOTE: Before implementing extraction logic, run the inspection script:
    PYTHONPATH=backend python -c "
    import asyncio
    from playwright.async_api import async_playwright
    from playwright_stealth import stealth_async

    async def inspect():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            await stealth_async(context)
            page = await context.new_page()
            await page.goto('https://www.playalberta.ca/sports', wait_until='networkidle')
            await page.pause()  # opens Playwright inspector
            await browser.close()
    asyncio.run(inspect())
    "
Use the inspector to find the CSS selectors for event names, odds, and markets.
Then fill in ODDS_CONTAINER_SELECTOR and the extraction logic below.
"""
import asyncio
import logging
import random
from datetime import datetime, timezone

from playwright_stealth import stealth_async

from normalizer import normalize_event_name, normalize_market_outcome
from scrapers.base import OddsRecord, OddsScraper, UA_LIST

logger = logging.getLogger(__name__)


class PlayAlbertaScraper(OddsScraper):
    BOOK_NAME = "playalberta"
    ODDS_URL = "https://www.playalberta.ca/sports"
    ODDS_CONTAINER_SELECTOR = ".sports-event-list"  # UPDATE after inspection

    async def fetch_odds(self) -> list[OddsRecord]:
        context = await self.browser.new_context(user_agent=random.choice(UA_LIST))
        await stealth_async(context)
        page = await context.new_page()
        records = []
        try:
            await page.goto(self.ODDS_URL, wait_until="networkidle", timeout=30_000)
            await page.wait_for_selector(self.ODDS_CONTAINER_SELECTOR, timeout=15_000)
            await asyncio.sleep(random.uniform(0.8, 2.5))

            # TODO: implement extraction after live inspection
            # Pattern:
            #   events = await page.query_selector_all(".event-row")
            #   for event in events:
            #       raw_name = await event.query_selector_eval(".event-name", "el => el.innerText")
            #       raw_start = await event.query_selector_eval(".event-time", "el => el.dataset.timestamp")
            #       markets = await event.query_selector_all(".market-row")
            #       for market_el in markets:
            #           raw_market = ...
            #           for outcome_el in outcomes:
            #               raw_outcome = ...
            #               raw_odds = float(...)
            #               normalized = normalize_market_outcome(raw_market, raw_outcome)
            #               if normalized is None:
            #                   continue
            #               market, outcome = normalized
            #               records.append(OddsRecord(
            #                   book=self.BOOK_NAME,
            #                   sport=detect_sport(raw_name),  # helper TBD
            #                   event_name=normalize_event_name(raw_name),
            #                   event_start=parse_timestamp(raw_start),
            #                   market=market,
            #                   outcome=outcome,
            #                   decimal_odds=raw_odds,
            #                   scraped_at=datetime.now(timezone.utc),
            #               ))

        except Exception as e:
            logger.warning("PlayAlberta scrape failed: %s", e)
            raise
        finally:
            await context.close()
        return records
```

- [ ] **Step 2: Commit stub scraper**

```bash
git add backend/scrapers/playalberta.py
git commit -m "feat: playalberta scraper stub with inspection pattern"
```

- [ ] **Step 3: Run live inspection to discover selectors**

```bash
cd backend && source .venv/bin/activate
python -c "
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        await stealth_async(context)
        page = await context.new_page()
        await page.goto('https://www.playalberta.ca/sports', wait_until='networkidle')
        await page.pause()
        await browser.close()
asyncio.run(inspect())
"
```

Use the Playwright inspector (DevTools) to identify selectors. Document findings as inline comments in the scraper.

- [ ] **Step 4: Implement extraction logic and commit**

Fill in the `# TODO` section with actual selectors and parsing. Then:

```bash
git add backend/scrapers/playalberta.py
git commit -m "feat: playalberta scraper extraction logic"
```

---

## Task 10: BetMGM Scraper

**Files:**
- Create: `backend/scrapers/betmgm.py`

Follow identical pattern as Task 9. URL: `https://www.betmgm.ca/en/sports`.

- [ ] **Step 1: Create stub using playalberta.py as template** — change `BOOK_NAME`, `ODDS_URL`, class name.
- [ ] **Step 2: Run live inspection** at `https://www.betmgm.ca/en/sports`.
- [ ] **Step 3: Implement extraction and commit.**

---

## Task 11: FanDuel Scraper

**Files:**
- Create: `backend/scrapers/fanduel.py`

URL: `https://www.fanduel.com/en-CA/sports`. Same pattern.

- [ ] **Step 1: Create stub.**
- [ ] **Step 2: Run live inspection.**
- [ ] **Step 3: Implement extraction and commit.**

---

## Task 12: Bet365 Scraper

**Files:**
- Create: `backend/scrapers/bet365.py`

URL: `https://www.bet365.ca`. Heavy anti-bot. If blocked, try: set `ODDS_URL` to the specific sport sub-page (e.g. `/en/sports/17/canada/`), increase stealth, and use a longer random delay (2–5s). If Cloudflare blocks all attempts, mark as `status="blocked"` and skip until a workaround is found.

- [ ] **Step 1: Create stub.**
- [ ] **Step 2: Run live inspection.** If Cloudflare presents a challenge page, note this in a comment — the scraper may need additional handling.
- [ ] **Step 3: Implement extraction (or stub with a clear TODO) and commit.**

---

## Task 13: Sports Interaction Scraper

**Files:**
- Create: `backend/scrapers/sportsinteraction.py`

URL: `https://www.sportsinteraction.com/sports`.

- [ ] **Step 1: Create stub.**
- [ ] **Step 2: Run live inspection.**
- [ ] **Step 3: Implement extraction and commit.**

---

## Task 14: Betway Scraper

**Files:**
- Create: `backend/scrapers/betway.py`

URL: `https://www.betway.ca/en/sport`.

- [ ] **Step 1: Create stub.**
- [ ] **Step 2: Run live inspection.**
- [ ] **Step 3: Implement extraction and commit.**

---

## Task 15: Frontend Scaffold + api.js

**Files:**
- Modify: `frontend/src/App.jsx` (replace Vite default)
- Modify: `frontend/src/App.css` (replace Vite default)
- Create: `frontend/src/api.js`

- [ ] **Step 1: Replace `frontend/src/App.jsx` with minimal shell**

```jsx
import { useState, createContext, useContext } from 'react'
import './App.css'

export const BankrollContext = createContext(100)

export default function App() {
  const [bankroll, setBankroll] = useState(100)
  return (
    <BankrollContext.Provider value={bankroll}>
      <div className="app">
        <header className="app-header">
          <h1>ARB FINDER — Alberta</h1>
          <label className="bankroll-label">
            Bankroll: $
            <input
              type="number"
              value={bankroll}
              min={1}
              onChange={e => setBankroll(Number(e.target.value))}
              className="bankroll-input"
            />
          </label>
        </header>
        <main>
          <p>Loading...</p>
        </main>
      </div>
    </BankrollContext.Provider>
  )
}
```

- [ ] **Step 2: Replace `frontend/src/App.css` with base styles**

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; background: #0f1117; color: #e2e8f0; }

.app-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; background: #1a1d2e; border-bottom: 1px solid #2d3148;
  position: sticky; top: 0; z-index: 10;
}
.app-header h1 { font-size: 1rem; font-weight: 700; letter-spacing: 0.05em; color: #a78bfa; }
.bankroll-label { font-size: 0.85rem; color: #94a3b8; }
.bankroll-input {
  width: 80px; margin-left: 4px; padding: 2px 6px;
  background: #2d3148; border: 1px solid #4a5568; border-radius: 4px;
  color: #e2e8f0; font-size: 0.85rem;
}

.book-status-bar { display: flex; gap: 8px; padding: 8px 20px; flex-wrap: wrap; background: #13152a; }
.book-badge {
  padding: 3px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600;
}
.book-badge.ok { background: #14532d; color: #86efac; }
.book-badge.error { background: #7f1d1d; color: #fca5a5; }
.book-badge.stale { background: #78350f; color: #fcd34d; }

table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 8px 20px; font-size: 0.75rem; color: #64748b;
     border-bottom: 1px solid #2d3148; text-transform: uppercase; letter-spacing: 0.05em; }
td { padding: 10px 20px; border-bottom: 1px solid #1e2235; font-size: 0.875rem; }
tr.expandable:hover { background: #1a1d2e; cursor: pointer; }
tr.expanded-row { background: #141628; }

.profit-badge {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-weight: 700; font-size: 0.8rem; background: #14532d; color: #86efac;
}

.stake-calc { padding: 8px 20px 16px 40px; color: #94a3b8; font-size: 0.85rem; }
.stake-row { margin: 4px 0; }
.stake-profit { margin-top: 8px; font-weight: 600; color: #86efac; }

@keyframes flash-new {
  0% { background: #854d0e; }
  100% { background: transparent; }
}
.new-flash { animation: flash-new 3s ease-out forwards; }

.sound-toggle { background: none; border: none; cursor: pointer; font-size: 1.2rem; padding: 4px; }
```

- [ ] **Step 3: Create `frontend/src/api.js`**

```js
const BASE = 'http://localhost:8000'

export async function fetchOpportunities() {
  const res = await fetch(`${BASE}/api/opportunities`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchBooks() {
  const res = await fetch(`${BASE}/api/books`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
```

- [ ] **Step 4: Verify frontend starts**

```bash
cd frontend && npm run dev
```

Expected: Vite starts on `http://localhost:5173`. Browser shows "Loading...".

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.css frontend/src/api.js
git commit -m "feat: frontend scaffold with bankroll context and base styles"
```

---

## Task 16: useWebSocket Hook

**Files:**
- Create: `frontend/src/hooks/useWebSocket.js`

- [ ] **Step 1: Create `frontend/src/hooks/useWebSocket.js`**

```js
import { useEffect, useRef, useCallback } from 'react'

const WS_URL = 'ws://localhost:8000/ws'

export function useWebSocket(onMessage) {
  const wsRef = useRef(null)
  const retryDelay = useRef(1000)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        onMessageRef.current(msg)
      } catch (err) {
        console.error('WS parse error', err)
      }
    }

    ws.onopen = () => {
      retryDelay.current = 1000  // reset backoff
    }

    ws.onclose = () => {
      const delay = retryDelay.current
      retryDelay.current = Math.min(delay * 2, 30000)
      setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()  // triggers onclose → reconnect
  }, [])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
    }
  }, [connect])
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useWebSocket.js
git commit -m "feat: useWebSocket hook with exponential backoff reconnect"
```

---

## Task 17: useOpportunities Hook

**Files:**
- Create: `frontend/src/hooks/useOpportunities.js`

- [ ] **Step 1: Create `frontend/src/hooks/useOpportunities.js`**

```js
import { useState, useCallback, useRef } from 'react'
import { fetchOpportunities } from '../api'

export function useOpportunities() {
  // Map of id → opportunity, plus a Set of "new" ids for flash animation
  const [opps, setOpps] = useState({})
  const [newIds, setNewIds] = useState(new Set())
  const newIdTimers = useRef({})

  const loadInitial = useCallback(async () => {
    try {
      const data = await fetchOpportunities()
      const map = {}
      for (const o of data.opportunities) map[o.id] = o
      setOpps(map)
    } catch (e) {
      console.error('Failed to load opportunities', e)
    }
  }, [])

  const handleMessage = useCallback((msg) => {
    if (msg.type === 'new_opportunity') {
      setOpps(prev => ({ ...prev, [msg.data.id]: msg.data }))
      setNewIds(prev => new Set([...prev, msg.data.id]))
      // Remove from newIds after 10s
      if (newIdTimers.current[msg.data.id]) clearTimeout(newIdTimers.current[msg.data.id])
      newIdTimers.current[msg.data.id] = setTimeout(() => {
        setNewIds(prev => { const s = new Set(prev); s.delete(msg.data.id); return s })
      }, 10000)
    } else if (msg.type === 'opportunity_updated') {
      setOpps(prev => ({ ...prev, [msg.data.id]: msg.data }))
    } else if (msg.type === 'opportunity_expired') {
      setOpps(prev => {
        const next = { ...prev }
        delete next[msg.id]
        return next
      })
    }
  }, [])

  return { opps, newIds, loadInitial, handleMessage }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useOpportunities.js
git commit -m "feat: useOpportunities hook with WS event handling"
```

---

## Task 18: BookStatusBar Component

**Files:**
- Create: `frontend/src/components/BookStatusBar.jsx`

- [ ] **Step 1: Create `frontend/src/components/BookStatusBar.jsx`**

```jsx
import { useState, useEffect, useCallback } from 'react'
import { fetchBooks } from '../api'
import { useWebSocket } from '../hooks/useWebSocket'

export default function BookStatusBar() {
  const [books, setBooks] = useState({})  // { bookName: { status, last_scraped_at, record_count, last_error } }

  useEffect(() => {
    fetchBooks()
      .then(data => {
        const map = {}
        for (const b of data.books) map[b.name] = b
        setBooks(map)
      })
      .catch(console.error)
  }, [])

  const handleMessage = useCallback((msg) => {
    if (msg.type === 'odds_updated') {
      setBooks(prev => ({
        ...prev,
        [msg.book]: {
          name: msg.book,
          status: msg.status,
          last_scraped_at: msg.scraped_at,
          record_count: msg.record_count,
          last_error: null,
        }
      }))
    }
  }, [])

  useWebSocket(handleMessage)

  function timeSince(iso) {
    if (!iso) return '?'
    const secs = Math.round((Date.now() - new Date(iso)) / 1000)
    return secs < 60 ? `${secs}s` : `${Math.round(secs / 60)}m`
  }

  return (
    <div className="book-status-bar">
      {Object.values(books).map(b => (
        <span key={b.name} className={`book-badge ${b.status}`} title={b.last_error || ''}>
          {b.name} {b.status === 'ok' ? `✓ ${timeSince(b.last_scraped_at)}` : '✗'}
        </span>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/BookStatusBar.jsx
git commit -m "feat: BookStatusBar with live WS updates"
```

---

## Task 19: StakeCalculator Component

**Files:**
- Create: `frontend/src/components/StakeCalculator.jsx`

- [ ] **Step 1: Create `frontend/src/components/StakeCalculator.jsx`**

```jsx
import { useContext } from 'react'
import { BankrollContext } from '../App'

function calculateStakes(bankroll, legs) {
  const implied = legs.map(l => 1 / l.decimal_odds)
  const arbSum = implied.reduce((a, b) => a + b, 0)
  return implied.map(imp => (bankroll * imp / arbSum).toFixed(2))
}

export default function StakeCalculator({ opportunity }) {
  const bankroll = useContext(BankrollContext)
  const stakes = calculateStakes(bankroll, opportunity.outcomes)
  const profit = (bankroll * opportunity.margin).toFixed(2)

  return (
    <div className="stake-calc">
      {opportunity.outcomes.map((leg, i) => (
        <div key={leg.outcome} className="stake-row">
          <strong>{leg.outcome}</strong>: {leg.book} @ {leg.decimal_odds} → <strong>${stakes[i]}</strong>
        </div>
      ))}
      <div className="stake-profit">Guaranteed profit: ${profit} ({(opportunity.margin * 100).toFixed(2)}%)</div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/StakeCalculator.jsx
git commit -m "feat: StakeCalculator with live bankroll context"
```

---

## Task 20: AlertSound Component

**Files:**
- Create: `frontend/src/components/AlertSound.jsx`

- [ ] **Step 1: Create `frontend/src/components/AlertSound.jsx`**

```jsx
import { useState, useCallback, useImperativeHandle, forwardRef } from 'react'

const AlertSound = forwardRef(function AlertSound(_, ref) {
  const [enabled, setEnabled] = useState(true)

  const playChime = useCallback(() => {
    if (!enabled) return
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.type = 'triangle'
      osc.frequency.setValueAtTime(880, ctx.currentTime)
      gain.gain.setValueAtTime(0.3, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.1)
      osc.start(ctx.currentTime)
      osc.stop(ctx.currentTime + 0.1)
    } catch (e) {
      console.warn('Audio failed', e)
    }
  }, [enabled])

  useImperativeHandle(ref, () => ({ playChime }))

  return (
    <button
      className="sound-toggle"
      onClick={() => setEnabled(e => !e)}
      title={enabled ? 'Mute alerts' : 'Unmute alerts'}
    >
      {enabled ? '🔔' : '🔕'}
    </button>
  )
})

export default AlertSound
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/AlertSound.jsx
git commit -m "feat: AlertSound with Web Audio API chime and toggle"
```

---

## Task 21: OpportunitiesTable Component

**Files:**
- Create: `frontend/src/components/OpportunitiesTable.jsx`

- [ ] **Step 1: Create `frontend/src/components/OpportunitiesTable.jsx`**

```jsx
import { useState } from 'react'
import StakeCalculator from './StakeCalculator'

const SPORT_EMOJI = { nhl: '🏒', nfl: '🏈', nba: '🏀', mlb: '⚾', mls: '⚽', soccer: '⚽' }

export default function OpportunitiesTable({ opps, newIds }) {
  const [expanded, setExpanded] = useState(new Set())

  const sorted = Object.values(opps).sort((a, b) => {
    // Pin new items first for 10s (tracked by newIds), then sort by margin
    const aNew = newIds.has(a.id) ? 1 : 0
    const bNew = newIds.has(b.id) ? 1 : 0
    if (bNew !== aNew) return bNew - aNew
    return b.margin - a.margin
  })

  function toggleExpand(id) {
    setExpanded(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })
  }

  if (sorted.length === 0) {
    return <p style={{ padding: '40px 20px', color: '#64748b' }}>No arbitrage opportunities detected.</p>
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Sport</th>
          <th>Event</th>
          <th>Market</th>
          <th>Profit</th>
          <th>Books</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map(opp => {
          const isExp = expanded.has(opp.id)
          const isNew = newIds.has(opp.id)
          const books = [...new Set(opp.outcomes.map(o => o.book))].join(', ')
          return (
            <>
              <tr
                key={opp.id}
                className={`expandable ${isNew ? 'new-flash' : ''}`}
                onClick={() => toggleExpand(opp.id)}
              >
                <td>{SPORT_EMOJI[opp.sport] || '🎯'} {opp.sport.toUpperCase()}</td>
                <td>{opp.event_name}</td>
                <td>{opp.market}</td>
                <td><span className="profit-badge">+{(opp.margin * 100).toFixed(2)}%</span></td>
                <td>{books} {isExp ? '▲' : '▼'}</td>
              </tr>
              {isExp && (
                <tr key={`${opp.id}-detail`} className="expanded-row">
                  <td colSpan={5}>
                    <StakeCalculator opportunity={opp} />
                  </td>
                </tr>
              )}
            </>
          )
        })}
      </tbody>
    </table>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/OpportunitiesTable.jsx
git commit -m "feat: OpportunitiesTable with expandable rows and flash animation"
```

---

## Task 22: Assemble App.jsx

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Replace `frontend/src/App.jsx` with full assembled app**

```jsx
import { useState, createContext, useEffect, useRef } from 'react'
import './App.css'
import BookStatusBar from './components/BookStatusBar'
import OpportunitiesTable from './components/OpportunitiesTable'
import AlertSound from './components/AlertSound'
import { useWebSocket } from './hooks/useWebSocket'
import { useOpportunities } from './hooks/useOpportunities'

export const BankrollContext = createContext(100)

export default function App() {
  const [bankroll, setBankroll] = useState(100)
  const soundRef = useRef(null)

  const { opps, newIds, loadInitial, handleMessage } = useOpportunities()

  // Wrap handleMessage to also trigger sound on new opportunity
  const handleMessageWithSound = (msg) => {
    if (msg.type === 'new_opportunity') {
      soundRef.current?.playChime()
    }
    handleMessage(msg)
  }

  useWebSocket(handleMessageWithSound)

  useEffect(() => { loadInitial() }, [loadInitial])

  return (
    <BankrollContext.Provider value={bankroll}>
      <div className="app">
        <header className="app-header">
          <h1>ARB FINDER — Alberta</h1>
          <label className="bankroll-label">
            Bankroll: $
            <input
              type="number"
              value={bankroll}
              min={1}
              onChange={e => setBankroll(Number(e.target.value))}
              className="bankroll-input"
            />
          </label>
          <AlertSound ref={soundRef} />
        </header>
        <BookStatusBar />
        <OpportunitiesTable opps={opps} newIds={newIds} />
      </div>
    </BankrollContext.Provider>
  )
}
```

- [ ] **Step 2: Verify frontend builds without errors**

```bash
cd frontend && npm run build
```

Expected: `dist/` created, no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat: assemble full app with all components wired together"
```

---

## Task 23: End-to-End Integration Verification

- [ ] **Step 1: Start backend**

```bash
cd backend && source .venv/bin/activate && uvicorn main:app --port 8000
```

Expected: `Application startup complete.`

- [ ] **Step 2: Start frontend in separate terminal**

```bash
cd frontend && npm run dev
```

Expected: Vite dev server running on `http://localhost:5173`.

- [ ] **Step 3: Verify REST endpoints**

```bash
curl http://localhost:8000/api/opportunities
curl http://localhost:8000/api/books
```

Expected: valid JSON responses.

- [ ] **Step 4: Verify WebSocket**

Open `http://localhost:5173` in browser. Open browser DevTools → Network → WS. Confirm WebSocket connection to `ws://localhost:8000/ws` is established.

- [ ] **Step 5: Verify scrape cycle fires**

Watch backend logs. After 45s, confirm a scrape cycle log appears:
```
INFO: Scrape cycle starting
INFO: Cycle complete in X.Xs — N opps, M ok, K error
```

- [ ] **Step 6: Verify book status badges update in UI**

After a cycle completes, the BookStatusBar badges should update with "✓ Xs" timestamps.

- [ ] **Step 7: Final commit**

```bash
git add .
git commit -m "chore: integration verified — all components connected"
```

---

## Notes for Implementer

**Scraper implementation is iterative.** Tasks 9–14 involve live site inspection with the Playwright inspector. This is expected exploratory work. Each site has unique DOM structure; use the non-headless inspection script provided in Task 9 to discover selectors before writing extraction logic.

**Bet365 may block Playwright entirely** due to Cloudflare. If so: document the block in `backend/scrapers/bet365.py` as a comment, leave the scraper returning `[]`, and move on. The system degrades gracefully — a blocked scraper just contributes no records.

**Sport detection** (mapping event names to a sport string like "nhl", "mls") is site-specific. Each scraper should detect sport from the page section/category it's scraping (e.g., if scraping the NHL section URL, hardcode `sport="nhl"` for those records). Add a `detect_sport(url_section: str) -> str` helper to `normalizer.py` if needed.

**teams.json coverage** is intentionally sparse at launch. Add entries whenever the normalizer logs unrecognized team tokens. The log line in `normalize_event_name` will indicate what's missing.
