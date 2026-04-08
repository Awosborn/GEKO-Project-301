"""Shared constants and helpers for bidding-rule infractions and penalties."""

from __future__ import annotations

from typing import Dict

# Major infractions should dominate reward and analytics weighting.
STRAT_BREAK_PENALTY = 250
ACBL_BREAK_PENALTY = 400

MAJOR_INFRACTION_PENALTIES: Dict[str, int] = {
    "strategy_mismatch": STRAT_BREAK_PENALTY,
    "acbl_chart_violation": ACBL_BREAK_PENALTY,
}


def penalty_for_rule(rule_type: str) -> int:
    """Return configured penalty for a rule type; unknown types default to zero."""
    return int(MAJOR_INFRACTION_PENALTIES.get(rule_type, 0))
