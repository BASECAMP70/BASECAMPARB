import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product
from typing import List, Tuple, Dict, Optional

from scrapers.base import OddsRecord


@dataclass
class OpportunityLeg:
    outcome: str
    book: str
    decimal_odds: float
    recommended_stake: float
    participant: str = ""       # human-readable selection, e.g. "Edmonton Oilers -1.5"
    scraped_at: Optional[datetime] = None  # when this specific odd was fetched


@dataclass
class Opportunity:
    id: str
    sport: str
    event_name: str
    event_start: datetime
    market: str
    margin: float
    arb_sum: float
    outcomes: List[OpportunityLeg]
    detected_at: datetime
    updated_at: datetime


def _make_id(sport: str, event_name: str, market: str) -> str:
    raw = f"{sport}:{event_name}:{market}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def calculate_stakes(bankroll: float, legs: List[OpportunityLeg]) -> List[float]:
    """Return stake per leg so each returns bankroll + profit."""
    implied = [1 / leg.decimal_odds for leg in legs]
    arb_sum = sum(implied)
    return [round(bankroll * imp / arb_sum, 2) for imp in implied]


def _base_participant(participant: str) -> str:
    """Strip trailing handicap suffix (+1.5, -1.5) to get the canonical team name."""
    return re.sub(r'\s*[+-]\d+(?:\.\d+)?$', '', participant.strip())


def _handicap_sign(participant: str) -> Optional[str]:
    """Return '+' or '-' if participant has a handicap suffix, else None."""
    m = re.search(r'([+-])\d+(?:\.\d+)?$', participant.strip())
    return m.group(1) if m else None


def _find_best_combo(
    side_options: List[List[OddsRecord]],
    participants: List[str],
    require_different_teams: bool = False,
) -> Optional[Tuple]:
    """Return the first valid combo (best odds, all different books) or None.

    If require_different_teams is True (used for spread), also reject combos
    where two legs are for the same base team (e.g. CHI -1.5 vs CHI +1.5).
    """
    for combo in product(*side_options):
        books = [r.book for r in combo]
        if len(set(books)) < len(books):
            continue  # same book twice
        if require_different_teams:
            base_teams = [_base_participant(r.participant) for r in combo]
            if len(set(base_teams)) < len(base_teams):
                continue  # same team on both sides — not a real arb
        return combo
    return None


def detect_arbs(records: List[OddsRecord], min_margin: float = 0.005) -> List[Opportunity]:
    """Detect cross-book arb opportunities in a list of OddsRecords.

    Market-specific grouping strategies:
    - moneyline: group by canonical team name (avoids home/away label mismatch)
    - spread:    group by handicap SIGN (+ vs −) so we always pair a −1.5 leg
                 with a +1.5 leg, never two favorites against each other
    - totals:    group by outcome label (over / under)
    """
    now = datetime.now(timezone.utc)

    # Group by (sport, event_name, market)
    groups: Dict[tuple, List[OddsRecord]] = {}
    for r in records:
        key = (r.sport, r.event_name, r.market)
        groups.setdefault(key, []).append(r)

    opportunities = []

    for (sport, event_name, market), group in groups.items():

        # ── Build per-side options ───────────────────────────────────────────
        if market == "moneyline":
            # Group by canonical team name; draw kept as "Draw"
            by_side: Dict[str, List[OddsRecord]] = {}
            for r in group:
                base = _base_participant(r.participant) if r.participant else r.outcome
                by_side.setdefault(base, []).append(r)

            has_draw = "Draw" in by_side
            expected = 3 if has_draw else 2
            if len(by_side) != expected:
                continue
            participants = list(by_side.keys())

        elif market == "spread":
            # Group by handicap sign (+ vs −).
            # A valid arb always pairs one −1.5 leg with one +1.5 leg
            # for DIFFERENT teams (same-team -1.5/+1.5 is not an arb).
            neg_side = []
            pos_side = []
            for r in group:
                sign = _handicap_sign(r.participant) if r.participant else None
                if sign == '-':
                    neg_side.append(r)
                elif sign == '+':
                    pos_side.append(r)
            if not neg_side or not pos_side:
                continue
            by_side = {'-1.5': neg_side, '+1.5': pos_side}
            participants = ['-1.5', '+1.5']

        elif market == "totals":
            # Standard over/under labels are universal across books
            by_side = {}
            for r in group:
                by_side.setdefault(r.outcome, []).append(r)
            if not all(k in by_side for k in ("over", "under")):
                continue
            participants = ["over", "under"]

        else:
            continue

        # Sort each side by odds descending so product() tries best first
        for p in participants:
            by_side[p].sort(key=lambda r: r.decimal_odds, reverse=True)

        # ── Find the best valid combo (different books for every leg) ────────
        side_options = [by_side[p] for p in participants]
        combo = _find_best_combo(
            side_options, participants,
            require_different_teams=(market == "spread"),
        )
        if combo is None:
            continue

        odds_vals = [r.decimal_odds for r in combo]
        arb_sum = sum(1 / o for o in odds_vals)
        margin = 1 - arb_sum

        if arb_sum >= 1.0 or margin < min_margin:
            continue

        event_start = combo[0].event_start
        legs = [
            OpportunityLeg(
                outcome=participants[i],
                book=combo[i].book,
                decimal_odds=combo[i].decimal_odds,
                recommended_stake=0.0,
                participant=combo[i].participant,
                scraped_at=combo[i].scraped_at,
            )
            for i in range(len(participants))
        ]
        stakes = calculate_stakes(100.0, legs)
        for leg, stake in zip(legs, stakes):
            leg.recommended_stake = stake

        opp = Opportunity(
            id=_make_id(sport, event_name, market),
            sport=sport,
            event_name=event_name,
            event_start=event_start,
            market=market,
            margin=margin,
            arb_sum=arb_sum,
            outcomes=legs,
            detected_at=now,
            updated_at=now,
        )
        opportunities.append(opp)

    return opportunities


def diff_opportunities(
    prev: Dict[str, Opportunity],
    curr: Dict[str, Opportunity],
) -> Tuple[List[Opportunity], List[Opportunity], List[str]]:
    """Return (new, updated, expired_ids)."""
    new = [o for id_, o in curr.items() if id_ not in prev]
    updated = [
        o for id_, o in curr.items()
        if id_ in prev and (
            o.margin != prev[id_].margin or
            any(l.decimal_odds != pl.decimal_odds
                for l, pl in zip(o.outcomes, prev[id_].outcomes))
        )
    ]
    expired_ids = [id_ for id_ in prev if id_ not in curr]
    return new, updated, expired_ids
