import os
from dotenv import load_dotenv

load_dotenv()

SCRAPE_INTERVAL_SECONDS = int(os.getenv("SCRAPE_INTERVAL_SECONDS", "45"))
MIN_ARB_MARGIN = float(os.getenv("MIN_ARB_MARGIN", "0.005"))
ODDS_STALE_SECONDS = int(os.getenv("ODDS_STALE_SECONDS", "180"))
ODDS_EVICT_SECONDS = int(os.getenv("ODDS_EVICT_SECONDS", "600"))
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "http://localhost:5173")
