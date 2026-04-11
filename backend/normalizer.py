import json
import logging
import re
from pathlib import Path
from typing import Optional, Tuple

from rapidfuzz import process as fuzz_process, fuzz

logger = logging.getLogger(__name__)

_TEAMS_PATH = Path(__file__).parent / "data" / "teams.json"
_teams: dict[str, str] = {}
_canonical_names: list[str] = []   # unique canonical values for fuzzy matching
_fuzzy_cache: dict[str, str] = {}  # lowercased token -> resolved canonical

_FUZZY_THRESHOLD = 80  # minimum score (0-100) to accept a fuzzy match


def _load_teams() -> dict[str, str]:
    """Return a case-insensitive token -> canonical name lookup."""
    global _teams, _canonical_names
    if not _teams:
        data = json.loads(_TEAMS_PATH.read_text())
        raw: dict[str, str] = data["teams"]
        lookup: dict[str, str] = {}
        canonicals: set[str] = set()
        for token, canonical in raw.items():
            lookup[token.lower()] = canonical
            lookup[canonical.lower()] = canonical
            canonicals.add(canonical)
        _teams = lookup
        _canonical_names = sorted(canonicals)
    return _teams


def _resolve_team(token: str) -> str:
    """Exact lookup first; fall back to RapidFuzz if no exact match found.

    token must already be lowercased.
    """
    teams = _load_teams()

    # 1. Exact (case-insensitive) lookup
    result = teams.get(token)
    if result:
        return result

    # 2. Fuzzy cache hit
    if token in _fuzzy_cache:
        return _fuzzy_cache[token]

    # 3. RapidFuzz against all canonical names
    match = fuzz_process.extractOne(
        token,
        _canonical_names,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=_FUZZY_THRESHOLD,
    )
    if match:
        canonical = match[0]
        logger.debug("Fuzzy match: %r -> %r (score=%s)", token, canonical, match[1])
        _fuzzy_cache[token] = canonical
        _teams[token] = canonical   # cache in exact lookup for next call
        return canonical

    # 4. No match — return token as-is (suppress repeated warnings via cache)
    _fuzzy_cache[token] = token  # cache so we don't warn again
    logger.debug("Unknown team token, no fuzzy match found: %r", token)
    return token


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
    s = raw.strip().lower()
    # Normalize separators
    s = re.sub(r"\s+at\s+", " vs ", s)
    s = re.sub(r"\s+@\s+", " vs ", s)
    s = re.sub(r"\s+[-–—]\s+", " vs ", s)   # handle "Home - Away" (Betway format)
    s = re.sub(r"\s+v\s+", " vs ", s)
    s = re.sub(r"\s+vs\.\s+", " vs ", s)
    parts = s.split(" vs ", 1)
    if len(parts) != 2:
        return s  # can't parse, return as-is
    token_a = parts[0].strip()
    token_b = parts[1].strip()
    team_a = _resolve_team(token_a)
    team_b = _resolve_team(token_b)
    pair = sorted([team_a, team_b])
    return f"{pair[0]} vs {pair[1]}"


def normalize_participant(raw: str) -> str:
    """Return a canonical participant label, preserving any trailing handicap suffix.

    E.g. "OTT Senators -1.5"  -> "Ottawa Senators -1.5"
         "VAN Canucks +1.5"   -> "Vancouver Canucks +1.5"
         "NAS Predators"       -> "Nashville Predators"
    """
    raw = raw.strip()
    # Split off a trailing handicap like "-1.5", "+1.5", "(-1.5)", "(+1.5)"
    m = re.match(r"^(.*?)\s*(\()?([+-]\d+(?:\.\d+)?)\)?$", raw)
    if m:
        team_part = m.group(1).strip()
        handicap = m.group(3)
        resolved = _resolve_team(team_part.lower())
        return f"{resolved} {handicap}"
    else:
        return _resolve_team(raw.lower())


def normalize_market_outcome(raw_market: str, raw_outcome: str) -> Optional[Tuple[str, str]]:
    """Return (canonical_market, canonical_outcome) or None if unrecognized."""
    market = _MARKET_MAP.get(raw_market.strip().lower())
    if market is None:
        return None
    outcome = _OUTCOME_MAP.get(raw_outcome.strip().lower())
    if outcome is None:
        return None
    return market, outcome
