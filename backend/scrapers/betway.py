"""
Betway scraper.

NOTE: Live URL inspection (March 2024) confirms Betway Canada (betway.ca) is
Ontario-only.  The site displays: "It looks like you may be outside of Ontario.
If you are in Ontario, please continue here on betway.ca"

Betway holds an iGaming Ontario licence but does not hold an AGLC (Alberta) licence.
This scraper returns an empty list.

If Betway ever launches in Alberta, implement using their React/AngularJS DOM:
  Event rows:  '[class*="event-item"]' or '.bw-EventDisplay'
  Teams:       '.bw-EventDisplay_Team' or '[class*="Participant"]'
  Odds:        '.bw-EventDisplay_OddsLabel' or '[class*="PriceButton"]'
"""

import logging
from typing import List

from scrapers.base import OddsRecord, OddsScraper

logger = logging.getLogger(__name__)


class BetwayScraper(OddsScraper):
    BOOK_NAME = "betway"
    ODDS_URL = ""  # Not available in Alberta (Ontario licence only)

    async def fetch_odds(self) -> List[OddsRecord]:
        logger.debug(
            "[betway] Skipped — Betway Canada (betway.ca) is Ontario-only. "
            "No Alberta AGLC licence."
        )
        return []
