import hashlib
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


def detect_arbs(records: List[OddsRecord], min_margin: float = 0.005) -> List[Opportunity]:
    """Detect cross-book arb opportunities in a list of OddsRecords."""
    now = datetime.now(timezone.utc)

    # Group by (sport, event_name, market)
    groups: Dict[tuple, List[OddsRecord]] = {}
    for r in records:
        key = (r.sport, r.event_name, r.market)
        groups.setdefault(key, []).append(r)

    opportunities = []

    for (sport, event_name, market), group in groups.items():
        # Determine expected outcomes for this market
        if market == "moneyline":
            # Check if draw outcome exists → 3-way; else 2-way
            has_draw = any(r.outcome == "draw" for r in group)
            expected_outcomes = ["home", "draw", "away"] if has_draw else ["home", "away"]
        elif market == "totals":
            expected_outcomes = ["over", "under"]
        elif market == "spread":
            expected_outcomes = ["home", "away"]
        else:
            continue

        # Best odds per outcome per book
        best_per_outcome: Dict[str, List[Tuple[str, float]]] = {}
        for r in group:
            if r.outcome not in expected_outcomes:
                continue
            entry = best_per_outcome.setdefault(r.outcome, [])
            entry.append((r.book, r.decimal_odds))

        # Ensure all expected outcomes have at least one record
        if not all(o in best_per_outcome for o in expected_outcomes):
            continue

        # Sort each outcome's options by odds descending
        for outcome in expected_outcomes:
            best_per_outcome[outcome].sort(key=lambda x: x[1], reverse=True)

        # Try combinations: for each outcome, pick from available (book, odds)
        outcome_options = [best_per_outcome[o] for o in expected_outcomes]

        for combo in product(*outcome_options):
            # combo: ((book, odds), (book, odds), ...)
            books = [c[0] for c in combo]
            if len(set(books)) < len(books):
                continue  # duplicate book — skip

            odds_vals = [c[1] for c in combo]
            arb_sum = sum(1 / o for o in odds_vals)
            margin = 1 - arb_sum

            if arb_sum < 1.0 and margin >= min_margin:
                # Find event_start from first matching record
                event_start = next(
                    r.event_start for r in group if r.outcome == expected_outcomes[0]
                )

                # Build legs
                legs = [
                    OpportunityLeg(
                        outcome=expected_outcomes[i],
                        book=combo[i][0],
                        decimal_odds=combo[i][1],
                        recommended_stake=0.0,
                    )
                    for i in range(len(expected_outcomes))
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
                break  # take the best valid combo for this market group

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
