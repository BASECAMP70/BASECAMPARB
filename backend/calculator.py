from dataclasses import dataclass, field
from datetime import datetime
from typing import List


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
