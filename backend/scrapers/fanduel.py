"""
FanDuel scraper.

NOTE: Live URL inspection (March 2024) confirms FanDuel does NOT operate in Alberta:
  - fanduel.com/sports/hockey → 404
  - fanduel.ca → DNS not found
  - can.fanduel.com → SSL error

FanDuel is licensed in Ontario only (via FanDuel Group Canada).  They do not hold an
Alberta Gaming, Liquor and Cannabis (AGLC) licence.  This scraper returns an empty list.

If FanDuel ever launches in Alberta, the expected URL pattern is:
  https://sportsbook.fanduel.com  (with geolocation AB)
DOM selectors would use FanDuel's React structure:
  Event containers: '[class*="EventCell"]'
  Team names:       '[class*="ParticipantName"]'
  Odds buttons:     '[class*="OddsButton"]'
"""

import logging
from typing import List

from scrapers.base import OddsRecord, OddsScraper

logger = logging.getLogger(__name__)


class FanDuelScraper(OddsScraper):
    BOOK_NAME = "fanduel"
    ODDS_URL = ""  # Not available in Alberta

    async def fetch_odds(self) -> List[OddsRecord]:
        logger.debug(
            "[fanduel] Skipped — FanDuel is not licensed in Alberta (Ontario only)."
        )
        return []
