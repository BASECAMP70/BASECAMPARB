"""
Bet365 Canada scraper.

DOM structure (verified via live Playwright inspection on bet365.ca):

  Fixture rows:   [class*="cpm-ParticipantFixtureDetailsIceHockey"]
    Team names embedded as concatenated text, e.g. "NY IslandersTOR Maple Leafs7:07 PM4"
    Home team first, then away team.

  Odds buttons:   [class*="cpm-ParticipantOdds"][class*="gl-Participant_General"]
    - Class modifier "_Odds_Left"  → home team odds
    - Class modifier "_Odds_Right" → away team odds
    - The visible text of the inner span holds the decimal value, e.g. "2.05"

  Market groups:  [class*="gl-MarketGroup"]
    Each group covers one market (Money Line / Spread / Totals) for a set of games.
    The market label appears in the header: [class*="gl-MarketGroupLabel"] or header text.

Strategy:
  1. Navigate to /en/sports/ice-hockey/ to get the main NHL money-line listing.
  2. For each market group, read its label.  Skip non-moneyline groups.
  3. Walk fixture elements inside the group; match each fixture to its pair of odds buttons.
  4. Produce OddsRecord entries.

American odds ("+165" / "-200") are converted to decimal automatically if detected.
"""

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import List

from playwright_stealth import stealth_async

from normalizer import normalize_event_name, normalize_market_outcome
from scrapers.base import OddsRecord, OddsScraper, UA_LIST

logger = logging.getLogger(__name__)

_SPORT_MAP = {
    "ice hockey": "nhl",
    "hockey": "nhl",
    "nhl": "nhl",
    "basketball": "nba",
    "nba": "nba",
    "football": "nfl",
    "nfl": "nfl",
    "baseball": "mlb",
    "mlb": "mlb",
    "soccer": "soccer",
}


def _american_to_decimal(val: float) -> float:
    """Convert American odds to decimal."""
    if val >= 100:
        return round(val / 100 + 1, 4)
    elif val <= -100:
        return round(100 / abs(val) + 1, 4)
    return val


def _parse_odds(text: str) -> "float | None":
    """Parse an odds string to decimal float.  Handles decimal, American, fractional,
    and puck-line combined strings like '-1.5+165' or '+1.5-200'."""
    text = text.strip()
    if not text:
        return None
    # Decimal: "2.05", "1.87"
    m = re.match(r'^(\d+\.\d+)$', text)
    if m:
        return float(m.group(1))
    # Plain American: "+165", "-200", "165"
    m = re.match(r'^([+-]?\d+)$', text)
    if m:
        return _american_to_decimal(float(m.group(1)))
    # Fractional: "4/5"
    m = re.match(r'^(\d+)/(\d+)$', text)
    if m:
        num, den = float(m.group(1)), float(m.group(2))
        return round(num / den + 1, 4)
    # Puck-line combined: "-1.5+165", "+1.5-200"
    # Extract the trailing American odds (last +/- followed by digits)
    m = re.search(r'([+-]\d+)$', text)
    if m:
        return _american_to_decimal(float(m.group(1)))
    return None


class Bet365Scraper(OddsScraper):
    BOOK_NAME = "bet365"
    # NHL landing page — shows puck-line odds for all of today's games
    ODDS_URL = "https://www.bet365.ca/en/sports/ice-hockey/nhl/"
    # Outer fixture rows carry the rcl-Market class; sub-elements do not
    ODDS_CONTAINER_SELECTOR = '[class*="cpm-ParticipantFixtureDetailsIceHockey"][class*="rcl-Market"]'

    async def fetch_odds(self) -> List[OddsRecord]:
        context = await self.browser.new_context(
            user_agent=random.choice(UA_LIST),
            locale="en-CA",
            geolocation={"latitude": 53.5461, "longitude": -113.4938, "accuracy": 50},
            permissions=["geolocation"],
        )
        await stealth_async(context)
        page = await context.new_page()
        records: List[OddsRecord] = []
        now = datetime.now(timezone.utc)

        try:
            await page.goto(self.ODDS_URL, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_selector(self.ODDS_CONTAINER_SELECTOR, timeout=20_000)
            await asyncio.sleep(random.uniform(3.0, 5.0))

            raw = await page.evaluate("""() => {
                // ── Strategy ────────────────────────────────────────────────────
                // bet365 NHL page (spotlight coupon layout):
                //
                //  gl-MarketGroupContainer  ← one per market type (puck line, totals, ML, etc.)
                //    ├─ cpm-ParticipantFixtureDetailsIceHockey + rcl-Market  ← OUTER fixture row
                //    │    └─ (many sub-elements that also match the prefix class)
                //    └─ cpm-MarketOdds  ← market column wrapper (NOT inside the fixture)
                //         └─ cpm-ParticipantOdds gl-Participant_General  ← individual odds buttons
                //
                // Outer fixture rows are identified by ALSO having class "rcl-Market".
                // Sub-elements only have the prefix (cpm-ParticipantFixtureDetailsIceHockey_*).
                //
                // Approach:
                //   • Find the hockey container (has outer fixture rows).
                //   • Separate its odds into puck-line (Handicap class) and moneyline (no Handicap).
                //   • Match outer fixtures with their odds by index: fixture[i] → odds[i*2, i*2+1].

                const outerFixtures = [
                    ...document.querySelectorAll(
                        '[class*="cpm-ParticipantFixtureDetailsIceHockey"][class*="rcl-Market"]'
                    )
                ];
                if (!outerFixtures.length) return [];

                // Find the gl-MarketGroupContainer that owns these fixtures
                const hockeyContainer = (() => {
                    let el = outerFixtures[0].parentElement;
                    for (let i = 0; i < 8 && el; i++) {
                        if (el.className.includes('gl-MarketGroupContainer')) return el;
                        el = el.parentElement;
                    }
                    return null;
                })();
                if (!hockeyContainer) return [];

                // ALL puck-line (Handicap) odds inside the hockey container, in DOM order
                const plOdds = [
                    ...hockeyContainer.querySelectorAll(
                        '[class*="cpm-ParticipantOdds"][class*="gl-Participant_General"][class*="Handicap"]'
                    )
                ];

                // ALL non-handicap, non-totals odds (money-line candidates)
                const mlOdds = [
                    ...hockeyContainer.querySelectorAll(
                        '[class*="cpm-ParticipantOdds"][class*="gl-Participant_General"]'
                    )
                ].filter(el => !el.className.includes('Handicap') &&
                               !/^[OU]\\s/.test(el.textContent.trim()));

                // Helper: get price text from an odds element (prefer _Odds child)
                const priceText = (el) => {
                    const inner = el && el.querySelector('[class*="_Odds"]');
                    return (inner || el) ? (inner || el).textContent.trim() : '';
                };

                // Helper: get handicap text (puck-line value like "-1.5")
                const handicapText = (el) => {
                    const hEl = el && el.querySelector('[class*="_Handicap"]');
                    return hEl ? hEl.textContent.trim() : '';
                };

                const results = [];

                for (let i = 0; i < outerFixtures.length; i++) {
                    const fix = outerFixtures[i];

                    // Team names from _TeamContainer sub-elements
                    const teamEls = fix.querySelectorAll('[class*="_TeamContainer"]');
                    let home = '', away = '';
                    if (teamEls.length >= 2) {
                        home = teamEls[0].textContent.trim();
                        away = teamEls[1].textContent.trim();
                    } else {
                        // Fallback: strip time then split by capital boundary
                        const txt = fix.textContent.replace(/\\d+:\\d+\\s*(AM|PM).*/i, '').trim();
                        const m = txt.match(/^(.{3,25}?)([A-Z].{3,25})$/);
                        if (m) { home = m[1].trim(); away = m[2].trim(); }
                        else home = txt;
                    }
                    if (!home || !away) continue;

                    // ── Puck line ──────────────────────────────────────────────
                    const plHome = plOdds[i * 2];
                    const plAway = plOdds[i * 2 + 1];
                    if (plHome && plAway) {
                        results.push({
                            home, away,
                            homeOdds: priceText(plHome),
                            awayOdds: priceText(plAway),
                            homeHandicap: handicapText(plHome),
                            awayHandicap: handicapText(plAway),
                            market: 'spread',
                        });
                    }

                    // ── Money line (if available for this game) ────────────────
                    const mlHome = mlOdds[i * 2];
                    const mlAway = mlOdds[i * 2 + 1];
                    if (mlHome && mlAway) {
                        results.push({
                            home, away,
                            homeOdds: priceText(mlHome),
                            awayOdds: priceText(mlAway),
                            homeHandicap: '',
                            awayHandicap: '',
                            market: 'moneyline',
                        });
                    }
                }

                return results;
            }""")

            for ev in raw:
                home = ev.get("home", "").strip()
                away = ev.get("away", "").strip()
                if not home or not away:
                    continue

                home_odds = _parse_odds(ev.get("homeOdds", ""))
                away_odds = _parse_odds(ev.get("awayOdds", ""))
                if not home_odds or not away_odds:
                    continue

                sport = "nhl"
                market = ev.get("market", "moneyline")
                event_name = normalize_event_name(f"{home} vs {away}")

                records.append(OddsRecord(
                    book=self.BOOK_NAME,
                    sport=sport,
                    event_name=event_name,
                    event_start=now,
                    market=market,
                    outcome="home",
                    decimal_odds=home_odds,
                    scraped_at=now,
                ))
                records.append(OddsRecord(
                    book=self.BOOK_NAME,
                    sport=sport,
                    event_name=event_name,
                    event_start=now,
                    market=market,
                    outcome="away",
                    decimal_odds=away_odds,
                    scraped_at=now,
                ))

            logger.info("[%s] scraped %d records from %d raw events",
                        self.BOOK_NAME, len(records), len(raw))

        except Exception as e:
            logger.warning("%s scrape failed: %s", self.BOOK_NAME, e)
        finally:
            await context.close()

        return records
