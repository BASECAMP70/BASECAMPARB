"""
BetMGM scraper.

NOTE: Live URL inspection (March 2024) shows BetMGM redirects all Canadian traffic to a
US geo-selector page ("Where are you playing from?") listing only US states (Arizona,
Colorado, Illinois, Indiana, Iowa, ...).  sports.ab.betmgm.ca does not resolve.
BetMGM operates in Ontario (sports.on.betmgm.ca) but there is no confirmed Alberta URL.

Until an Alberta-specific URL is identified, this scraper returns an empty list.

When an Alberta URL is confirmed, replace ODDS_URL and implement DOM extraction using
GVC / Roar Digital (Kambi-based) selectors:
  Event rows:  '.KambiBC-event-item'
  Teams:       '.KambiBC-bet-offer__participant'
  Odds:        '.KambiBC-outcome__odds'
"""

import logging
from typing import List

from scrapers.base import OddsRecord, OddsScraper

logger = logging.getLogger(__name__)


class BetMGMScraper(OddsScraper):
    BOOK_NAME = "betmgm"
    ODDS_URL = ""  # Not yet confirmed for Alberta

    async def fetch_odds(self) -> List[OddsRecord]:
        logger.debug(
            "[betmgm] Skipped — no confirmed Alberta URL. "
            "BetMGM redirects CA traffic to a US geo-selector."
        )
        return []
