import json
import re
from pathlib import Path
from typing import Optional, Tuple

_TEAMS_PATH = Path(__file__).parent / "data" / "teams.json"
_teams: dict[str, str] = {}


def _load_teams() -> dict[str, str]:
    """Return a case-insensitive token -> canonical name lookup.

    Includes both the raw keys from teams.json and the canonical values
    (lowercased) mapped to themselves, so full team names like
    'Edmonton Oilers' resolve correctly.
    """
    global _teams
    if not _teams:
        data = json.loads(_TEAMS_PATH.read_text())
        raw: dict[str, str] = data["teams"]
        # Build lowercase key -> canonical value mapping
        lookup: dict[str, str] = {}
        for token, canonical in raw.items():
            lookup[token.lower()] = canonical
            # Also map the canonical name itself (lowercased) back to canonical
            lookup[canonical.lower()] = canonical
        _teams = lookup
    return _teams


_MARKET_MAP: dict[str, str] = {
    "moneyline": "moneyline",
    "match winner": "moneyline",
    "1x2": "moneyline",
    "totals": "totals",
    "over/under": "totals",
    "spread": "spread",
    "puck line": "spread",
    "run line": "spread",
}

_OUTCOME_MAP: dict[str, str] = {
    "home": "home",
    "away": "away",
    "draw": "draw",
    "over": "over",
    "under": "under",
    "1": "home",
    "2": "away",
    "x": "draw",
}


def normalize_event_name(raw: str) -> str:
    """Return canonical event name: 'Team A vs Team B' in alphabetical order."""
    teams = _load_teams()
    s = raw.strip().lower()
    # Normalize separators
    s = re.sub(r"\s+at\s+", " vs ", s)
    s = re.sub(r"\s+@\s+", " vs ", s)
    s = re.sub(r"\s+v\s+", " vs ", s)
    s = re.sub(r"\s+vs\.\s+", " vs ", s)
    parts = s.split(" vs ", 1)
    if len(parts) != 2:
        return s  # can't parse, return as-is
    token_a = parts[0].strip()
    token_b = parts[1].strip()
    # Look up each token using the lowercase key (tokens are already lowercased)
    team_a = teams.get(token_a, token_a)
    team_b = teams.get(token_b, token_b)
    # Alphabetical order
    pair = sorted([team_a, team_b])
    return f"{pair[0]} vs {pair[1]}"


def normalize_market_outcome(raw_market: str, raw_outcome: str) -> Optional[Tuple[str, str]]:
    """Return (canonical_market, canonical_outcome) or None if unrecognized."""
    market = _MARKET_MAP.get(raw_market.strip().lower())
    if market is None:
        return None
    outcome = _OUTCOME_MAP.get(raw_outcome.strip().lower())
    if outcome is None:
        return None
    return market, outcome
