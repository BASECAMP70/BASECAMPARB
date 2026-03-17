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
    """Parse an odds string to decimal float.  Handles decimal or American format."""
    text = text.strip()
    # Decimal: "2.05", "1.87"
    m = re.match(r'^(\d+\.\d+)$', text)
    if m:
        return float(m.group(1))
    # American: "+165", "-200", "EVS", "1/1"
    m = re.match(r'^([+-]?\d+)$', text)
    if m:
        return _american_to_decimal(float(m.group(1)))
    # Fractional: "4/5"
    m = re.match(r'^(\d+)/(\d+)$', text)
    if m:
        num, den = float(m.group(1)), float(m.group(2))
        return round(num / den + 1, 4)
    return None


class Bet365Scraper(OddsScraper):
    BOOK_NAME = "bet365"
    # Direct URL for NHL money-line listing
    ODDS_URL = "https://www.bet365.ca/en/sports/ice-hockey/"
    ODDS_CONTAINER_SELECTOR = '[class*="cpm-ParticipantFixtureDetailsIceHockey"]'

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
                const results = [];

                // Each market group contains fixtures + their odds for one market type
                const marketGroups = document.querySelectorAll('[class*="gl-MarketGroup"]');

                for (const group of marketGroups) {
                    // Get market label from header element
                    const headerEl = group.querySelector(
                        '[class*="gl-MarketGroupLabel"], [class*="MarketGroupLabel"], ' +
                        '[class*="MarketGroupHeader"], [class*="cpm-CouponHeader"]'
                    );
                    const marketLabel = headerEl ? headerEl.textContent.trim().toLowerCase() : '';

                    // Only extract money line (the default NHL view)
                    // Skip explicit spread/totals groups
                    if (marketLabel && (marketLabel.includes('spread') ||
                        marketLabel.includes('puck line') ||
                        marketLabel.includes('total') ||
                        marketLabel.includes('over/under'))) {
                        continue;
                    }

                    // Fixture rows within this group
                    const fixtures = group.querySelectorAll('[class*="cpm-ParticipantFixtureDetailsIceHockey"]');

                    for (const fixture of fixtures) {
                        // Extract home/away team names
                        // Bet365 has team name elements or concatenated text
                        const teamEls = fixture.querySelectorAll('[class*="Participant_Name"], [class*="TeamName"]');
                        let home = '', away = '';
                        if (teamEls.length >= 2) {
                            home = teamEls[0].textContent.trim();
                            away = teamEls[1].textContent.trim();
                        } else {
                            // Fall back: split raw text (teams concatenated without separator)
                            // pattern: the fixture shows "Team ATeam B HH:MM PM N" where N = num markets
                            const rawText = fixture.textContent.trim();
                            // Remove trailing time and market count
                            const cleaned = rawText.replace(/\\d+:\\d+\\s*(AM|PM).*$/, '').trim();
                            // Try to split at capital letter boundaries between two team names
                            const match = cleaned.match(/^(.+?)([A-Z][a-z].*[a-z])$/);
                            if (match) {
                                home = match[1].trim();
                                away = match[2].trim();
                            } else {
                                home = cleaned;
                                away = '';
                            }
                        }

                        if (!home) continue;

                        // Find the sibling odds buttons for this fixture
                        // Bet365 odds buttons have class patterns like:
                        //   cpm-ParticipantOdds gl-Participant_General cpm-ParticipantOdds_Odds_Left
                        //   cpm-ParticipantOdds gl-Participant_General cpm-ParticipantOdds_Odds_Right
                        // Walk up from fixture to find the parent row, then find odds siblings
                        let container = fixture.parentElement;
                        for (let i = 0; i < 4 && container; i++) {
                            const oddsEls = container.querySelectorAll(
                                '[class*="cpm-ParticipantOdds"][class*="gl-Participant_General"]'
                            );
                            if (oddsEls.length >= 2) {
                                // Get odds text (decimal or American) from each button
                                const getOdds = (el) => {
                                    // Look for inner span with the price value
                                    const span = el.querySelector('span, [class*="OddsLabel"], [class*="Price"]');
                                    return span ? span.textContent.trim() : el.textContent.trim();
                                };
                                const homeOddsText = getOdds(oddsEls[0]);
                                const awayOddsText = getOdds(oddsEls[1]);
                                results.push({
                                    home, away,
                                    homeOdds: homeOddsText,
                                    awayOdds: awayOddsText,
                                    marketLabel
                                });
                                break;
                            }
                            container = container.parentElement;
                        }
                    }
                }

                // Fallback: if market groups yielded nothing, try a simpler approach
                // by finding all fixture rows and pairing with adjacent odds
                if (results.length === 0) {
                    const allFixtures = document.querySelectorAll(
                        '[class*="cpm-ParticipantFixtureDetailsIceHockey"]'
                    );
                    for (const fixture of allFixtures) {
                        const rawText = fixture.textContent.trim();
                        // Look for sibling elements with decimal odds near this fixture
                        const parent = fixture.parentElement;
                        if (!parent) continue;
                        const oddsEls = parent.querySelectorAll(
                            '[class*="cpm-ParticipantOdds"], [class*="gl-Participant"]'
                        );
                        if (oddsEls.length < 2) continue;

                        const teamEls = fixture.querySelectorAll('[class*="Name"]');
                        let home = '', away = '';
                        if (teamEls.length >= 2) {
                            home = teamEls[0].textContent.trim();
                            away = teamEls[1].textContent.trim();
                        } else {
                            const parts = rawText.split(/\\n/).map(s => s.trim()).filter(Boolean);
                            home = parts[0] || '';
                            away = parts[1] || '';
                        }
                        results.push({
                            home, away,
                            homeOdds: oddsEls[0].textContent.trim(),
                            awayOdds: oddsEls[1].textContent.trim(),
                            marketLabel: 'moneyline'
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

                # Determine sport (this scraper targets ice-hockey URL)
                sport = "nhl"

                event_name = normalize_event_name(f"{home} vs {away}")

                records.append(OddsRecord(
                    book=self.BOOK_NAME,
                    sport=sport,
                    event_name=event_name,
                    event_start=now,
                    market="moneyline",
                    outcome="home",
                    decimal_odds=home_odds,
                    scraped_at=now,
                ))
                records.append(OddsRecord(
                    book=self.BOOK_NAME,
                    sport=sport,
                    event_name=event_name,
                    event_start=now,
                    market="moneyline",
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
