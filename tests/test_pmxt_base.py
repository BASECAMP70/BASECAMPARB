"""Unit tests for PmxtScraper._map_market mapping logic."""
from dataclasses import dataclass
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
    assert home_record.participant < away_record.participant


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


def test_map_market_skips_single_invalid_price_leg():
    """When only one outcome price is out of range, that leg is dropped, not the entire market.
    The other valid leg still produces a record."""
    scraper = make_scraper()
    market = MockMarket(outcomes=[
        MockOutcome("Boston Celtics", 0.005),   # too low — should be skipped
        MockOutcome("Los Angeles Lakers", 0.45),  # valid
    ])
    records = scraper._map_market(market, "nba", NOW)
    # Only the valid leg produces a record
    assert len(records) == 1
    assert records[0].outcome == "away"  # Lakers is alphabetically second


def test_map_market_price_boundary_exactly_at_limits():
    """Prices exactly at 0.01 and 0.99 are excluded (inclusive boundary)."""
    scraper = make_scraper()
    # price == 0.01 → excluded
    market_low = MockMarket(outcomes=[
        MockOutcome("Boston Celtics", 0.01),
        MockOutcome("Los Angeles Lakers", 0.45),
    ])
    records_low = scraper._map_market(market_low, "nba", NOW)
    assert all(r.outcome != "home" for r in records_low)  # Celtics leg dropped

    # price == 0.99 → excluded
    market_high = MockMarket(outcomes=[
        MockOutcome("Boston Celtics", 0.55),
        MockOutcome("Los Angeles Lakers", 0.99),
    ])
    records_high = scraper._map_market(market_high, "nba", NOW)
    assert all(r.outcome != "away" for r in records_high)  # Lakers leg dropped


def test_map_market_scraped_at():
    scraper = make_scraper()
    market = MockMarket(outcomes=[
        MockOutcome("Boston Celtics", 0.55),
        MockOutcome("Los Angeles Lakers", 0.45),
    ])
    records = scraper._map_market(market, "nba", NOW)
    assert all(r.scraped_at == NOW for r in records)


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
