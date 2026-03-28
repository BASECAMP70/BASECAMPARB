"""
Polymarket scraper — prediction market odds via Gamma REST API.

No browser needed — pure aiohttp API calls (same pattern as Betway).

Endpoint: https://gamma-api.polymarket.com/events
  ?active=true&closed=false&tag_slug={sport}&limit=100

Supported sports: nba, nhl, mlb

Prices are in the range 0–1 (implied probability).
Decimal odds = 1 / price.

Question formats parsed:
  "Will the Boston Celtics beat the Los Angeles Lakers?"
  "Boston Celtics vs Los Angeles Lakers - Winner"
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import aiohttp

from normalizer import normalize_event_name
from scrapers.base import OddsRecord, OddsScraper

logger = logging.getLogger(__name__)

_GAMMA_API = "https://gamma-api.polymarket.com"

# (sport_key, tag_slug) — tag slugs confirmed from Polymarket Gamma API
_SPORT_TAGS: List[Tuple[str, str]] = [
    ("nba", "nba"),
    ("nhl", "nhl"),
    ("mlb", "mlb"),
]

# "Will the Boston Celtics beat the Los Angeles Lakers on March 28?"
_WILL_RE = re.compile(
    r"Will\s+(?:the\s+)?(.+?)\s+beat\s+(?:the\s+)?(.+?)(?:\s+on\s|\s*\?|$)",
    re.IGNORECASE,
)
# "Boston Celtics vs Los Angeles Lakers - Winner" or "Celtics vs Lakers"
_VS_RE = re.compile(
    r"^(.+?)\s+vs\.?\s+(.+?)(?:\s*[-–—(]|\s*\?|$)",
    re.IGNORECASE,
)


def _parse_teams(question: str) -> Optional[Tuple[str, str]]:
    """Return (team_a, team_b) from market question, or None."""
    m = _WILL_RE.search(question)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = _VS_RE.search(question)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None


def _decode_json_field(val):
    """outcomePrices / outcomes may arrive as a JSON-encoded string."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return val if isinstance(val, list) else []


class PolymarketScraper(OddsScraper):
    BOOK_NAME = "polymarket"
    ODDS_URL  = "https://polymarket.com/sports"

    async def fetch_odds(self) -> List[OddsRecord]:
        now = datetime.now(timezone.utc)
        try:
            records = await self._fetch_all_sports(now)
            logger.info("[polymarket] Gamma API returned %d records", len(records))
            return records
        except Exception as exc:
            logger.warning("[polymarket] fetch failed: %s", exc)
            return []

    async def _fetch_all_sports(self, now: datetime) -> List[OddsRecord]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }
        async with aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as session:
            tasks = [
                self._fetch_sport(session, tag_slug, sport_key, now)
                for sport_key, tag_slug in _SPORT_TAGS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        records: List[OddsRecord] = []
        for (sport_key, tag_slug), result in zip(_SPORT_TAGS, results):
            if isinstance(result, Exception):
                logger.warning("[polymarket] %s fetch error: %s", sport_key, result)
            else:
                records.extend(result)
        return records

    async def _fetch_sport(
        self,
        session: aiohttp.ClientSession,
        tag_slug: str,
        sport_key: str,
        now: datetime,
    ) -> List[OddsRecord]:
        url = f"{_GAMMA_API}/events"
        params = {
            "active":    "true",
            "closed":    "false",
            "tag_slug":  tag_slug,
            "limit":     "100",
            "order":     "volume24hr",
            "ascending": "false",
        }
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Gamma API HTTP {resp.status} for tag_slug={tag_slug}")
            payload = await resp.json(content_type=None)

        # Gamma API may return list directly or wrapped in {"data": [...]}
        if isinstance(payload, list):
            events = payload
        else:
            events = payload.get("data", payload.get("events", []))

        records: List[OddsRecord] = []
        for event in events:
            records.extend(self._parse_event(event, sport_key, now))
        return records

    def _parse_event(
        self, event: dict, sport_key: str, now: datetime
    ) -> List[OddsRecord]:
        markets = event.get("markets", [])
        if not markets:
            return []

        records = []
        for market in markets:
            if not market.get("active", True):
                continue
            if market.get("closed", False):
                continue

            question           = market.get("question", "")
            outcome_prices_raw = _decode_json_field(market.get("outcomePrices", []))
            outcomes_raw       = _decode_json_field(market.get("outcomes", []))

            if len(outcome_prices_raw) < 2 or len(outcomes_raw) < 2:
                continue

            teams = _parse_teams(question)
            if not teams:
                logger.debug("[polymarket] Skipping unparseable question: %r", question)
                continue

            team_a, team_b = teams
            event_name = normalize_event_name(f"{team_a} vs {team_b}")

            # Use market endDate as event_start (when market resolves)
            end_str = market.get("endDate") or event.get("endDate", "")
            try:
                event_start = datetime.fromisoformat(
                    end_str.replace("Z", "+00:00")
                ) if end_str else now
            except Exception:
                event_start = now

            slug      = market.get("slug", "")
            event_url = (
                f"https://polymarket.com/event/{slug}"
                if slug else "https://polymarket.com/sports"
            )

            # outcomePrices[0] = team_a wins (YES), outcomePrices[1] = team_b wins (NO)
            legs = [
                (team_a, "home", outcome_prices_raw[0]),
                (team_b, "away", outcome_prices_raw[1]),
            ]
            for participant, outcome, price_str in legs:
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    continue
                if price <= 0.01 or price >= 0.99:
                    continue  # skip near-certain or stale markets
                decimal_odds = round(1.0 / price, 4)
                if decimal_odds <= 1.0:
                    continue

                records.append(OddsRecord(
                    book=self.BOOK_NAME,
                    sport=sport_key,
                    event_name=event_name,
                    event_start=event_start,
                    market="moneyline",
                    outcome=outcome,
                    decimal_odds=decimal_odds,
                    scraped_at=now,
                    participant=participant,
                    event_url=event_url,
                ))

        return records
