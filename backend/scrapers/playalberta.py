"""
PlayAlberta.ca scraper.

DOM structure (verified via live Playwright inspection):
  Sport blocks:   .bto-sb-event-match
  Sport name:     .bto-sb-h4
  Market labels:  .bto-sb-market-label  e.g. "Money Line", "Spread", "Total" / "Home", "Draw", "Away"
  Game rows:      .bto-sb-event-item
  Home team:      .bto-sb-team-home .bto-sb-team-name
  Away team:      .bto-sb-team-away .bto-sb-team-name
  Game time:      .bto-sb-event-time
  Odds (decimal): .bto-sb-odd  (left-to-right, one per market column per team)
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import List

from playwright_stealth import stealth_async

from normalizer import normalize_event_name, normalize_market_outcome
from scrapers.base import OddsRecord, OddsScraper, UA_LIST

logger = logging.getLogger(__name__)

# Map PlayAlberta label text → (canonical_market, outcome_order)
# outcome_order is a list of canonical outcomes that correspond to the odds columns
_LABEL_MAP = {
    "money line": ("moneyline", ["home", "away"]),
    "ml":         ("moneyline", ["home", "away"]),
    "spread":     ("spread",    ["home", "away"]),
    "puck line":  ("spread",    ["home", "away"]),
    "total":      ("totals",    ["over", "under"]),
    "over/under": ("totals",    ["over", "under"]),
    "home":       ("moneyline", ["home"]),
    "draw":       ("moneyline", ["draw"]),
    "away":       ("moneyline", ["away"]),
}

# Map PlayAlberta sport header → canonical sport key
_SPORT_MAP = {
    "hockey": "nhl",
    "nhl": "nhl",
    "basketball": "nba",
    "nba": "nba",
    "football": "nfl",
    "nfl": "nfl",
    "baseball": "mlb",
    "mlb": "mlb",
    "soccer": "soccer",
    "mls": "mls",
}


class PlayAlbertaScraper(OddsScraper):
    BOOK_NAME = "playalberta"
    ODDS_URL = "https://www.playalberta.ca/sports"
    ODDS_CONTAINER_SELECTOR = ".bto-sb-event-match"

    async def fetch_odds(self) -> List[OddsRecord]:
        context = await self.browser.new_context(user_agent=random.choice(UA_LIST))
        await stealth_async(context)
        page = await context.new_page()
        records: List[OddsRecord] = []
        now = datetime.now(timezone.utc)

        try:
            await page.goto(self.ODDS_URL, wait_until="domcontentloaded", timeout=30_000)
            # Wait for sport blocks to appear
            await page.wait_for_selector(self.ODDS_CONTAINER_SELECTOR, timeout=20_000)
            await asyncio.sleep(random.uniform(2.0, 4.0))

            raw_events = await page.evaluate("""() => {
                const events = [];
                const sportBlocks = document.querySelectorAll('.bto-sb-event-match');

                for (const block of sportBlocks) {
                    const sportEl = block.querySelector('.bto-sb-h4');
                    const sport = sportEl ? sportEl.textContent.trim() : '';

                    // Market column labels for this block
                    const labels = [...block.querySelectorAll('.bto-sb-market-label')]
                        .map(el => el.textContent.trim().toLowerCase());

                    const rows = block.querySelectorAll('.bto-sb-event-item');
                    for (const row of rows) {
                        const homeEl = row.querySelector('.bto-sb-team-home .bto-sb-team-name');
                        const awayEl = row.querySelector('.bto-sb-team-away .bto-sb-team-name');
                        if (!homeEl || !awayEl) continue;

                        const home = homeEl.textContent.trim();
                        const away = awayEl.textContent.trim();
                        const timeEl = row.querySelector('.bto-sb-event-time');
                        const timeText = timeEl ? timeEl.textContent.trim() : '';

                        // All decimal odds in column order
                        const odds = [...row.querySelectorAll('.bto-sb-odd')]
                            .map(el => parseFloat(el.textContent.trim()))
                            .filter(n => !isNaN(n) && n > 1.0);

                        events.push({ sport, home, away, timeText, odds, labels });
                    }
                }
                return events;
            }""")

            for ev in raw_events:
                sport_raw = ev["sport"].lower()
                sport = _SPORT_MAP.get(sport_raw)
                # Try partial match if no exact hit
                if not sport:
                    for k, v in _SPORT_MAP.items():
                        if k in sport_raw:
                            sport = v
                            break
                if not sport:
                    sport = sport_raw or "unknown"

                home = ev["home"]
                away = ev["away"]
                event_name = normalize_event_name(f"{home} vs {away}")
                odds = ev["odds"]
                labels = ev["labels"]

                # Walk market columns; each label owns 1 or 2 odds slots.
                # Collect per-event records so we can post-process spread handicaps.
                ev_records: List[OddsRecord] = []
                odds_idx = 0
                for label in labels:
                    mapping = _LABEL_MAP.get(label)
                    if not mapping:
                        odds_idx += 1
                        continue
                    market, outcomes = mapping

                    for outcome in outcomes:
                        if odds_idx >= len(odds):
                            break
                        decimal_odds = odds[odds_idx]
                        odds_idx += 1

                        # Skip implausible spread odds — prevents totals-line values
                        # (e.g. 71.94 from a misaligned slot) from polluting spread records.
                        if market == "spread" and not (1.20 <= decimal_odds <= 5.00):
                            continue

                        # Build human-readable participant name
                        if outcome == "home":
                            participant = home
                        elif outcome == "away":
                            participant = away
                        elif outcome == "over":
                            participant = "Over"
                        elif outcome == "under":
                            participant = "Under"
                        else:
                            participant = outcome.capitalize()

                        ev_records.append(OddsRecord(
                            book=self.BOOK_NAME,
                            sport=sport,
                            event_name=event_name,
                            event_start=now,
                            market=market,
                            outcome=outcome,
                            decimal_odds=decimal_odds,
                            scraped_at=now,
                            participant=participant,
                        ))

                # ── Post-process: add +1.5 / -1.5 handicap to spread participant names ──
                # Infer handicap by comparing moneyline odds:
                #   home underdog (ML_home > ML_away)  → home gets +1.5, away gets -1.5
                #   home favourite (ML_home < ML_away) → home gets -1.5, away gets +1.5
                ml_home = next((r.decimal_odds for r in ev_records
                                if r.market == "moneyline" and r.outcome == "home"), None)
                ml_away = next((r.decimal_odds for r in ev_records
                                if r.market == "moneyline" and r.outcome == "away"), None)
                if ml_home and ml_away:
                    home_hcap = "+1.5" if ml_home > ml_away else "-1.5"
                    away_hcap = "-1.5" if ml_home > ml_away else "+1.5"
                    for r in ev_records:
                        if r.market == "spread":
                            if r.outcome == "home":
                                r.participant = f"{r.participant} {home_hcap}"
                            elif r.outcome == "away":
                                r.participant = f"{r.participant} {away_hcap}"

                records.extend(ev_records)

            logger.info("[%s] scraped %d records from %d events",
                        self.BOOK_NAME, len(records), len(raw_events))

        except Exception as e:
            logger.warning("%s scrape failed: %s", self.BOOK_NAME, e)
        finally:
            await context.close()

        return records
