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
