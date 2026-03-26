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

  Workflow per sport:
    1. POST GetGroup — returns event IDs for the sport/league
    2. POST GetEventsWithMultipleMarkets — returns events + markets + outcomes

  Supported sports and their market cnames (discovered via API probing):
    NHL:      money-line
    NBA:      money-line
    MLB:      money-line
    Soccer:   draw-no-bet  (2-way, no draw market available in CA)
"""

import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import List, Tuple

import aiohttp

from normalizer import normalize_event_name
from scrapers.base import OddsRecord, OddsScraper, UA_LIST

logger = logging.getLogger(__name__)

_API_BASE = "https://betway.com/g/services/api"

# Canada market constants
_BRAND_ID            = 3
_LANGUAGE_ID         = 25
_TERRITORY_ID        = 38
_TERRITORY_CODE      = "CA"
_CLIENT_TYPE_ID      = 2
_JURISDICTION_ID     = 2
_CLIENT_INTEGRATOR_ID = 1

# (group_cname, category_cname, subcat_cname, sport_key, market_cnames)
_SPORT_CONFIGS: List[Tuple[str, str, str, str, List[str]]] = [
    ("nhl",            "ice-hockey",  "north-america", "nhl",    ["money-line"]),
    ("nba",            "basketball",  "usa",           "nba",    ["money-line"]),
    ("mlb",            "baseball",    "usa",           "mlb",    ["money-line"]),
    ("premier-league", "soccer",      "england",       "soccer", ["draw-no-bet"]),
    ("la-liga",        "soccer",      "spain",         "soccer", ["draw-no-bet"]),
    ("bundesliga",     "soccer",      "germany",       "soccer", ["draw-no-bet"]),
    ("serie-a",        "soccer",      "italy",         "soccer", ["draw-no-bet"]),
    ("ligue-1",        "soccer",      "france",        "soccer", ["draw-no-bet"]),
    ("mls",            "soccer",      "north-america", "soccer", ["draw-no-bet"]),
]


def _base_payload() -> dict:
    return {
        "BrandId":             _BRAND_ID,
        "LanguageId":          _LANGUAGE_ID,
        "TerritoryId":         _TERRITORY_ID,
        "TerritoryCode":       _TERRITORY_CODE,
        "ClientTypeId":        _CLIENT_TYPE_ID,
        "JurisdictionId":      _JURISDICTION_ID,
        "ClientIntegratorId":  _CLIENT_INTEGRATOR_ID,
        "CorrelationId":       str(uuid.uuid4()),
    }


def _canonical_market(cname: str) -> str:
    """Map a Betway market cname to our canonical market key."""
    if "money-line" in cname or "draw-no-bet" in cname:
        return "moneyline"
    return ""


class BetwayScraper(OddsScraper):
    BOOK_NAME = "betway"
    ODDS_URL  = "https://betway.com/g/en-ca/sports"

    async def fetch_odds(self) -> List[OddsRecord]:
        now = datetime.now(timezone.utc)
        try:
            records = await self._fetch_all_sports(now)
            logger.info("[betway] API returned %d records across all sports", len(records))
            return records
        except Exception as exc:
            logger.warning("[betway] API fetch failed: %s", exc)
            return []

    async def _fetch_all_sports(self, now: datetime) -> List[OddsRecord]:
        headers = {
            "User-Agent":      random.choice(UA_LIST),
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "en-CA,en;q=0.9",
            "Content-Type":    "application/json",
            "Origin":          "https://betway.com",
            "Referer":         "https://betway.com/g/en-ca/sports/",
        }

        async with aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=45),
        ) as session:
            # Fetch all sport configs concurrently
            tasks = [
                self._fetch_sport(session, cfg, now)
                for cfg in _SPORT_CONFIGS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        records: List[OddsRecord] = []
        for cfg, result in zip(_SPORT_CONFIGS, results):
            sport_key = cfg[3]
            if isinstance(result, Exception):
                logger.warning("[betway] %s fetch error: %s", sport_key, result)
            else:
                records.extend(result)
        return records

    async def _fetch_sport(
        self,
        session: aiohttp.ClientSession,
        cfg: Tuple[str, str, str, str, List[str]],
        now: datetime,
    ) -> List[OddsRecord]:
        group_cname, cat_cname, subcat_cname, sport_key, market_cnames = cfg

        event_ids = await self._get_event_ids(session, group_cname, cat_cname, subcat_cname)
        if not event_ids:
            logger.debug("[betway] No events for %s/%s/%s", group_cname, cat_cname, subcat_cname)
            return []

        return await self._get_odds(session, event_ids, market_cnames, sport_key, now)

    # ── API calls ─────────────────────────────────────────────────────────────

    async def _get_event_ids(
        self,
        session: aiohttp.ClientSession,
        group_cname: str,
        category_cname: str,
        subcat_cname: str,
    ) -> List[int]:
        """POST GetGroup and return non-outright event IDs."""
        payload = _base_payload()
        payload.update({
            "GroupCName":       group_cname,
            "CategoryCName":    category_cname,
            "SubCategoryCName": subcat_cname,
            "PremiumOnly":      False,
        })
        url = f"{_API_BASE}/events/v2/GetGroup"
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                raise RuntimeError(f"GetGroup {group_cname} HTTP {resp.status}")
            data = await resp.json(content_type=None)

        return [
            s["EventId"]
            for s in data.get("EventSummaries", [])
            if not s.get("IsOutright", True)
        ]

    async def _get_odds(
        self,
        session: aiohttp.ClientSession,
        event_ids: List[int],
        market_cnames: List[str],
        sport_key: str,
        now: datetime,
    ) -> List[OddsRecord]:
        payload = _base_payload()
        payload.update({
            "EventMarketSets": [
                {
                    "EventIds":    event_ids,
                    "MarketCNames": market_cnames,
                }
            ],
            "ScoreboardRequest": {"IncidentRequest": {}, "ScoreboardType": 3},
        })
        url = f"{_API_BASE}/events/v2/GetEventsWithMultipleMarkets"
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                raise RuntimeError(f"GetEventsWithMultipleMarkets HTTP {resp.status}")
            data = await resp.json(content_type=None)

        if not data.get("Success", True):
            raise RuntimeError(f"API errors: {data.get('Errors', [])}")

        events_by_id   = {e["Id"]: e for e in data.get("Events",   [])}
        outcomes_by_id = {o["Id"]: o for o in data.get("Outcomes", [])}

        records: List[OddsRecord] = []
        for market in data.get("Markets", []):
            recs = self._parse_market(
                market, events_by_id, outcomes_by_id, sport_key, now
            )
            records.extend(recs)

        return records

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_market(
        self,
        market: dict,
        events_by_id: dict,
        outcomes_by_id: dict,
        sport_key: str,
        now: datetime,
    ) -> List[OddsRecord]:
        if market.get("IsSuspended", False):
            return []

        cname = market.get("MarketCName", "")
        canonical_market = _canonical_market(cname)
        if not canonical_market:
            return []

        event_id = market.get("EventId")
        ev = events_by_id.get(event_id)
        if not ev:
            return []

        # Build a slug-based deep-link using team CNames (e.g. minnesota-wild-vs-florida-panthers)
        # URL format mirrors the group URL: /g/en/sports/ev/{cat}/{sub}/{group}/{away}-vs-{home}/
        away_cname  = ev.get("AwayTeamCName", "")
        home_cname  = ev.get("HomeTeamCName", "")
        cat_cname   = ev.get("CategoryCName", "")
        sub_cname   = ev.get("SubCategoryCName", "")
        grp_cname   = ev.get("GroupCName", "")
        if all([away_cname, home_cname, cat_cname, sub_cname, grp_cname]):
            event_url = (
                f"https://betway.com/g/en-ca/sports/ev/"
                f"{cat_cname}/{sub_cname}/{grp_cname}/"
                f"{away_cname}-vs-{home_cname}/"
            )
        else:
            event_url = f"https://betway.com/g/en-ca/sports/ev/{event_id}/" if event_id else ""

        # Event start time
        ms = ev.get("Milliseconds", 0)
        try:
            event_start = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        except Exception:
            event_start = now

        # Canonical event name
        home_name = ev.get("HomeTeamName", "")
        away_name = ev.get("AwayTeamName", "")
        raw_name  = ev.get("EventName", "")
        vs_name   = f"{home_name} vs {away_name}" if home_name and away_name else raw_name
        event_name = normalize_event_name(vs_name)

        # Home / away outcome ID sets
        outcome_groups  = market.get("OutcomeGroups", {})
        home_outcome_ids = set(outcome_groups.get("home", {}).get("outcomes", []))
        away_outcome_ids = set(outcome_groups.get("away", {}).get("outcomes", []))

        # Flatten outcome ID list
        flat_ids: List[int] = []
        for row in market.get("Outcomes", []):
            if isinstance(row, list):
                flat_ids.extend(row)
            else:
                flat_ids.append(row)

        records = []
        for oid in flat_ids:
            out = outcomes_by_id.get(oid)
            if not out:
                continue
            if not out.get("IsDisplay", True) or not out.get("IsActive", True):
                continue

            odds_decimal = out.get("OddsDecimal")
            if not odds_decimal or odds_decimal <= 1.0:
                continue

            bet_name        = out.get("BetName", "")
            handicap_display = out.get("HandicapDisplay", "")

            # Determine home / away
            if oid in home_outcome_ids:
                outcome = "home"
            elif oid in away_outcome_ids:
                outcome = "away"
            else:
                if bet_name == home_name:
                    outcome = "home"
                elif bet_name == away_name:
                    outcome = "away"
                else:
                    logger.debug(
                        "[betway] Cannot classify outcome %d (%r) for %s",
                        oid, bet_name, event_name,
                    )
                    continue

            # Participant label: team name + handicap if applicable
            if canonical_market == "spread" and handicap_display:
                participant = f"{bet_name} {handicap_display}"
            else:
                participant = bet_name

            records.append(OddsRecord(
                book=self.BOOK_NAME,
                sport=sport_key,
                event_name=event_name,
                event_start=event_start,
                market=canonical_market,
                outcome=outcome,
                decimal_odds=float(odds_decimal),
                scraped_at=now,
                participant=participant,
                event_url=event_url,
            ))

        return records
