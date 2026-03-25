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
    # Initial URL — bet365.ca redirects to a regional SPA (e.g. on.bet365.ca/#/HO/)
    ODDS_URL = "https://www.bet365.ca/en/sports/ice-hockey/nhl/"
    # After the initial redirect lands, navigate to the full NHL competition listing.
    # 18000083 is the stable bet365 competition ID for the NHL.
    NHL_HASH = "#/HH/18000083/"
    # Wait for the first NHL fixture to appear
    ODDS_CONTAINER_SELECTOR = '[class*="cpm-ParticipantFixtureDetailsIceHockey"]:not([class*="Hidden"])'

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
            # Step 1: navigate to get the regional domain (e.g. on.bet365.ca)
            await page.goto(self.ODDS_URL, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(random.uniform(1.5, 2.5))

            # Step 2: navigate to the full NHL competition page on the resolved domain.
            # The homepage (#/HO/) only shows a 2-game spotlight; #/HH/18000083/ shows
            # the complete upcoming NHL schedule with Spread / Total / Money columns.
            base_url = page.url.split("#")[0]
            await page.goto(base_url + self.NHL_HASH, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(random.uniform(1.5, 2.5))

            await page.wait_for_selector(self.ODDS_CONTAINER_SELECTOR, timeout=20_000)
            await asyncio.sleep(random.uniform(1.5, 2.5))

            raw = await page.evaluate("""() => {
                // ── DOM structure (verified 2025-03-25) ─────────────────────────
                // gl-MarketGroupContainer
                //   cpm-MarketFixture  (fixture column — team names)
                //     cpm-ParticipantFixtureDetailsIceHockey           (visible)
                //     cpm-ParticipantFixtureDetailsIceHockey Hidden    (skip)
                //     ...
                //   cpm-MarketOdds  (Spread column)
                //     cpm-MarketOddsHeader  "Spread"
                //     cpm-ParticipantOdds gl-Participant_General cpm-ParticipantHandicap50 ...
                //   cpm-MarketOdds  (Total column)
                //     cpm-MarketOddsHeader  "Total"
                //     cpm-ParticipantOdds gl-Participant_General cpm-ParticipantHandicap50 ...
                //   cpm-MarketOdds  (Money column)
                //     cpm-MarketOddsHeader  "Money"
                //     cpm-ParticipantOdds gl-Participant_General cpm-ParticipantHandicap50 ...
                //     NOTE: ALL odds buttons (Spread, Total, Money) carry the cpm-ParticipantHandicap50
                //     class for styling.  We scope to moneyCol so no :not(Handicap) filter is needed.
                //
                // Team name:  .cpm-ParticipantFixtureDetailsIceHockey_Team  (exact class token)
                // Odds text:  inner span  .cpm-ParticipantOdds_Odds

                const FIXTURE_SEL = '[class*="cpm-ParticipantFixtureDetailsIceHockey"]:not([class*="Hidden"])';
                // All participant odds buttons inside the Money column (scoped, so no Handicap filter needed)
                const ML_ODDS_SEL  = '[class*="cpm-ParticipantOdds"][class*="gl-Participant_General"]';

                const oddsText = (el) => {
                    const span = el && el.querySelector('[class*="cpm-ParticipantOdds_Odds"]');
                    return (span || el) ? (span || el).textContent.trim() : '';
                };

                const results = [];
                const containers = document.querySelectorAll('[class*="gl-MarketGroupContainer"]');

                for (const container of containers) {
                    // Non-Hidden NHL fixture rows inside this container
                    const fixRows = [...container.querySelectorAll(FIXTURE_SEL)];
                    if (!fixRows.length) continue;

                    // Find the "Money" market odds column (direct child/descendant cpm-MarketOdds
                    // whose cpm-MarketOddsHeader says "Money")
                    const oddsColumns = container.querySelectorAll('[class*="cpm-MarketOdds"]');
                    let moneyCol = null;
                    for (const col of oddsColumns) {
                        const hdr = col.querySelector('[class*="cpm-MarketOddsHeader"]');
                        if (hdr && /money/i.test(hdr.textContent)) {
                            moneyCol = col;
                            break;
                        }
                    }
                    if (!moneyCol) continue;

                    // All odds buttons inside the Money column
                    const mlOdds = [...moneyCol.querySelectorAll(ML_ODDS_SEL)];
                    const gameCount = Math.floor(mlOdds.length / 2);
                    if (!gameCount) continue;

                    // The spotlight section repeats the same game fixture element for each
                    // sub-market (period betting, props, etc.).  Collect unique game pairs
                    // (first occurrence of each home+away team combination) to align with
                    // the money-line odds that are ordered per game.
                    const seen = new Set();
                    const uniqueGames = [];
                    for (const fix of fixRows) {
                        const teamEls = fix.querySelectorAll('.cpm-ParticipantFixtureDetailsIceHockey_Team');
                        if (teamEls.length < 2) continue;
                        const home = teamEls[0].textContent.trim();
                        const away = teamEls[1].textContent.trim();
                        if (!home || !away) continue;
                        const key = home + '|' + away;
                        if (!seen.has(key)) {
                            seen.add(key);
                            uniqueGames.push({ home, away });
                        }
                        if (uniqueGames.length >= gameCount) break;
                    }

                    for (let i = 0; i < uniqueGames.length; i++) {
                        const { home, away } = uniqueGames[i];
                        results.push({
                            home, away,
                            homeOdds: oddsText(mlOdds[i * 2]),
                            awayOdds: oddsText(mlOdds[i * 2 + 1]),
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
