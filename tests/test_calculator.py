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
    # arb_sum = 0.9950 → margin = 0.00498 < 0.005 threshold
    records = [
        make_record("betmgm", "home", 2.01),
        make_record("fanduel", "away", 2.01),
    ]
    opps = detect_arbs(records, min_margin=0.005)
    assert opps == []
