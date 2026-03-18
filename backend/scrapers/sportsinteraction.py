"""
Sports Interaction scraper.

SI uses the bwin/GVC CDS (Content Delivery System) REST API:

  Base URL: https://www.sportsinteraction.com/cds-api/bettingoffer/fixtures
  Required params:
    x-bwin-accessid  = OGQ2ZTg0MGYtYjkwNS00ZmI1LTlkN2YtZDVmY2Y0ZDNkYmFl
    lang             = en-ca
    country          = CA
    userCountry      = CA
    fixtureTypes     = Standard
    state            = PreMatch
    count            = 100

  Sport IDs (bwin canonical):
    4  = Ice Hockey
    1  = Soccer
    2  = Basketball
    3  = Baseball
    6  = American Football

  The fixtures endpoint returns:
    {
      "fixtures": [
        {
          "id": "...",
          "name": {"value": "Edmonton Oilers vs Calgary Flames"},
          "startDate": "2024-03-17T02:00:00Z",
          "stage": "PreMatch",
          "optionMarkets": [
            {
              "name": {"value": "Money Line"},
              "options": [
                {"name": {"value": "Edmonton Oilers"}, "price": {"decimal": 1.85}},
                {"name": {"value": "Calgary Flames"},  "price": {"decimal": 2.10}}
              ]
            }
          ]
        }
      ]
    }

  If optionMarkets is empty, the API returns fixture metadata but no odds.
  In that case we fall back to DOM scraping.

DOM fallback:
  The bwin Angular app renders event rows tagged with Angular component selectors.
  We capture the full page text and look for patterns.
"""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from typing import List

import aiohttp
from playwright_stealth import stealth_async

from normalizer import normalize_event_name, normalize_market_outcome
from scrapers.base import OddsRecord, OddsScraper, UA_LIST

logger = logging.getLogger(__name__)

_ACCESS_ID = "OGQ2ZTg0MGYtYjkwNS00ZmI1LTlkN2YtZDVmY2Y0ZDNkYmFl"
_BASE_PARAMS = (
    f"x-bwin-accessid={_ACCESS_ID}"
    f"&lang=en-ca&country=CA&userCountry=CA"
    f"&fixtureTypes=Standard&state=PreMatch"
)
_FIXTURES_URL = (
    "https://www.sportsinteraction.com/cds-api/bettingoffer/fixtures"
    f"?{_BASE_PARAMS}&count=100"
)

# bwin sport IDs to try for hockey (4 is the canonical bwin ice-hockey ID)
_HOCKEY_SPORT_IDS = [4, 11, 13]

_SPORT_ID_MAP = {
    4: "nhl",
    11: "nhl",
    13: "nhl",
    1: "soccer",
    2: "nba",
    3: "mlb",
    6: "nfl",
}

_MARKET_NAME_MAP = {
    "money line": "moneyline",
    "moneyline": "moneyline",
    "1x2": "moneyline",
    "match winner": "moneyline",
    "puck line": "spread",
    "spread": "spread",
    "total": "totals",
    "over/under": "totals",
    "game total": "totals",
}


class SportsInteractionScraper(OddsScraper):
    BOOK_NAME = "sportsinteraction"
    ODDS_URL = "https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/"

    async def fetch_odds(self) -> List[OddsRecord]:
        records: List[OddsRecord] = []
        now = datetime.now(timezone.utc)

        # ── Primary: CDS REST API ────────────────────────────────────────────
        try:
            records = await self._fetch_via_api(now)
            if records:
                logger.info("[%s] API returned %d records", self.BOOK_NAME, len(records))
                return records
        except Exception as exc:
            logger.debug("[%s] API fetch failed (%s), trying DOM fallback", self.BOOK_NAME, exc)

        # ── Fallback: browser DOM ────────────────────────────────────────────
        try:
            records = await self._fetch_via_dom(now)
            logger.info("[%s] DOM fallback returned %d records", self.BOOK_NAME, len(records))
        except Exception as exc:
            logger.warning("[%s] DOM fallback also failed: %s", self.BOOK_NAME, exc)

        return records

    async def _fetch_via_api(self, now: datetime) -> List[OddsRecord]:
        """Try the CDS fixtures endpoint for hockey sport IDs."""
        records: List[OddsRecord] = []
        headers = {
            "Accept": "application/json",
            "x-bwin-accessid": _ACCESS_ID,
            "User-Agent": random.choice(UA_LIST),
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            for sport_id in _HOCKEY_SPORT_IDS:
                url = f"{_FIXTURES_URL}&sportId={sport_id}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    fixtures = data.get("fixtures", [])

                    for fixture in fixtures:
                        name = fixture.get("name", {}).get("value", "")
                        stage = fixture.get("stage", "")
                        start_raw = fixture.get("startDate", "")

                        if stage not in ("PreMatch", ""):
                            continue

                        # Parse event name → home vs away
                        # SI names like "Edmonton Oilers vs Calgary Flames"
                        event_name = normalize_event_name(name)

                        # Parse start time
                        try:
                            from datetime import datetime as dt
                            event_start = dt.fromisoformat(start_raw.replace("Z", "+00:00"))
                        except Exception:
                            event_start = now

                        sport = _SPORT_ID_MAP.get(sport_id, "nhl")
                        option_markets = fixture.get("optionMarkets", [])

                        for market in option_markets:
                            market_label = market.get("name", {}).get("value", "").lower()
                            canonical_market = _MARKET_NAME_MAP.get(market_label)
                            if not canonical_market:
                                continue

                            options = market.get("options", [])
                            for option in options:
                                opt_name = option.get("name", {}).get("value", "").lower()
                                price = option.get("price", {})
                                decimal_odds = price.get("decimal")
                                if not decimal_odds:
                                    continue

                                # Map option name to canonical outcome
                                if canonical_market == "moneyline":
                                    # Match home/away from event name
                                    parts = event_name.lower().split(" vs ")
                                    if len(parts) == 2:
                                        outcome = "home" if opt_name in parts[0] else "away"
                                    else:
                                        outcome = "home"
                                    participant = option.get("name", {}).get("value", "")
                                elif canonical_market == "totals":
                                    outcome = "over" if "over" in opt_name else "under"
                                    participant = "Over" if outcome == "over" else "Under"
                                elif canonical_market == "spread":
                                    parts = event_name.lower().split(" vs ")
                                    outcome = "home" if len(parts) == 2 and opt_name in parts[0] else "away"
                                    participant = option.get("name", {}).get("value", "")
                                else:
                                    continue

                                records.append(OddsRecord(
                                    book=self.BOOK_NAME,
                                    sport=sport,
                                    event_name=event_name,
                                    event_start=event_start,
                                    market=canonical_market,
                                    outcome=outcome,
                                    decimal_odds=float(decimal_odds),
                                    scraped_at=now,
                                    participant=participant,
                                ))

                    if records:
                        break  # found data, no need to try other sport IDs

        return records

    async def _fetch_via_dom(self, now: datetime) -> List[OddsRecord]:
        """DOM fallback: navigate hockey page and extract visible odds."""
        context = await self.browser.new_context(
            user_agent=random.choice(UA_LIST),
            locale="en-CA",
        )
        await stealth_async(context)
        page = await context.new_page()
        records: List[OddsRecord] = []

        try:
            # Try multiple SI hockey URLs
            for url in [
                "https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/",
                "https://www.sportsinteraction.com/en-ca/sports/ice-hockey/",
                "https://www.sportsinteraction.com/en-ca/sports-betting/nhl/",
            ]:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                    await asyncio.sleep(6)
                    title = await page.title()
                    if "not found" not in title.lower():
                        break
                except Exception:
                    continue

            raw = await page.evaluate("""() => {
                // bwin/GVC Angular app: events are in ms-event or similar components
                // Try various selectors used by the bwin platform
                const results = [];
                const sels = [
                    '[class*="ms-event"]', 'ms-event', '[class*="event-row"]',
                    '[class*="EventRow"]', '[class*="fixture"]',
                ];

                for (const sel of sels) {
                    const els = document.querySelectorAll(sel);
                    if (!els.length) continue;

                    for (const el of els) {
                        const text = el.textContent.trim();
                        // Look for elements with decimal odds (X.XX pattern) and team names
                        const odds = text.match(/[1-9]\\.[0-9]{2}/g);
                        if (!odds || odds.length < 2) continue;

                        // Try to split into parts
                        const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
                        if (lines.length < 2) continue;

                        results.push({
                            text: text.slice(0, 300),
                            lines: lines.slice(0, 10),
                            odds: odds.slice(0, 4)
                        });
                    }
                    if (results.length > 0) break;
                }

                // Also scan for any element with 2+ adjacent decimal odds
                if (results.length === 0) {
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                    let node;
                    while ((node = walker.nextNode()) && results.length < 20) {
                        const txt = node.textContent.trim();
                        const odds = txt.match(/[1-9]\\.[0-9]{2}/g);
                        if (odds && odds.length >= 2 && txt.length < 400) {
                            if (node.children.length < 10) {
                                const lines = txt.split('\\n').map(s => s.trim()).filter(Boolean);
                                results.push({text: txt.slice(0, 300), lines: lines.slice(0, 8), odds});
                            }
                        }
                    }
                }

                return results;
            }""")

            for ev in raw:
                lines = ev.get("lines", [])
                odds = [float(o) for o in ev.get("odds", []) if float(o) > 1.0]

                if len(lines) < 2 or len(odds) < 2:
                    continue

                home = lines[0]
                away = lines[1]
                if not home or not away:
                    continue

                event_name = normalize_event_name(f"{home} vs {away}")

                if odds[0] > 1.0:
                    records.append(OddsRecord(
                        book=self.BOOK_NAME, sport="nhl",
                        event_name=event_name, event_start=now,
                        market="moneyline", outcome="home",
                        decimal_odds=odds[0], scraped_at=now,
                        participant=home,
                    ))
                if len(odds) > 1 and odds[1] > 1.0:
                    records.append(OddsRecord(
                        book=self.BOOK_NAME, sport="nhl",
                        event_name=event_name, event_start=now,
                        market="moneyline", outcome="away",
                        decimal_odds=odds[1], scraped_at=now,
                        participant=away,
                    ))

        finally:
            await context.close()

        return records
