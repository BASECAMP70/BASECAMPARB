# PMXT Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five PMXT-backed prediction market scrapers (Kalshi, Limitless, Probable, Myriad, Opinion) that run alongside the existing Polymarket scraper and feed OddsRecord data into the arb engine.

**Architecture:** A shared `PmxtScraper` base class handles async bridging, sport querying, and OddsRecord mapping. Five thin subclasses each set a `BOOK_NAME` and implement `_make_exchange()`. Scrapers are registered in `scheduler.py` outside the Playwright block so they run even when a browser is unavailable.

**Tech Stack:** Python 3.9, PMXT Python SDK (`pmxt`), Node.js sidecar (`pmxtjs`), pytest, existing `normalizer.py` utilities.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/scrapers/pmxt_base.py` | Create | Abstract base: async bridging, sport loop, OddsRecord mapping |
| `backend/scrapers/kalshi.py` | Create | KalshiScraper — reads KALSHI_API_KEY / KALSHI_PRIVATE_KEY from env |
| `backend/scrapers/limitless.py` | Create | LimitlessScraper — no auth |
| `backend/scrapers/probable.py` | Create | ProbableScraper — no auth |
| `backend/scrapers/myriad.py` | Create | MyriadScraper — no auth |
| `backend/scrapers/opinion.py` | Create | OpinionScraper — no auth |
| `backend/scheduler.py` | Modify | Move PolymarketScraper + add 5 PMXT scrapers outside Playwright block |
| `backend/requirements.txt` | Modify | Add `pmxt` |
| `tests/test_pmxt_base.py` | Create | Unit tests for `_map_market` mapping logic |

---

## Task 1: Install PMXT

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Install the Python SDK into the project venv**

Run from the repo root:
```bash
cd backend && .venv/Scripts/python.exe -m pip install pmxt
```
Expected: `Successfully installed pmxt-...`

- [ ] **Step 2: Install Node.js (if not already installed)**

Download and install from https://nodejs.org (LTS version). Verify:
```bash
node --version   # should print v18.x or higher
npm --version
```
If these commands fail, Node.js is not on PATH — restart your terminal or add `C:\Program Files\nodejs` to PATH.

- [ ] **Step 3: Install the Node.js sidecar globally**

```bash
npm install -g pmxtjs
```
Expected: `added N packages` with no errors.

- [ ] **Step 3: Add pmxt to requirements.txt**

In `backend/requirements.txt`, add at the end:
```
pmxt
```

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat: add pmxt dependency"
```

---

## Task 2: Write failing tests for `_map_market`

**Files:**
- Create: `tests/test_pmxt_base.py`

The `_map_market(self, market, sport_key, now)` method is the core mapping logic. We test it in isolation using mock PMXT objects — no sidecar needed.

- [ ] **Step 1: Create `tests/test_pmxt_base.py`**

```python
"""Unit tests for PmxtScraper._map_market mapping logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
import pytest


# ---------------------------------------------------------------------------
# Mock PMXT objects (mirror PMXT SDK data model)
# ---------------------------------------------------------------------------

@dataclass
class MockOutcome:
    label: str
    price: float

@dataclass
class MockMarket:
    outcomes: List[MockOutcome]
    end_date: Optional[str] = "2026-04-10T02:00:00+00:00"
    url: Optional[str] = "https://kalshi.com/market/test"


# ---------------------------------------------------------------------------
# Concrete stub so we can instantiate the abstract base
# ---------------------------------------------------------------------------

def make_scraper():
    """Import and instantiate a concrete PmxtScraper subclass for testing."""
    from scrapers.pmxt_base import PmxtScraper

    class _Stub(PmxtScraper):
        BOOK_NAME = "test_exchange"
        def _make_exchange(self):
            return None  # not called in _map_market tests

    return _Stub(browser=None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

NOW = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)


def test_map_market_returns_two_records():
    scraper = make_scraper()
    market = MockMarket(outcomes=[
        MockOutcome("Boston Celtics", 0.55),
        MockOutcome("Los Angeles Lakers", 0.45),
    ])
    records = scraper._map_market(market, "nba", NOW)
    assert len(records) == 2


def test_map_market_book_name():
    scraper = make_scraper()
    market = MockMarket(outcomes=[
        MockOutcome("Boston Celtics", 0.55),
        MockOutcome("Los Angeles Lakers", 0.45),
    ])
    records = scraper._map_market(market, "nba", NOW)
    assert all(r.book == "test_exchange" for r in records)


def test_map_market_sport_key():
    scraper = make_scraper()
    market = MockMarket(outcomes=[
        MockOutcome("Boston Celtics", 0.55),
        MockOutcome("Los Angeles Lakers", 0.45),
    ])
    records = scraper._map_market(market, "nba", NOW)
    assert all(r.sport == "nba" for r in records)


def test_map_market_decimal_odds_conversion():
    scraper = make_scraper()
    market = MockMarket(outcomes=[
        MockOutcome("Boston Celtics", 0.5),
        MockOutcome("Los Angeles Lakers", 0.5),
    ])
    records = scraper._map_market(market, "nba", NOW)
    assert all(r.decimal_odds == round(1.0 / 0.5, 4) for r in records)


def test_map_market_home_away_alphabetical():
    """'home' must be assigned to the alphabetically-first canonical team name,
    matching how normalize_event_name orders teams."""
    scraper = make_scraper()
    # "Boston Celtics" < "Los Angeles Lakers" alphabetically
    market = MockMarket(outcomes=[
        MockOutcome("Los Angeles Lakers", 0.55),  # listed first but alphabetically second
        MockOutcome("Boston Celtics", 0.45),
    ])
    records = scraper._map_market(market, "nba", NOW)
    home_record = next(r for r in records if r.outcome == "home")
    away_record = next(r for r in records if r.outcome == "away")
    assert "Celtics" in home_record.participant or home_record.participant < away_record.participant


def test_map_market_event_name_canonical():
    """event_name must be consistent regardless of outcome order."""
    scraper = make_scraper()
    market_a = MockMarket(outcomes=[
        MockOutcome("Boston Celtics", 0.55),
        MockOutcome("Los Angeles Lakers", 0.45),
    ])
    market_b = MockMarket(outcomes=[
        MockOutcome("Los Angeles Lakers", 0.55),
        MockOutcome("Boston Celtics", 0.45),
    ])
    records_a = scraper._map_market(market_a, "nba", NOW)
    records_b = scraper._map_market(market_b, "nba", NOW)
    assert records_a[0].event_name == records_b[0].event_name


def test_map_market_skips_low_price():
    scraper = make_scraper()
    market = MockMarket(outcomes=[
        MockOutcome("Boston Celtics", 0.005),   # too low
        MockOutcome("Los Angeles Lakers", 0.995),  # too high
    ])
    records = scraper._map_market(market, "nba", NOW)
    assert records == []


def test_map_market_skips_non_binary():
    """Markets with outcome count != 2 are skipped entirely."""
    scraper = make_scraper()
    market = MockMarket(outcomes=[
        MockOutcome("Team A", 0.4),
        MockOutcome("Team B", 0.3),
        MockOutcome("Team C", 0.3),
    ])
    records = scraper._map_market(market, "nba", NOW)
    assert records == []


def test_map_market_event_url():
    scraper = make_scraper()
    market = MockMarket(
        outcomes=[MockOutcome("Boston Celtics", 0.55), MockOutcome("Los Angeles Lakers", 0.45)],
        url="https://kalshi.com/market/nba-celtics-lakers",
    )
    records = scraper._map_market(market, "nba", NOW)
    assert all(r.event_url == "https://kalshi.com/market/nba-celtics-lakers" for r in records)


def test_map_market_event_start_from_end_date():
    scraper = make_scraper()
    market = MockMarket(
        outcomes=[MockOutcome("Boston Celtics", 0.55), MockOutcome("Los Angeles Lakers", 0.45)],
        end_date="2026-04-15T02:00:00+00:00",
    )
    records = scraper._map_market(market, "nba", NOW)
    assert records[0].event_start == datetime(2026, 4, 15, 2, 0, 0, tzinfo=timezone.utc)


def test_map_market_event_start_fallback():
    """When end_date is absent, event_start falls back to scraped_at (NOW)."""
    scraper = make_scraper()
    market = MockMarket(
        outcomes=[MockOutcome("Boston Celtics", 0.55), MockOutcome("Los Angeles Lakers", 0.45)],
        end_date=None,
    )
    records = scraper._map_market(market, "nba", NOW)
    assert records[0].event_start == NOW


def test_map_market_market_type_is_moneyline():
    scraper = make_scraper()
    market = MockMarket(outcomes=[
        MockOutcome("Boston Celtics", 0.55),
        MockOutcome("Los Angeles Lakers", 0.45),
    ])
    records = scraper._map_market(market, "nba", NOW)
    assert all(r.market == "moneyline" for r in records)
```

- [ ] **Step 2: Run tests to confirm they fail** (module doesn't exist yet)

```bash
cd backend && .venv/Scripts/python.exe -m pytest ../tests/test_pmxt_base.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError: No module named 'scrapers.pmxt_base'`

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_pmxt_base.py
git commit -m "test: add failing tests for PmxtScraper._map_market"
```

---

## Task 3: Implement `scrapers/pmxt_base.py`

**Files:**
- Create: `backend/scrapers/pmxt_base.py`

- [ ] **Step 1: Create `backend/scrapers/pmxt_base.py`**

```python
"""
Shared base class for PMXT prediction market scrapers.

PMXT SDK is synchronous — all exchange calls run in a thread executor
to avoid blocking the asyncio event loop.

Subclasses must set BOOK_NAME and implement _make_exchange().
"""
import asyncio
import logging
from abc import abstractmethod
from datetime import datetime, timezone
from typing import List

from normalizer import normalize_event_name, normalize_participant
from scrapers.base import OddsRecord, OddsScraper

logger = logging.getLogger(__name__)

_SPORTS = ["nba", "nhl", "mlb"]


class PmxtScraper(OddsScraper):
    """Abstract base for PMXT-backed scrapers."""

    @abstractmethod
    def _make_exchange(self):
        """Return a configured PMXT exchange instance."""

    async def fetch_odds(self) -> List[OddsRecord]:
        now = datetime.now(timezone.utc)
        try:
            exchange = self._make_exchange()
        except Exception as exc:
            logger.warning("[%s] Exchange init failed: %s", self.BOOK_NAME, exc)
            return []

        records: List[OddsRecord] = []
        loop = asyncio.get_event_loop()

        for sport in _SPORTS:
            try:
                markets = await loop.run_in_executor(
                    None,
                    lambda s=sport: exchange.fetch_markets(query=s),
                )
                for market in markets:
                    records.extend(self._map_market(market, sport, now))
            except Exception as exc:
                logger.warning("[%s] %s fetch error: %s", self.BOOK_NAME, sport, exc)

        logger.info("[%s] fetched %d records", self.BOOK_NAME, len(records))
        return records

    def _map_market(self, market, sport_key: str, now: datetime) -> List[OddsRecord]:
        """Convert a single PMXT market object to a list of OddsRecord."""
        outcomes = getattr(market, "outcomes", [])
        if len(outcomes) != 2:
            return []

        outcome_a, outcome_b = outcomes

        # Resolve canonical team names for consistent home/away assignment
        name_a = normalize_participant(outcome_a.label)
        name_b = normalize_participant(outcome_b.label)

        # Alphabetical sort — must match normalize_event_name's sort order
        if name_a <= name_b:
            home_label, away_label = outcome_a.label, outcome_b.label
            home_price, away_price = outcome_a.price, outcome_b.price
            home_name, away_name = name_a, name_b
        else:
            home_label, away_label = outcome_b.label, outcome_a.label
            home_price, away_price = outcome_b.price, outcome_a.price
            home_name, away_name = name_b, name_a

        event_name = normalize_event_name(f"{home_label} vs {away_label}")

        # Parse event_start from market.end_date
        end_date = getattr(market, "end_date", None)
        try:
            event_start = (
                datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                if end_date
                else now
            )
        except Exception:
            event_start = now

        event_url = getattr(market, "url", None) or f"https://{self.BOOK_NAME}.com"

        records = []
        for participant, outcome_str, price in [
            (home_name, "home", home_price),
            (away_name, "away", away_price),
        ]:
            if price <= 0.01 or price >= 0.99:
                continue
            decimal_odds = round(1.0 / price, 4)
            if decimal_odds <= 1.0:
                continue
            records.append(OddsRecord(
                book=self.BOOK_NAME,
                sport=sport_key,
                event_name=event_name,
                event_start=event_start,
                market="moneyline",
                outcome=outcome_str,
                decimal_odds=decimal_odds,
                scraped_at=now,
                participant=participant,
                event_url=event_url,
            ))

        return records
```

- [ ] **Step 2: Run the tests — all should pass**

```bash
cd backend && .venv/Scripts/python.exe -m pytest ../tests/test_pmxt_base.py -v
```
Expected: all 11 tests PASS.

If `test_map_market_home_away_alphabetical` fails, the issue is in the alphabetical comparison logic — ensure `normalize_participant` is resolving "Boston Celtics" to a canonical name that sorts before "Los Angeles Lakers".

- [ ] **Step 3: Commit**

```bash
git add backend/scrapers/pmxt_base.py
git commit -m "feat: add PmxtScraper base class with OddsRecord mapping"
```

---

## Task 4: Implement the five thin subclasses

**Files:**
- Create: `backend/scrapers/kalshi.py`
- Create: `backend/scrapers/limitless.py`
- Create: `backend/scrapers/probable.py`
- Create: `backend/scrapers/myriad.py`
- Create: `backend/scrapers/opinion.py`

- [ ] **Step 1: Create `backend/scrapers/kalshi.py`**

```python
"""Kalshi prediction market scraper via PMXT SDK."""
import logging
import os

from scrapers.pmxt_base import PmxtScraper

logger = logging.getLogger(__name__)


class KalshiScraper(PmxtScraper):
    BOOK_NAME = "kalshi"

    def _make_exchange(self):
        import pmxt
        api_key = os.getenv("KALSHI_API_KEY")
        private_key = os.getenv("KALSHI_PRIVATE_KEY")
        if not api_key or not private_key:
            raise RuntimeError(
                "KALSHI_API_KEY and KALSHI_PRIVATE_KEY env vars are required"
            )
        return pmxt.Kalshi(api_key=api_key, private_key=private_key)
```

- [ ] **Step 2: Create `backend/scrapers/limitless.py`**

```python
"""Limitless prediction market scraper via PMXT SDK."""
from scrapers.pmxt_base import PmxtScraper


class LimitlessScraper(PmxtScraper):
    BOOK_NAME = "limitless"

    def _make_exchange(self):
        import pmxt
        return pmxt.Limitless()
```

- [ ] **Step 3: Create `backend/scrapers/probable.py`**

```python
"""Probable prediction market scraper via PMXT SDK."""
from scrapers.pmxt_base import PmxtScraper


class ProbableScraper(PmxtScraper):
    BOOK_NAME = "probable"

    def _make_exchange(self):
        import pmxt
        return pmxt.Probable()
```

- [ ] **Step 4: Create `backend/scrapers/myriad.py`**

```python
"""Myriad prediction market scraper via PMXT SDK."""
from scrapers.pmxt_base import PmxtScraper


class MyriadScraper(PmxtScraper):
    BOOK_NAME = "myriad"

    def _make_exchange(self):
        import pmxt
        return pmxt.Myriad()
```

- [ ] **Step 5: Create `backend/scrapers/opinion.py`**

```python
"""Opinion prediction market scraper via PMXT SDK."""
from scrapers.pmxt_base import PmxtScraper


class OpinionScraper(PmxtScraper):
    BOOK_NAME = "opinion"

    def _make_exchange(self):
        import pmxt
        return pmxt.Opinion()
```

- [ ] **Step 6: Run full test suite to confirm nothing is broken**

```bash
cd backend && .venv/Scripts/python.exe -m pytest ../tests/ -v
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/scrapers/kalshi.py backend/scrapers/limitless.py backend/scrapers/probable.py backend/scrapers/myriad.py backend/scrapers/opinion.py
git commit -m "feat: add Kalshi, Limitless, Probable, Myriad, Opinion scrapers via PMXT"
```

---

## Task 5: Register scrapers in `scheduler.py`

**Files:**
- Modify: `backend/scheduler.py`

Currently `PolymarketScraper` is instantiated inside the Playwright `try` block (lines 46–54), meaning it's disabled if the browser fails to launch. PMXT scrapers also don't need a browser. Fix this by moving all browser-free scrapers outside the Playwright block.

- [ ] **Step 1: Update imports at the top of `scheduler.py`**

Add after the existing scraper imports:
```python
from scrapers.kalshi import KalshiScraper
from scrapers.limitless import LimitlessScraper
from scrapers.probable import ProbableScraper
from scrapers.myriad import MyriadScraper
from scrapers.opinion import OpinionScraper
```

- [ ] **Step 2: Move PolymarketScraper and add PMXT scrapers outside the Playwright block**

Find this section in `start_scheduler()`:

```python
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
            PolymarketScraper,
            # Bet99Scraper,  # suppressed
        ]
        _scrapers = [cls(_browser) for cls in scraper_classes]
        logger.info("Playwright browser launched — %d scrapers ready", len(_scrapers))
    except Exception as exc:
        logger.warning("Playwright/Chromium unavailable (%s: %s) — scrapers disabled, API still running",
                       type(exc).__name__, exc)
        _scrapers = []
```

Replace with:

```python
    # Browser-free scrapers — always active regardless of Playwright availability
    _browser_free_scrapers = [
        PolymarketScraper(None),
        KalshiScraper(None),
        LimitlessScraper(None),
        ProbableScraper(None),
        MyriadScraper(None),
        OpinionScraper(None),
    ]

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
        browser_scrapers = [
            PlayAlbertaScraper(_browser),
            Bet365Scraper(_browser),
            SportsInteractionScraper(_browser),
            BetwayScraper(_browser),
            # Bet99Scraper(_browser),  # suppressed
        ]
        _scrapers = browser_scrapers + _browser_free_scrapers
        logger.info("Playwright browser launched — %d scrapers ready", len(_scrapers))
    except Exception as exc:
        logger.warning("Playwright/Chromium unavailable (%s: %s) — browser scrapers disabled",
                       type(exc).__name__, exc)
        _scrapers = _browser_free_scrapers
```

- [ ] **Step 3: Remove the now-unused `PolymarketScraper` import line that was inside the try block**

Verify the import at the top of `scheduler.py` already has:
```python
from scrapers.polymarket import PolymarketScraper
```
It does (line 16) — no change needed.

- [ ] **Step 4: Run the full test suite one more time**

```bash
cd backend && .venv/Scripts/python.exe -m pytest ../tests/ -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/scheduler.py
git commit -m "feat: register PMXT scrapers outside Playwright block; fix PolymarketScraper always-on"
```

---

## Task 6: Smoke test with live PMXT (optional but recommended)

This task verifies the Node.js sidecar is wired up correctly and at least one exchange returns data. It does not require Kalshi credentials.

- [ ] **Step 1: Run a quick smoke test from the Python REPL**

```bash
cd backend && .venv/Scripts/python.exe -c "
import asyncio
from scrapers.limitless import LimitlessScraper

async def main():
    s = LimitlessScraper(None)
    records = await s.fetch_odds()
    print(f'Limitless returned {len(records)} records')
    if records:
        r = records[0]
        print(f'  Sample: {r.event_name} | {r.outcome} | {r.decimal_odds}')

asyncio.run(main())
"
```
Expected: prints record count (may be 0 if no active markets, but should not throw).

If you see `ModuleNotFoundError: No module named 'pmxt'` — run `pip install pmxt` in the venv again.
If you see a Node.js error — confirm `pmxtjs` is globally installed: `npm list -g pmxtjs`.

- [ ] **Step 2: Final commit if any fixes were needed, otherwise done**

```bash
git add -A
git commit -m "feat: PMXT integration complete"
```
