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
# outcome_order is a list of canonical outcomes that correspond to the odds columns.
# Spread/puck-line/total are kept here so the odds-index counter advances correctly
# even though we only emit moneyline records.
_LABEL_MAP = {
    "money line": ("moneyline", ["home", "away"]),   # order overridden at runtime for "@" games
    "ml":         ("moneyline", ["home", "away"]),
    "spread":     ("spread",    ["home", "away"]),
    "puck line":  ("spread",    ["home", "away"]),
    "run line":   ("spread",    ["home", "away"]),
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
        page = await context.new_page()
        await stealth_async(page)
        records: List[OddsRecord] = []
        now = datetime.now(timezone.utc)

        try:
            await page.goto(self.ODDS_URL, wait_until="domcontentloaded", timeout=25_000)
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

                        const cssFirst  = homeEl.textContent.trim();
                        const cssSecond = awayEl.textContent.trim();
                        const sepEl = row.querySelector('.bto-sb-team-separator');
                        const separator = sepEl ? sepEl.textContent.trim() : '';
                        const timeEl = row.querySelector('.bto-sb-event-time');
                        const timeText = timeEl ? timeEl.textContent.trim() : '';

                        // Parse each .bto-sb-odd cell:
                        //   1-span cell: pure decimal odds (moneyline or totals)
                        //               → { price: 2.05, handicap: null }
                        //   2-span cell: handicap line + odds (spread)
                        //               → { price: 1.94, handicap: "-1.5" }
                        //   anything else: null (position kept for index alignment)
                        const parseOdd = el => {
                            const spans = el.querySelectorAll('span');
                            if (spans.length === 1) {
                                const m = spans[0].textContent.trim().match(/^(\d+\.\d+)$/);
                                return m ? { price: parseFloat(m[1]), handicap: null } : null;
                            }
                            if (spans.length === 2) {
                                const hcap = spans[0].textContent.trim();
                                const m = spans[1].textContent.trim().match(/^(\d+\.\d+)$/);
                                return m ? { price: parseFloat(m[1]), handicap: hcap } : null;
                            }
                            return null;
                        };
                        const odds = [...row.querySelectorAll('.bto-sb-odd')].map(el => parseOdd(el));

                        // Extract per-game deep link (e.g. /sports/hockey/nhl/dal-stars-@-ny-islanders/sm-2343314)
                        const eventLink = row.querySelector('a[href*="/sports/"]');
                        const eventPath = eventLink ? eventLink.getAttribute('href') : '';
                        const eventUrl = eventPath ? 'https://playalberta.ca' + eventPath : '';

                        events.push({ sport, cssFirst, cssSecond, separator, timeText, odds, labels, eventUrl });
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

                # PlayAlberta uses "Away @ Home" for North American sports:
                #   .bto-sb-team-home (cssFirst)  = the AWAY team displayed first
                #   .bto-sb-team-away (cssSecond) = the HOME team displayed second
                # For soccer "vs" games the order is conventional (home first).
                separator = ev.get("separator", "")
                css_first  = ev["cssFirst"]
                css_second = ev["cssSecond"]
                if separator == "@":
                    home = css_second   # second displayed = actual home
                    away = css_first    # first displayed  = actual away
                    # Odds array is in display order: away-team odds first
                    ml_outcomes = ["away", "home"]
                else:
                    home = css_first
                    away = css_second
                    ml_outcomes = ["home", "away"]

                event_name = normalize_event_name(f"{home} vs {away}")
                odds = ev["odds"]
                labels = ev["labels"]
                event_url = ev.get("eventUrl", "")

                # Walk market columns; each label owns 1 or 2 odds slots.
                # Spread and moneyline follow team display order (ml_outcomes).
                # Totals always use ["over", "under"] order.
                ev_records: List[OddsRecord] = []
                odds_idx = 0
                for label in labels:
                    mapping = _LABEL_MAP.get(label)
                    if not mapping:
                        odds_idx += 1
                        continue
                    market, outcomes = mapping

                    # Moneyline and spread both follow the separator-aware display order
                    if market in ("moneyline", "spread") and label in ("money line", "ml", "spread", "puck line", "run line"):
                        outcomes = ml_outcomes

                    for outcome in outcomes:
                        if odds_idx >= len(odds):
                            break
                        cell = odds[odds_idx]
                        odds_idx += 1

                        if cell is None:
                            continue
                        decimal_odds = cell.get("price", 0)
                        handicap = cell.get("handicap")
                        if not decimal_odds or decimal_odds <= 1.0:
                            continue

                        # Build human-readable participant name
                        if market == "spread":
                            base = home if outcome == "home" else away
                            participant = f"{base} {handicap}" if handicap else base
                        elif outcome == "home":
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
                            event_url=event_url,
                        ))

                records.extend(ev_records)

            logger.info("[%s] scraped %d records from %d events",
                        self.BOOK_NAME, len(records), len(raw_events))

        except Exception as e:
            logger.warning("%s scrape failed: %s", self.BOOK_NAME, e)
        finally:
            try:
                await asyncio.wait_for(context.close(), timeout=5)
            except Exception:
                pass

        return records
