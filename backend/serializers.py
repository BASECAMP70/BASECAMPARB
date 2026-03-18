from calculator import Opportunity
from typing import Dict, Any


def serialize_opportunity(o: Opportunity) -> Dict[str, Any]:
    return {
        "id": o.id,
        "sport": o.sport,
        "event_name": o.event_name,
        "event_start": o.event_start.isoformat(),
        "market": o.market,
        "margin": o.margin,
        "arb_sum": o.arb_sum,
        "detected_at": o.detected_at.isoformat(),
        "updated_at": o.updated_at.isoformat(),
        "outcomes": [
            {
                "outcome": leg.outcome,
                "book": leg.book,
                "decimal_odds": leg.decimal_odds,
                "recommended_stake": leg.recommended_stake,
                "participant": leg.participant,
                "scraped_at": leg.scraped_at.isoformat() if leg.scraped_at else None,
            }
            for leg in o.outcomes
        ],
    }
