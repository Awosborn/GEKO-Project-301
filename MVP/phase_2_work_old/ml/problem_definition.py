"""Locked problem-definition decisions for supervised next-action datasets.

This module centralizes dataset/model assumptions that must remain stable so
feature engineering and labels stay consistent across training runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class VisibilityPolicy(str, Enum):
    """Information available to the policy model."""

    ACTING_HAND_PLUS_PUBLIC = "acting_hand_plus_public"


class LabelSource(str, Enum):
    """Canonical source used to create "best move" labels."""

    SOLVER = "solver"


@dataclass(frozen=True)
class ProblemDefinition:
    """Immutable decisions for data schema, features, and targets."""

    seat_order: List[str]
    inference_visibility: VisibilityPolicy
    training_visibility: VisibilityPolicy
    label_source: LabelSource
    derive_declarer_dummy_now: bool


# Seat ids used throughout the existing pipeline are 1..4.
SEAT_ID_TO_COMPASS: Dict[int, str] = {1: "N", 2: "E", 3: "S", 4: "W"}
COMPASS_TO_SEAT_ID: Dict[str, int] = {value: key for key, value in SEAT_ID_TO_COMPASS.items()}


def auction_seat_to_act(dealer_seat: int, call_index: int) -> int:
    """Return seat id (1..4) that acts for a 0-indexed auction call.

    Auction order is clockwise starting from the dealer.
    """
    if dealer_seat not in (1, 2, 3, 4):
        raise ValueError("dealer_seat must be in [1, 2, 3, 4]")
    if call_index < 0:
        raise ValueError("call_index must be >= 0")
    return ((dealer_seat - 1 + call_index) % 4) + 1


LOCKED_PROBLEM_DEFINITION = ProblemDefinition(
    seat_order=["N", "E", "S", "W"],
    inference_visibility=VisibilityPolicy.ACTING_HAND_PLUS_PUBLIC,
    training_visibility=VisibilityPolicy.ACTING_HAND_PLUS_PUBLIC,
    label_source=LabelSource.SOLVER,
    derive_declarer_dummy_now=True,
)
