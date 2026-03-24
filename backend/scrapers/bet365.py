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
    # Alternate path appended to whatever domain bet365 redirects to
    NHL_PATH = "/en/sports/ice-hockey/nhl/"
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
            # bet365.ca redirects to a regional domain (e.g. on.bet365.ca) but lands
            # on the correct NHL page — the URL will contain "Ice_Hockey" in the hash.
            # We do NOT attempt a second navigation; the redirect destination is correct.
            await page.goto(self.ODDS_URL, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(random.uniform(2.0, 3.0))

            await page.wait_for_selector(self.ODDS_CONTAINER_SELECTOR, timeout=20_000)
            await asyncio.sleep(random.uniform(2.0, 3.5))

            raw = await page.evaluate("""() => {
                // ── Strategy ────────────────────────────────────────────────────
                // bet365 NHL page layout (after regional redirect):
                //
                //  Multiple gl-MarketGroupContainer blocks stacked on the page.
                //  We look for the Money Line group first (by its header label),
                //  then fall back to any container that has non-Handicap participant
                //  odds (2 per fixture = home + away money-line prices).
                //
                //  Fixture rows: cpm-ParticipantFixtureDetailsIceHockey + rcl-Market
                //  ML odds:      cpm-ParticipantOdds gl-Participant_General   (no Handicap class)

                const FIXTURE_SEL = '[class*="cpm-ParticipantFixtureDetailsIceHockey"][class*="rcl-Market"]';
                const ML_ODDS_SEL  = '[class*="cpm-ParticipantOdds"][class*="gl-Participant_General"]:not([class*="Handicap"])';

                const priceText = (el) => {
                    const inner = el && el.querySelector('[class*="_Odds"]');
                    return (inner || el) ? (inner || el).textContent.trim() : '';
                };
                const getTeams = (fix) => {
                    const teamEls = fix.querySelectorAll('[class*="_TeamContainer"]');
                    if (teamEls.length >= 2)
                        return [teamEls[0].textContent.trim(), teamEls[1].textContent.trim()];
                    const txt = fix.textContent.replace(/\\d+:\\d+\\s*(AM|PM).*/i, '').trim();
                    const m = txt.match(/^(.{3,25}?)([A-Z].{3,25})$/);
                    return m ? [m[1].trim(), m[2].trim()] : [txt, ''];
                };

                const outerFixtures = [...document.querySelectorAll(FIXTURE_SEL)];
                if (!outerFixtures.length) return [];
                const fc = outerFixtures.length;

                // ── Find a money-line market group container ──────────────────
                const allContainers = [...document.querySelectorAll('[class*="gl-MarketGroupContainer"]')];

                let mlContainer = null;

                // 1) Look for a container whose header says "Money Line"
                for (const c of allContainers) {
                    const lbl = c.querySelector('[class*="gl-MarketGroupLabel"], [class*="gl-Market_HeaderLabel"]');
                    if (lbl && lbl.textContent.toLowerCase().includes('money line')) {
                        mlContainer = c;
                        break;
                    }
                }

                // 2) Fallback: any container with enough non-Handicap participant odds
                if (!mlContainer) {
                    for (const c of allContainers) {
                        const odds = c.querySelectorAll(ML_ODDS_SEL);
                        if (odds.length >= fc * 2) { mlContainer = c; break; }
                    }
                }

                if (!mlContainer) return [];

                const mlOdds = [...mlContainer.querySelectorAll(ML_ODDS_SEL)].slice(0, fc * 2);
                if (mlOdds.length < fc * 2) return [];

                const results = [];
                for (let i = 0; i < fc; i++) {
                    const [home, away] = getTeams(outerFixtures[i]);
                    if (!home || !away) continue;
                    results.push({
                        home, away,
                        homeOdds: priceText(mlOdds[i * 2]),
                        awayOdds: priceText(mlOdds[i * 2 + 1]),
                        homeHandicap: '',
                        awayHandicap: '',
                        market: 'moneyline',
                    });
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

                # Build participant labels (include handicap line for spread)
                home_hcap = ev.get("homeHandicap", "").strip()
                away_hcap = ev.get("awayHandicap", "").strip()
                home_participant = f"{home} {home_hcap}".strip() if home_hcap else home
                away_participant = f"{away} {away_hcap}".strip() if away_hcap else away

                records.append(OddsRecord(
                    book=self.BOOK_NAME,
                    sport=sport,
                    event_name=event_name,
                    event_start=now,
                    market=market,
                    outcome="home",
                    decimal_odds=home_odds,
                    scraped_at=now,
                    participant=home_participant,
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
                    participant=away_participant,
                ))

            logger.info("[%s] scraped %d records from %d raw events",
                        self.BOOK_NAME, len(records), len(raw))

        except Exception as e:
            logger.warning("%s scrape failed: %s", self.BOOK_NAME, e)
        finally:
            await context.close()

        return records
