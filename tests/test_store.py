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
