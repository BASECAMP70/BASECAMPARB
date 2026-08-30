"""Myriad prediction market scraper via PMXT SDK."""
from scrapers.pmxt_base import PmxtScraper


class MyriadScraper(PmxtScraper):
    BOOK_NAME = "myriad"

    def _make_exchange(self):
        import pmxt
        return pmxt.Myriad()
