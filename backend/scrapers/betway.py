"""
Betway scraper — Canadian market (betway.com/g/en-ca).

API approach (no browser needed):
  Base URL: https://betway.com/g/services/api/events/v2/
  All requests are POST with JSON bodies.

  Required base payload fields (Canadian market):
    BrandId          = 3
    LanguageId       = 25
    TerritoryId      = 38
    TerritoryCode    = "CA"
    ClientTypeId     = 2
    JurisdictionId   = 2
    ClientIntegratorId = 1
    CorrelationId    = fresh UUID per request

  Workflow:
    1. POST GetGroup — returns NHL event IDs (non-outright only)
    2. POST GetEventsWithMultipleMarkets — with EventMarketSets containing
       those event IDs and MarketCNames ["money-line", "ice-hockey-puck-line"].
       Response includes three parallel arrays:
         Events[]   — event metadata (HomeTeamName, AwayTeamName, Milliseconds)
         Markets[]  — market metadata (Id, Title, MarketCName, Handicap, Outcomes,
                       OutcomeGroups.home/away.outcomes)
         Outcomes[] — individual selections (Id, OddsDecimal, BetName, HandicapDisplay,
                       Handicap, MarketId, EventId, TeamCName)

  Outcome identification:
    money-line: OutcomeGroups.home.outcomes / .away.outcomes list membership
    puck-line:  Handicap on outcome — negative = that team gives handicap (spread home/away
                determined by whether Handicap matches event-level perspective from
                OutcomeGroups)
"""

import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import List

import aiohttp

from normalizer import normalize_event_name
from scrapers.base import OddsRecord, OddsScraper, UA_LIST

logger = logging.getLogger(__name__)

_API_BASE = "https://betway.com/g/services/api"

# Canada market constants (discovered via network interception)
_BRAND_ID = 3
_LANGUAGE_ID = 25
_TERRITORY_ID = 38
_TERRITORY_CODE = "CA"
_CLIENT_TYPE_ID = 2
_JURISDICTION_ID = 2
_CLIENT_INTEGRATOR_ID = 1

_MARKET_CNAMES = ["money-line", "ice-hockey-puck-line"]


def _base_payload() -> dict:
    return {
        "BrandId": _BRAND_ID,
        "LanguageId": _LANGUAGE_ID,
        "TerritoryId": _TERRITORY_ID,
        "TerritoryCode": _TERRITORY_CODE,
        "ClientTypeId": _CLIENT_TYPE_ID,
        "JurisdictionId": _JURISDICTION_ID,
        "ClientIntegratorId": _CLIENT_INTEGRATOR_ID,
        "CorrelationId": str(uuid.uuid4()),
    }


class BetwayScraper(OddsScraper):
    BOOK_NAME = "betway"
    ODDS_URL = "https://betway.com/g/en-ca/sports/gr/ice-hockey/nhl/"

    async def fetch_odds(self) -> List[OddsRecord]:
        now = datetime.now(timezone.utc)
        try:
            records = await self._fetch_via_api(now)
            logger.info("[betway] API returned %d records", len(records))
            return records
        except Exception as exc:
            logger.warning("[betway] API fetch failed: %s", exc)
            return []

    async def _fetch_via_api(self, now: datetime) -> List[OddsRecord]:
        headers = {
            "User-Agent": random.choice(UA_LIST),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-CA,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://betway.com",
            "Referer": "https://betway.com/g/en-ca/sports/gr/ice-hockey/nhl/",
        }

        async with aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as session:
            # ── Step 1: fetch NHL event IDs ──────────────────────────────────
            event_ids = await self._get_nhl_event_ids(session)
            if not event_ids:
                logger.warning("[betway] No NHL event IDs returned")
                return []

            logger.debug("[betway] NHL event IDs: %s", event_ids)

            # ── Step 2: fetch events + markets + outcomes ─────────────────────
            return await self._get_odds(session, event_ids, now)

    async def _get_nhl_event_ids(self, session: aiohttp.ClientSession) -> List[int]:
        """POST GetGroup and return non-outright NHL event IDs."""
        payload = _base_payload()
        payload.update({
            "GroupCName": "nhl",
            "CategoryCName": "ice-hockey",
            "SubCategoryCName": "north-america",
            "PremiumOnly": False,
        })
        url = f"{_API_BASE}/events/v2/GetGroup"
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                raise RuntimeError(f"GetGroup returned HTTP {resp.status}")
            data = await resp.json(content_type=None)

        summaries = data.get("EventSummaries", [])
        return [
            s["EventId"]
            for s in summaries
            if not s.get("IsOutright", True)
        ]

    async def _get_odds(
        self,
        session: aiohttp.ClientSession,
        event_ids: List[int],
        now: datetime,
    ) -> List[OddsRecord]:
        payload = _base_payload()
        payload.update({
            "EventMarketSets": [
                {
                    "EventIds": event_ids,
                    "MarketCNames": _MARKET_CNAMES,
                }
            ],
            "ScoreboardRequest": {"IncidentRequest": {}, "ScoreboardType": 3},
        })
        url = f"{_API_BASE}/events/v2/GetEventsWithMultipleMarkets"
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                raise RuntimeError(f"GetEventsWithMultipleMarkets returned HTTP {resp.status}")
            data = await resp.json(content_type=None)

        if not data.get("Success", True):
            errors = data.get("Errors", [])
            raise RuntimeError(f"GetEventsWithMultipleMarkets errors: {errors}")

        events_raw = data.get("Events", [])
        markets_raw = data.get("Markets", [])
        outcomes_raw = data.get("Outcomes", [])

        # Index for fast lookup
        events_by_id = {e["Id"]: e for e in events_raw}
        outcomes_by_id = {o["Id"]: o for o in outcomes_raw}

        records: List[OddsRecord] = []

        for market in markets_raw:
            market_cname = market.get("MarketCName", "")
            event_id = market.get("EventId")
            ev = events_by_id.get(event_id)
            if not ev:
                continue

            # Skip suspended markets
            if market.get("IsSuspended", False):
                continue

            # Parse event start time from Milliseconds (UTC epoch ms)
            ms = ev.get("Milliseconds", 0)
            try:
                event_start = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
            except Exception:
                event_start = now

            # Build canonical event name (Betway uses "Home - Away" format)
            raw_name = ev.get("EventName", "")
            home_name = ev.get("HomeTeamName", "")
            away_name = ev.get("AwayTeamName", "")
            # Convert "Home - Away" → "Home vs Away" for normalizer
            vs_name = f"{home_name} vs {away_name}" if home_name and away_name else raw_name
            event_name = normalize_event_name(vs_name)

            # Identify home/away outcome IDs from OutcomeGroups
            outcome_groups = market.get("OutcomeGroups", {})
            home_outcome_ids = set(outcome_groups.get("home", {}).get("outcomes", []))
            away_outcome_ids = set(outcome_groups.get("away", {}).get("outcomes", []))

            # Flatten outcome rows (market.Outcomes is a list of lists)
            flat_outcome_ids: List[int] = []
            for row in market.get("Outcomes", []):
                if isinstance(row, list):
                    flat_outcome_ids.extend(row)
                else:
                    flat_outcome_ids.append(row)

            if "money-line" in market_cname:
                canonical_market = "moneyline"
            elif "puck-line" in market_cname:
                canonical_market = "spread"
            else:
                continue  # unknown market type

            for oid in flat_outcome_ids:
                out = outcomes_by_id.get(oid)
                if not out:
                    continue
                if not out.get("IsDisplay", True) or not out.get("IsActive", True):
                    continue

                odds_decimal = out.get("OddsDecimal")
                if not odds_decimal or odds_decimal <= 1.0:
                    continue

                bet_name = out.get("BetName", "")
                handicap_display = out.get("HandicapDisplay", "")
                handicap_val = out.get("Handicap")  # float or None

                # Determine home/away outcome
                if oid in home_outcome_ids:
                    outcome = "home"
                elif oid in away_outcome_ids:
                    outcome = "away"
                else:
                    # Fallback: match BetName against team names
                    if bet_name == home_name:
                        outcome = "home"
                    elif bet_name == away_name:
                        outcome = "away"
                    else:
                        logger.debug(
                            "[betway] Cannot classify outcome %d (%r) for event %s",
                            oid, bet_name, event_name,
                        )
                        continue

                # Build participant label
                if canonical_market == "spread" and handicap_display:
                    participant = f"{bet_name} {handicap_display}"
                else:
                    participant = bet_name

                records.append(OddsRecord(
                    book=self.BOOK_NAME,
                    sport="nhl",
                    event_name=event_name,
                    event_start=event_start,
                    market=canonical_market,
                    outcome=outcome,
                    decimal_odds=float(odds_decimal),
                    scraped_at=now,
                    participant=participant,
                ))

        return records
