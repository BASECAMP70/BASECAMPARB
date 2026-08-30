"""Limitless prediction market scraper via PMXT SDK."""
from scrapers.pmxt_base import PmxtScraper


class LimitlessScraper(PmxtScraper):
    BOOK_NAME = "limitless"

    def _make_exchange(self):
        import pmxt
        return pmxt.Limitless()
