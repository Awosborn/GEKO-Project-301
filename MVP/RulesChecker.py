"""Strategy compliance checks for bidding and card play.

The project stores strategy answers as numeric values in ``StrategyDeclaration.numeric_answers``.
This module exposes two public helpers:

* ``bid_follows_strategy``: validate whether a proposed bid is compatible with the
  selected strategy profile and hand context.
* ``card_play_follows_strategy``: validate whether a proposed card play is legal and
  aligned with basic declared defensive/declarer preferences.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from Data import StrategyDeclaration

# --- basic bridge constants -------------------------------------------------
SUITS: Tuple[str, ...] = ("C", "D", "H", "S")
RANKS: Tuple[str, ...] = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
HCP_MAP: Dict[str, int] = {"A": 4, "K": 3, "Q": 2, "J": 1}

# Numeric-answer indexes (0-based) in StrategyDeclaration.question_bank.
IDX_OPEN_MIN_1ST = 0
IDX_OPEN_MIN_2ND = 1
IDX_OPEN_MIN_3RD = 2
IDX_OPEN_MIN_4TH = 3
IDX_MAJOR_STYLE = 4
IDX_MINOR_STYLE = 5
IDX_1NT_MIN = 6
IDX_1NT_MAX = 7
IDX_MEANING_2D = 12
IDX_MEANING_2H = 13
IDX_MEANING_2S = 14
IDX_WEAK_TWO_STYLE = 15
IDX_3_LEVEL_PREEMPT_STYLE = 16
IDX_PREEMPT_VULN_ADJUSTMENT = 17
IDX_MAJOR_OPEN_LENGTH = 18
IDX_DECLARER_STYLE_NT = 72
IDX_DECLARER_STYLE_SUIT = 73


def _normalize_bid(bid: str) -> str:
    return bid.strip().upper()


def _hand_hcp(hand: Sequence[str]) -> int:
    return sum(HCP_MAP.get(card[:-1], 0) for card in hand)


def _suit_length(hand: Sequence[str], suit: str) -> int:
    return sum(1 for card in hand if card.endswith(suit))


def _opening_minimum_for_seat(strategy_answers: Sequence[int], seat: int) -> int:
    seat_idx_map = {1: IDX_OPEN_MIN_1ST, 2: IDX_OPEN_MIN_2ND, 3: IDX_OPEN_MIN_3RD, 4: IDX_OPEN_MIN_4TH}
    return strategy_answers[seat_idx_map[seat]]


def bid_follows_strategy(
    bid: str,
    hand: Sequence[str],
    strategy_answers: Sequence[int],
    *,
    seat: int,
    is_opening_bid: bool,
    vulnerability: bool = False,
) -> Tuple[bool, str]:
    """Check whether ``bid`` aligns with declared strategy answers.

    Args:
        bid: Candidate bid (e.g., ``1H``, ``1NT``, ``2S``, ``P``).
        hand: Player hand for evaluating HCP/shape constraints.
        strategy_answers: Numeric strategy answer array.
        seat: 1-4 seat position.
        is_opening_bid: True if this is the side's first non-pass bid.
        vulnerability: Whether bidder's side is vulnerable.

    Returns:
        (is_valid, message)
    """
    if len(strategy_answers) < 75:
        return False, "Strategy declaration is incomplete; expected 75 answers."
    if seat not in (1, 2, 3, 4):
        return False, "Seat must be one of 1, 2, 3, or 4."

    normalized = _normalize_bid(bid)
    if normalized in {"P", "X", "XX", "Q"}:
        return True, f"{normalized} accepted (non-contract action)."

    if len(normalized) < 2 or normalized[0] not in "1234567":
        return False, "Invalid contract bid format. Use 1C..7NT."

    level = int(normalized[0])
    strain = normalized[1:]
    if strain not in {"C", "D", "H", "S", "NT"}:
        return False, "Bid suit/strain must be C, D, H, S, or NT."

    hcp = _hand_hcp(hand)

    if is_opening_bid:
        open_min = _opening_minimum_for_seat(strategy_answers, seat)
        if hcp < open_min:
            return False, f"Opening bid rejected: hand has {hcp} HCP, below seat-{seat} minimum {open_min}."

    # 1NT range check
    if normalized == "1NT":
        nt_min = strategy_answers[IDX_1NT_MIN]
        nt_max = strategy_answers[IDX_1NT_MAX]
        if not (nt_min <= hcp <= nt_max):
            return False, f"1NT rejected: {hcp} HCP outside declared {nt_min}-{nt_max} range."

    # Major opening length requirement (Q19: 1=Always 5, 2=Usually 5, 3=Can be 4)
    if is_opening_bid and level == 1 and strain in {"H", "S"}:
        major_len_req_choice = strategy_answers[IDX_MAJOR_OPEN_LENGTH]
        min_len = 5 if major_len_req_choice == 1 else 4
        held = _suit_length(hand, strain)
        if held < min_len:
            return False, f"{normalized} rejected: {strain} length {held} below strategy requirement {min_len}+ cards."

    # Weak-two meaning check (Q13/14/15)
    if is_opening_bid and level == 2 and strain in {"D", "H", "S"}:
        meaning_idx = {"D": IDX_MEANING_2D, "H": IDX_MEANING_2H, "S": IDX_MEANING_2S}[strain]
        meaning_choice = strategy_answers[meaning_idx]
        # In question bank, option 1 is "Weak two" for each of these questions.
        if meaning_choice != 1:
            return False, f"{normalized} rejected: strategy does not define this opening as a weak two."

        style_choice = strategy_answers[IDX_WEAK_TWO_STYLE]  # 1=None, 2=Sound, 3=Normal, 4=Aggressive
        vuln_choice = strategy_answers[IDX_PREEMPT_VULN_ADJUSTMENT]

        # Coarse HCP guardrails by style.
        style_hcp_max = {2: 11, 3: 10, 4: 9}.get(style_choice, 10)
        if hcp > style_hcp_max:
            return False, f"Weak-two rejected: {hcp} HCP exceeds {style_hcp_max} for declared style."

        # If strongly vulnerability adjusted, tighten when vulnerable.
        if vulnerability and vuln_choice == 1 and hcp > max(6, style_hcp_max - 1):
            return False, "Weak-two rejected: vulnerable preempt too heavy for strongly adjusted style."

    # 3-level preempt style: simple top-end HCP sanity.
    if is_opening_bid and level == 3:
        preempt_style = strategy_answers[IDX_3_LEVEL_PREEMPT_STYLE]  # 1..4 (sound->very aggressive)
        style_cap = {1: 9, 2: 8, 3: 8, 4: 7}[preempt_style]
        if hcp > style_cap:
            return False, f"3-level preempt rejected: {hcp} HCP above style cap {style_cap}."

    # Opening style pressure for 1-level suit openings.
    if is_opening_bid and level == 1 and strain in SUITS:
        style_idx = IDX_MAJOR_STYLE if strain in {"H", "S"} else IDX_MINOR_STYLE
        style_choice = strategy_answers[style_idx]  # 1..5 very sound -> very light
        # Minimum opening offsets from declared seat minimum.
        penalty = {1: 1, 2: 0, 3: -1, 4: -2, 5: -2}[style_choice]
        required = _opening_minimum_for_seat(strategy_answers, seat) + penalty
        if hcp < required:
            return False, f"{normalized} rejected: {hcp} HCP below style-adjusted minimum {required}."

    return True, f"{normalized} is compatible with current strategy declaration."


def card_play_follows_strategy(
    card: str,
    hand: Sequence[str],
    trick_cards: Sequence[str],
    contract: Optional[Tuple[int, str, int, int]],
    strategy_answers: Sequence[int],
) -> Tuple[bool, str]:
    """Check whether a card play follows legal play and coarse strategy constraints.

    Args:
        card: Card being played.
        hand: Player's current hand.
        trick_cards: Cards already played to this trick in order.
        contract: (level, strain, declarer, multiplier) or ``None``.
        strategy_answers: Numeric strategy answers.

    Returns:
        (is_valid, message)
    """
    if len(strategy_answers) < 75:
        return False, "Strategy declaration is incomplete; expected 75 answers."

    normalized = card.strip().upper()
    if normalized not in hand:
        return False, "Card play rejected: card is not in player's hand."

    # Standard legal rule: follow lead suit if possible.
    if trick_cards:
        lead_suit = trick_cards[0][-1]
        has_lead = any(c.endswith(lead_suit) for c in hand)
        if has_lead and not normalized.endswith(lead_suit):
            return False, "Card play rejected: must follow suit when able."

    # Coarse style alignment for declarer line (no solver; lightweight consistency checks).
    if contract:
        strain = contract[1]
        declarer_style_idx = IDX_DECLARER_STYLE_NT if strain == "NT" else IDX_DECLARER_STYLE_SUIT
        declarer_style = strategy_answers[declarer_style_idx]  # 1 safety-first, 2 normal, 3 aggressive

        # If safety-first and discarding off-suit in trick when you can follow was already rejected,
        # encourage higher-card preservation by warning on aces/kings from non-winning context.
        if declarer_style == 1 and trick_cards:
            rank = normalized[:-1]
            if rank in {"A", "K"} and normalized[-1] != trick_cards[0][-1]:
                return False, "Card play rejected: safety-first style avoids high off-suit discards here."

    return True, f"Card {normalized} is legal and compatible with strategy declaration."


def strategy_answers_from_declaration(strategy: StrategyDeclaration) -> List[int]:
    """Small helper to safely pull numeric answers from a StrategyDeclaration object."""
    return list(strategy.numeric_answers)
