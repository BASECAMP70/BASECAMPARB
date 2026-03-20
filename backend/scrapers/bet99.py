"""
Bet99 scraper — Alberta market (bet99.com).

Bet99 runs on the Altenar sportsbook platform.  All odds are available
via a public REST API — no browser or authentication required.

API endpoint:
  GET https://sb2frontend-altenar2.biahosted.com/api/widget/GetEventsByChamp
  Required params:
    culture        = en-US
    timezoneOffset = 360
    integration    = bet99
    deviceType     = 1
    numFormat      = en-GB
    countryCode    = CA
    stateCode      = AB       ← pins to Alberta jurisdiction
    champId        = 0
    champIds       = 3232     ← NHL championship ID
    eventCount     = 100

Response structure (all in one flat response):
  events[]       — each has competitorIds[], marketIds[], startDate, name
  competitors[]  — id → name lookup
  markets[]      — id, typeId, isMB, sv (special value), oddIds[]
  odds[]         — id, price (decimal), competitorId, name, oddStatus

Market typeIds used:
  406  Winner (incl. OT & penalties)  — 2-way moneyline; single per event
  410  Handicap (incl. OT)            — puck line; isMB=True picks ±1.5
  412  Total (incl. OT)               — totals; isMB=True picks main line

home/away: competitorIds[0] = home, competitorIds[1] = away.
Matched via the competitorId field on each odd selection.
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import List

import aiohttp

from normalizer import normalize_event_name
from scrapers.base import OddsRecord, OddsScraper, UA_LIST

logger = logging.getLogger(__name__)

_API_URL = (
    "https://sb2frontend-altenar2.biahosted.com/api/widget/GetEventsByChamp"
    "?culture=en-US&timezoneOffset=360&integration=bet99&deviceType=1"
    "&numFormat=en-GB&countryCode=CA&stateCode=AB&champId=0"
    "&champIds=3232&eventCount=100"
)

# Market typeId constants
_TID_MONEYLINE = 406   # Winner (incl. OT & penalties) — 2-way
_TID_SPREAD    = 410   # Handicap (incl. OT)
_TID_TOTALS    = 412   # Total (incl. OT)


class Bet99Scraper(OddsScraper):
    BOOK_NAME = "bet99"
    ODDS_URL  = "https://bet99.com/sports/hockey"

    async def fetch_odds(self) -> List[OddsRecord]:
        now = datetime.now(timezone.utc)
        try:
            records = await self._fetch_via_api(now)
            logger.info("[bet99] API returned %d records", len(records))
            return records
        except Exception as exc:
            logger.warning("[bet99] fetch failed: %s", exc)
            return []

    async def _fetch_via_api(self, now: datetime) -> List[OddsRecord]:
        headers = {
            "User-Agent": random.choice(UA_LIST),
            "Accept": "application/json",
            "Referer": "https://bet99.com/",
        }
        async with aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as session:
            async with session.get(_API_URL) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)

        return self._parse(data, now)

    def _parse(self, data: dict, now: datetime) -> List[OddsRecord]:
        records: List[OddsRecord] = []

        comps       = {c["id"]: c["name"] for c in data.get("competitors", [])}
        odds_by_id  = {o["id"]: o         for o in data.get("odds",        [])}
        mkts_by_id  = {m["id"]: m         for m in data.get("markets",     [])}

        for ev in data.get("events", []):
            # Skip live / in-progress events
            if ev.get("et", 0) != 0:
                continue

            cids = ev.get("competitorIds", [])
            if len(cids) < 2:
                continue

            home_id, away_id = cids[0], cids[1]
            home_name = comps.get(home_id, "")
            away_name = comps.get(away_id, "")
            if not home_name or not away_name:
                continue

            event_name = normalize_event_name(f"{home_name} vs {away_name}")

            raw_start = ev.get("startDate", "")
            try:
                event_start = datetime.fromisoformat(
                    raw_start.replace("Z", "+00:00")
                )
            except Exception:
                event_start = now

            # Index this event's markets by typeId
            event_markets: dict[int, list] = {}
            for mid in ev.get("marketIds", []):
                m = mkts_by_id.get(mid)
                if m:
                    event_markets.setdefault(m["typeId"], []).append(m)

            # ── Moneyline (typeId 406) ────────────────────────────────────
            for m in event_markets.get(_TID_MONEYLINE, []):
                recs = self._make_moneyline_records(
                    m, home_id, away_id, home_name, away_name,
                    event_name, event_start, odds_by_id, now,
                )
                records.extend(recs)
                break  # only one moneyline per event

            # ── Spread / puck line (typeId 410, isMB=True) ───────────────
            for m in event_markets.get(_TID_SPREAD, []):
                if not m.get("isMB"):
                    continue
                recs = self._make_spread_records(
                    m, home_id, away_id,
                    event_name, event_start, odds_by_id, now,
                )
                records.extend(recs)
                break  # one main puck-line per event

        return records

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _active_odds(self, market: dict, odds_by_id: dict) -> list:
        """Return active (oddStatus==0) outcome dicts for a market."""
        return [
            odds_by_id[oid]
            for oid in market.get("oddIds", [])
            if oid in odds_by_id and odds_by_id[oid].get("oddStatus", 0) == 0
        ]

    def _make_moneyline_records(
        self, market, home_id, away_id, home_name, away_name,
        event_name, event_start, odds_by_id, now,
    ) -> List[OddsRecord]:
        records = []
        for o in self._active_odds(market, odds_by_id):
            price = o.get("price", 0)
            if not price or price <= 1.0:
                continue
            cid = o.get("competitorId")
            if cid == home_id:
                outcome, participant = "home", home_name
            elif cid == away_id:
                outcome, participant = "away", away_name
            else:
                continue  # draw or unknown — skip for hockey moneyline

            records.append(OddsRecord(
                book=self.BOOK_NAME,
                sport="nhl",
                event_name=event_name,
                event_start=event_start,
                market="moneyline",
                outcome=outcome,
                decimal_odds=float(price),
                scraped_at=now,
                participant=participant,
            ))
        return records

    def _make_spread_records(
        self, market, home_id, away_id,
        event_name, event_start, odds_by_id, now,
    ) -> List[OddsRecord]:
        records = []
        for o in self._active_odds(market, odds_by_id):
            price = o.get("price", 0)
            if not price or price <= 1.0:
                continue
            cid = o.get("competitorId")
            if cid == home_id:
                outcome = "home"
            elif cid == away_id:
                outcome = "away"
            else:
                continue

            participant = o.get("name", "")  # e.g. "Anaheim Ducks (-1.5)"

            records.append(OddsRecord(
                book=self.BOOK_NAME,
                sport="nhl",
                event_name=event_name,
                event_start=event_start,
                market="spread",
                outcome=outcome,
                decimal_odds=float(price),
                scraped_at=now,
                participant=participant,
            ))
        return records
