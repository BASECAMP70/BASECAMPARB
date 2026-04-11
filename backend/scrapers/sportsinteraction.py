"""
Sports Interaction scraper — DOM-based (bwin/GVC Angular app).

SI's CDS REST API is Cloudflare-protected when called directly.
Instead we use Playwright + stealth to navigate the sport pages and
extract odds from the rendered Angular components.

URL structure (confirmed 2026-03-27):
  NHL:  /en-ca/sports/hockey-12/betting/usa-9/nhl-34
  NBA:  /en-ca/sports/basketball-7/betting/usa-9/nba-6004
  MLB:  /en-ca/sports/baseball-23/betting/usa-9/mlb-75

DOM structure per game row:
  ms-six-pack-event
    a[href]   → /en-ca/sports/events/{away-slug}-at-{home-slug}-{event_id}
    .grid-six-pack-wrapper          (first = main game, second = 1H/props)
      ms-event-pick x6:  Spread(away), Spread(home),
                         Total(over),  Total(under),
                         Money(away),  Money(home)   ← we only use these two

Money odds are at picks[4] and picks[5].
Team names are derived from the event URL slug.
"""

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import List, Tuple

from playwright_stealth import stealth_async

from normalizer import normalize_event_name
from scrapers.base import OddsRecord, OddsScraper, UA_LIST

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.sportsinteraction.com"

# (sport_key, page_url)
_SPORT_PAGES: List[Tuple[str, str]] = [
    ("nhl",    f"{_BASE_URL}/en-ca/sports/hockey-12/betting/usa-9/nhl-34"),
    ("nba",    f"{_BASE_URL}/en-ca/sports/basketball-7/betting/usa-9/nba-6004"),
    ("mlb",    f"{_BASE_URL}/en-ca/sports/baseball-23/betting/usa-9/mlb-75"),
]

_JS_EXTRACT = """() => {
    const events = [...document.querySelectorAll('ms-six-pack-event')];
    return events.flatMap(ev => {
        const link = ev.querySelector('a[href]');
        const href = link ? link.href : '';
        if (!href) return [];

        // First six-pack wrapper = main game (not 1st-half / props)
        const wrapper = ev.querySelector('.grid-six-pack-wrapper');
        if (!wrapper) return [];

        const picks = [...wrapper.querySelectorAll('ms-event-pick.grid-option-selectable')];
        if (picks.length < 6) return [];

        // Layout: [0] away spread, [1] home spread,
        //         [2] over,        [3] under,
        //         [4] away money,  [5] home money

        // Extracts the decimal odds from a pick (the last number ≥ 1.01 with 2+ decimal places).
        // Works for moneyline ("2.05"), totals ("o6.5 1.87"), and spread ("-1.5 1.87").
        const getPickData = p => {
            const t = (p.querySelector('ms-font-resizer') || p).textContent.replace(/\\s+/g, ' ').trim();
            if (!t) return null;
            const oddsMatches = t.match(/\\b\\d+\\.\\d{2,}\\b/g);
            if (!oddsMatches) return null;
            const price = parseFloat(oddsMatches[oddsMatches.length - 1]);
            if (price <= 1.0) return null;
            // Handicap/line is the first signed or unsigned number (e.g. -1.5, +1.5, 6.5)
            const lineMatch = t.match(/([+-]?\\d+\\.?\\d*)/);
            const line = lineMatch ? lineMatch[1] : null;
            return { price, line };
        };

        const awayMoney = getPickData(picks[4]);
        const homeMoney = getPickData(picks[5]);
        if (!awayMoney || !homeMoney) return [];

        return [{
            href,
            awayMoney,
            homeMoney,
            awaySpread: getPickData(picks[0]),
            homeSpread: getPickData(picks[1]),
            overTotal:  getPickData(picks[2]),
            underTotal: getPickData(picks[3]),
        }];
    });
}"""


def _slug_to_name(slug: str) -> str:
    """Convert 'los-angeles-clippers' → 'Los Angeles Clippers'."""
    return " ".join(w.capitalize() for w in slug.split("-"))


def _parse_event_href(href: str) -> Tuple[str, str, str]:
    """
    Parse href like:
      https://www.sportsinteraction.com/en-ca/sports/events/los-angeles-clippers-at-indiana-pacers-19049071
    Returns (away_name, home_name, event_url).
    """
    m = re.search(r'/events/(.+)-at-(.+?)-(\d+)$', href)
    if not m:
        return "", "", href
    away_name = _slug_to_name(m.group(1))
    home_name = _slug_to_name(m.group(2))
    return away_name, home_name, href


class SportsInteractionScraper(OddsScraper):
    BOOK_NAME = "sportsinteraction"
    ODDS_URL  = f"{_BASE_URL}/en-ca/sports/hockey-12/betting/usa-9/nhl-34"

    async def fetch_odds(self) -> List[OddsRecord]:
        now = datetime.now(timezone.utc)
        records: List[OddsRecord] = []

        context = await self.browser.new_context(
            user_agent=random.choice(UA_LIST),
            locale="en-CA",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        await stealth_async(page)

        try:
            for sport_key, url in _SPORT_PAGES:
                try:
                    sport_records = await self._scrape_sport(page, sport_key, url, now)
                    records.extend(sport_records)
                    logger.info("[sportsinteraction] %s → %d records", sport_key, len(sport_records))
                except Exception as exc:
                    logger.warning("[sportsinteraction] %s scrape failed: %s", sport_key, exc)
        finally:
            try:
                await asyncio.wait_for(context.close(), timeout=5)
            except Exception:
                pass

        logger.info("[sportsinteraction] total %d records", len(records))
        return records

    async def _scrape_sport(
        self,
        page,
        sport_key: str,
        url: str,
        now: datetime,
    ) -> List[OddsRecord]:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # Wait for game rows to appear
        try:
            await page.wait_for_selector("ms-six-pack-event", timeout=20_000)
        except Exception:
            logger.warning("[sportsinteraction] No ms-six-pack-event found on %s", url)
            return []

        # Let Angular finish rendering odds
        await asyncio.sleep(3)

        raw_events = await page.evaluate(_JS_EXTRACT)

        records: List[OddsRecord] = []
        for ev in raw_events:
            href = ev.get("href", "")
            if not href:
                continue

            away_name, home_name, event_url = _parse_event_href(href)
            if not away_name or not home_name:
                logger.debug("[sportsinteraction] Could not parse href: %s", href)
                continue

            event_name = normalize_event_name(f"{home_name} vs {away_name}")

            def _add(market: str, outcome: str, participant: str, data):
                if not data:
                    return
                price = data.get("price", 0)
                if price <= 1.0:
                    return
                records.append(OddsRecord(
                    book=self.BOOK_NAME,
                    sport=sport_key,
                    event_name=event_name,
                    event_start=now,
                    market=market,
                    outcome=outcome,
                    decimal_odds=float(price),
                    scraped_at=now,
                    participant=participant,
                    event_url=event_url,
                ))

            # Moneyline
            _add("moneyline", "away", away_name, ev.get("awayMoney"))
            _add("moneyline", "home", home_name, ev.get("homeMoney"))

            # Spread — participant includes handicap line (e.g. "Lakers -1.5")
            away_spread = ev.get("awaySpread")
            home_spread = ev.get("homeSpread")
            if away_spread:
                line = away_spread.get("line", "")
                _add("spread", "away", f"{away_name} {line}".strip(), away_spread)
            if home_spread:
                line = home_spread.get("line", "")
                _add("spread", "home", f"{home_name} {line}".strip(), home_spread)

            # Totals
            _add("totals", "over",  "Over",  ev.get("overTotal"))
            _add("totals", "under", "Under", ev.get("underTotal"))

        return records
