"""Week-1 preprocessing utilities for supervised bidding datasets.

Implements the first four data-pipeline priorities from the project report:
1) derive ``deal_id`` from ``game_id`` + ``board_number``
2) normalize bid tokens to canonical forms
3) reconstruct pre-play 13-card hands from snapshot state
4) validate reconstructed hands and mark corrupt deals
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

PLAYERS: Tuple[int, ...] = (1, 2, 3, 4)


@dataclass(frozen=True)
class ReconstructionResult:
    """Outcome for hand reconstruction + corruption checks."""

    hands: Dict[int, List[str]]
    is_corrupted: bool
    reason: str = ""


def compute_deal_id(snapshot: Mapping[str, object]) -> str:
    """Build a stable deal id in the form ``<game_id>:<board_number>``."""
    return f"{snapshot['game_id']}:{snapshot['board_number']}"


def normalize_bid(raw: str) -> str:
    """Normalize a raw bid token into a canonical bridge token."""
    token = raw.strip()
    if not token:
        return "UNK"

    lower = token.lower()
    if lower == "pass":
        return "P"
    if lower == "d":
        return "X"
    if lower == "r":
        return "XX"

    token = token.upper()
    if len(token) == 2 and token[0] in "1234567" and token[1] == "N":
        return f"{token[0]}NT"

    return token


def normalize_bid_history(raw_bids: Iterable[str]) -> List[str]:
    """Normalize an iterable of bids."""
    return [normalize_bid(bid) for bid in raw_bids]


def reconstruct_full_hands(snapshot: Mapping[str, object]) -> ReconstructionResult:
    """Reconstruct each player's pre-play hand from snapshot state.

    Snapshot contract:
    * ``curr_card_hold``: list[4][str] cards currently held.
    * ``curr_card_play_hist``: list of events with fields ``player`` and ``card``.
    """
    raw_holds = snapshot.get("curr_card_hold")
    if not isinstance(raw_holds, list) or len(raw_holds) != 4:
        return ReconstructionResult(hands={}, is_corrupted=True, reason="curr_card_hold must contain 4 hands")

    hands: Dict[int, List[str]] = {}
    for idx, cards in enumerate(raw_holds, start=1):
        if not isinstance(cards, list):
            return ReconstructionResult(hands={}, is_corrupted=True, reason=f"hand {idx} is not a list")
        hands[idx] = [str(card).upper() for card in cards]

    raw_play_hist = snapshot.get("curr_card_play_hist", [])
    if not isinstance(raw_play_hist, list):
        return ReconstructionResult(hands=hands, is_corrupted=True, reason="curr_card_play_hist must be a list")

    for event in raw_play_hist:
        if not isinstance(event, Mapping):
            return ReconstructionResult(hands=hands, is_corrupted=True, reason="play event is not an object")
        player = int(event.get("player", 0))
        card = str(event.get("card", "")).upper()
        if player not in PLAYERS or not card:
            return ReconstructionResult(hands=hands, is_corrupted=True, reason="play event has invalid player/card")
        hands[player].append(card)

    counts = {player: len(hands[player]) for player in PLAYERS}
    if any(count != 13 for count in counts.values()):
        return ReconstructionResult(
            hands=hands,
            is_corrupted=True,
            reason=f"expected 13 cards per hand after reconstruction, got {counts}",
        )

    seen: MutableMapping[str, int] = {}
    for player in PLAYERS:
        for card in hands[player]:
            seen[card] = seen.get(card, 0) + 1
    duplicated = sorted(card for card, count in seen.items() if count > 1)
    if duplicated:
        return ReconstructionResult(
            hands=hands,
            is_corrupted=True,
            reason=f"duplicated cards across hands: {', '.join(duplicated)}",
        )

    return ReconstructionResult(hands=hands, is_corrupted=False)
