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
        loop = asyncio.get_running_loop()

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

        event_url = getattr(market, "url", None) or ""

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
                participant=participant,
                decimal_odds=decimal_odds,
                scraped_at=now,
                event_url=event_url,
            ))

        return records
