"""Kalshi prediction market scraper via PMXT SDK."""
import os

from scrapers.pmxt_base import PmxtScraper


class KalshiScraper(PmxtScraper):
    BOOK_NAME = "kalshi"

    def _make_exchange(self):
        import pmxt
        api_key = os.getenv("KALSHI_API_KEY")
        private_key = os.getenv("KALSHI_PRIVATE_KEY")
        if not api_key or not private_key:
            raise RuntimeError(
                "KALSHI_API_KEY and KALSHI_PRIVATE_KEY env vars are required"
            )
        return pmxt.Kalshi(api_key=api_key, private_key=private_key)
