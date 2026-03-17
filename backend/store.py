from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from scrapers.base import OddsRecord
from calculator import Opportunity


@dataclass
class BookStatus:
    name: str
    status: str                  # "ok" | "error" | "stale"
    last_scraped_at: Optional[datetime] = None
    record_count: int = 0
    last_error: Optional[str] = None


class Store:
    def __init__(self, stale_seconds: int = 180, evict_seconds: int = 600):
        self._stale_seconds = stale_seconds
        self._evict_seconds = evict_seconds
        self._odds: Dict[str, List[OddsRecord]] = {}
        self._opportunities: Dict[str, Opportunity] = {}
        self._book_status: Dict[str, BookStatus] = {}

    def update_book(self, book: str, records: Optional[List[OddsRecord]], error: Optional[str]):
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

    def get_records(self, book: str) -> List[OddsRecord]:
        return self._odds.get(book, [])

    def get_fresh_records(self) -> List[OddsRecord]:
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

    def update_opportunities(self, opportunities: Dict[str, Opportunity]):
        self._opportunities = opportunities

    def get_opportunities(self) -> Dict[str, Opportunity]:
        return self._opportunities

    def get_book_status(self) -> Dict[str, BookStatus]:
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
