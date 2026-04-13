"""Week-4 legality-mask helpers for supervised bidding/card-play models."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .normalize import normalize_bid, normalize_card

TRUMP_ORDER: Dict[str, int] = {"C": 0, "D": 1, "H": 2, "S": 3, "NT": 4}
CONTRACT_BIDS: List[str] = [f"{level}{strain}" for level in range(1, 8) for strain in ("C", "D", "H", "S", "NT")]


def _partnership(player: int) -> int:
    return 0 if player in {1, 3} else 1


def _bid_rank(contract_bid: str) -> int:
    level = int(contract_bid[0])
    strain = contract_bid[1:]
    return (level - 1) * 5 + TRUMP_ORDER[strain]


def _last_contract(prefix: Sequence[str]) -> Optional[Tuple[str, int]]:
    for idx in range(len(prefix) - 1, -1, -1):
        bid = normalize_bid(prefix[idx])
        if bid and bid[0] in "1234567" and bid[1:] in TRUMP_ORDER:
            player = (idx % 4) + 1
            return bid, player
    return None


def _last_non_pass_action(prefix: Sequence[str]) -> Optional[Tuple[str, int]]:
    for idx in range(len(prefix) - 1, -1, -1):
        bid = normalize_bid(prefix[idx])
        if bid != "P":
            return bid, (idx % 4) + 1
    return None


def is_legal_bid(candidate_bid: str, *, seat_to_act: int, bid_prefix: Sequence[str]) -> bool:
    """Validate one bid using the same core legality as ``GameLoop._validate_bid``."""
    bid = normalize_bid(candidate_bid)
    if bid == "P":
        return True

    last_contract = _last_contract(bid_prefix)
    last_non_pass = _last_non_pass_action(bid_prefix)

    if bid == "X":
        if not last_contract:
            return False
        _, contract_player = last_contract
        if _partnership(seat_to_act) == _partnership(contract_player):
            return False
        if last_non_pass and last_non_pass[0] in {"X", "XX"}:
            return False
        return True

    if bid == "XX":
        if not last_non_pass or last_non_pass[0] != "X":
            return False
        if not last_contract:
            return False
        _, contract_player = last_contract
        return _partnership(seat_to_act) == _partnership(contract_player)

    if len(bid) < 2 or bid[0] not in "1234567" or bid[1:] not in TRUMP_ORDER:
        return False

    if last_contract and _bid_rank(bid) <= _bid_rank(last_contract[0]):
        return False

    return True


def legal_bids(*, seat_to_act: int, bid_prefix: Sequence[str]) -> List[str]:
    """Return all legal bids (P/X/XX/contracts) for the acting seat."""
    candidates = ["P", "X", "XX", *CONTRACT_BIDS]
    return [bid for bid in candidates if is_legal_bid(bid, seat_to_act=seat_to_act, bid_prefix=bid_prefix)]


def bid_legality_mask(
    vocab_tokens: Sequence[str],
    *,
    seat_to_act: int,
    bid_prefix: Sequence[str],
    illegal_value: float = float("-inf"),
) -> List[float]:
    """Build a logit mask over ``vocab_tokens`` for bidding inference/training."""
    legal = set(legal_bids(seat_to_act=seat_to_act, bid_prefix=bid_prefix))
    mask: List[float] = []
    for token in vocab_tokens:
        normalized = normalize_bid(token)
        mask.append(0.0 if normalized in legal else illegal_value)
    return mask


def legal_cards(*, hand_cards: Sequence[str], trick_cards: Sequence[str]) -> List[str]:
    """Return legally playable cards (must follow lead suit when able)."""
    normalized_hand = [normalize_card(card) for card in hand_cards]
    if not trick_cards:
        return [card for card in normalized_hand if card != "UNK"]

    lead_suit = normalize_card(trick_cards[0])[-1]
    same_suit_cards = [card for card in normalized_hand if card.endswith(lead_suit)]
    if same_suit_cards:
        return same_suit_cards
    return [card for card in normalized_hand if card != "UNK"]


def card_legality_mask(
    vocab_tokens: Sequence[str],
    *,
    hand_cards: Sequence[str],
    trick_cards: Sequence[str],
    illegal_value: float = float("-inf"),
) -> List[float]:
    """Build a logit mask over ``vocab_tokens`` for card-play inference/training."""
    legal = set(legal_cards(hand_cards=hand_cards, trick_cards=trick_cards))
    mask: List[float] = []
    for token in vocab_tokens:
        normalized = normalize_card(token)
        mask.append(0.0 if normalized in legal else illegal_value)
    return mask
