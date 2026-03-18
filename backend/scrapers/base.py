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
    participant: str = ""   # human-readable selection, e.g. "Edmonton Oilers -1.5"


class OddsScraper(ABC):
    BOOK_NAME: str = ""         # override in subclass, e.g. "betmgm"
    ODDS_URL: str = ""          # override in subclass
    ODDS_CONTAINER_SELECTOR: str = ""  # override in subclass

    def __init__(self, browser):
        self.browser = browser

    @abstractmethod
    async def fetch_odds(self) -> list[OddsRecord]:
        """Navigate to book's odds page and return all available pre-game records."""
