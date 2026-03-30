"""Probable prediction market scraper via PMXT SDK."""
from scrapers.pmxt_base import PmxtScraper


class ProbableScraper(PmxtScraper):
    BOOK_NAME = "probable"

    def _make_exchange(self):
        import pmxt
        return pmxt.Probable()
