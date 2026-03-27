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
        const getOdds = p => {
            const t = (p.querySelector('ms-font-resizer') || p).textContent.trim();
            const n = parseFloat(t);
            return isNaN(n) ? null : n;
        };

        const awayMoney = getOdds(picks[4]);
        const homeMoney = getOdds(picks[5]);
        if (!awayMoney || !homeMoney || awayMoney <= 1.0 || homeMoney <= 1.0) return [];

        return [{ href, awayMoney, homeMoney }];
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
        await stealth_async(context)
        page = await context.new_page()

        try:
            for sport_key, url in _SPORT_PAGES:
                try:
                    sport_records = await self._scrape_sport(page, sport_key, url, now)
                    records.extend(sport_records)
                    logger.info("[sportsinteraction] %s → %d records", sport_key, len(sport_records))
                except Exception as exc:
                    logger.warning("[sportsinteraction] %s scrape failed: %s", sport_key, exc)
        finally:
            await context.close()

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
            href      = ev.get("href", "")
            away_money = ev.get("awayMoney")
            home_money = ev.get("homeMoney")

            if not href or not away_money or not home_money:
                continue

            away_name, home_name, event_url = _parse_event_href(href)
            if not away_name or not home_name:
                logger.debug("[sportsinteraction] Could not parse href: %s", href)
                continue

            event_name = normalize_event_name(f"{home_name} vs {away_name}")

            for outcome, participant, decimal_odds in [
                ("away", away_name, away_money),
                ("home", home_name, home_money),
            ]:
                records.append(OddsRecord(
                    book=self.BOOK_NAME,
                    sport=sport_key,
                    event_name=event_name,
                    event_start=now,
                    market="moneyline",
                    outcome=outcome,
                    decimal_odds=float(decimal_odds),
                    scraped_at=now,
                    participant=participant,
                    event_url=event_url,
                ))

        return records
