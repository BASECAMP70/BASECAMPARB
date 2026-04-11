"""Opinion prediction market scraper via PMXT SDK."""
from scrapers.pmxt_base import PmxtScraper


class OpinionScraper(PmxtScraper):
    BOOK_NAME = "opinion"

    def _make_exchange(self):
        import pmxt
        return pmxt.Opinion()
