import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import List

from playwright_stealth import stealth_async

from normalizer import normalize_event_name, normalize_market_outcome
from scrapers.base import OddsRecord, OddsScraper, UA_LIST

logger = logging.getLogger(__name__)


class BetMGMScraper(OddsScraper):
    BOOK_NAME = "betmgm"
    ODDS_URL = "https://sports.on.betmgm.ca/en/sports"
    ODDS_CONTAINER_SELECTOR = ".sports-event-list"  # UPDATE after inspection

    async def fetch_odds(self) -> List[OddsRecord]:
        context = await self.browser.new_context(user_agent=random.choice(UA_LIST))
        await stealth_async(context)
        page = await context.new_page()
        records: List[OddsRecord] = []
        try:
            await page.goto(self.ODDS_URL, wait_until="networkidle", timeout=30_000)
            await page.wait_for_selector(self.ODDS_CONTAINER_SELECTOR, timeout=15_000)
            await asyncio.sleep(random.uniform(0.8, 2.5))
            # TODO: implement extraction after live inspection
        except Exception as e:
            logger.warning("%s scrape failed: %s", self.BOOK_NAME, e)
            raise
        finally:
            await context.close()
        return records
