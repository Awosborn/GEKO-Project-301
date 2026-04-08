#!/usr/bin/env python3
"""MVP bridge hand loop based on the project comments."""

from __future__ import annotations

import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from Data import GameData, PLAYERS, RANKS, SUITS, build_deck

TRUMP_ORDER = {"C": 0, "D": 1, "H": 2, "S": 3, "NT": 4}
RANK_ORDER = {rank: idx for idx, rank in enumerate(RANKS)}


def preset(data: GameData, rng: random.Random | None = None) -> Tuple[List[int], int]:
    """Reset hand data, deal cards, and choose a random player-1 starting offset."""
    rng = rng or random.Random()
    data.reset_round_state()

    deck = build_deck()
    rng.shuffle(deck)
    for i, card in enumerate(deck):
        data.curr_card_hold[i % 4].append(card)

    for hand in data.curr_card_hold:
        hand.sort(key=lambda c: (RANK_ORDER[c[:-1]], SUITS.index(c[-1])))

    start_offset = rng.randint(0, 3)
    base = [1, 2, 3, 4]
    start_positions = base[-start_offset:] + base[:-start_offset]
    return start_positions, start_positions[0]


def display_cards(data: GameData) -> None:
    for i, hand in enumerate(data.curr_card_hold, start=1):
        print(f"Player {i} cards: {' '.join(hand)}")


def _bid_rank(bid: str) -> Optional[int]:
    bid = bid.upper().strip()
    if bid in {"P", "X", "XX"}:
        return None
    level = int(bid[0])
    suit = bid[1:]
    return (level - 1) * 5 + TRUMP_ORDER[suit]


def _partnership(player: int) -> int:
    return 0 if player in (1, 3) else 1


def _validate_bid(
    bid: str,
    player: int,
    last_contract: Optional[Tuple[int, str, int]],
    last_action: Optional[Tuple[str, int]],
) -> Tuple[bool, str]:
    bid = bid.upper().strip()
    if bid == "Q":
        return True, "quit"
    if bid == "P":
        return True, "pass"

    if bid == "X":
        if not last_contract:
            return False, "Cannot double before a contract bid exists."
        if _partnership(player) == _partnership(last_contract[2]):
            return False, "Cannot double your own side's contract."
        if last_action and last_action[0] in {"X", "XX"}:
            return False, "Double is only valid directly over a contract (passes allowed)."
        return True, "double"

    if bid == "XX":
        if not last_action or last_action[0] != "X":
            return False, "Redouble requires an opponent double first."
        if _partnership(player) != _partnership(last_contract[2]):
            return False, "Only the doubled side can redouble."
        return True, "redouble"

    if len(bid) < 2 or bid[0] not in "1234567" or bid[1:] not in TRUMP_ORDER:
        return False, "Use bids like 1C, 2H, 3NT, or actions P/X/XX/Q."

    if last_contract and _bid_rank(bid) <= _bid_rank(f"{last_contract[0]}{last_contract[1]}"):
        return False, "Bid must be higher than the previous contract bid."

    return True, "contract"


def bid_function(
    data: GameData,
    start_order: Sequence[int],
    input_fn: Callable[[str], str] = input,
) -> Tuple[Optional[Tuple[int, str, int]], Optional[str]]:
    """Run bidding until contract is set or everyone passes out the hand."""
    idx = 0
    passes_in_row = 0
    total_bids = 0
    last_contract: Optional[Tuple[int, str, int]] = None
    last_action: Optional[Tuple[str, int]] = None

    while True:
        player = start_order[idx % 4]
        raw = input_fn(
            f"PLAYER {player} please make your bid "
            "(1C..7NT, P=pass, X=double, XX=redouble, Q=quit): "
        ).strip().upper()

        ok, action = _validate_bid(raw, player, last_contract, last_action)
        if not ok:
            print(action)
            continue

        if action == "quit":
            return None, "quit"

        data.record_bid(player, raw)
        total_bids += 1

        if action == "pass":
            passes_in_row += 1
        else:
            passes_in_row = 0
            last_action = (action if action in {"X", "XX"} else "contract", player)
            if action == "contract":
                last_contract = (int(raw[0]), raw[1:], player)

        # four passes with no contract = passed-out hand
        if last_contract is None and total_bids >= 4 and passes_in_row >= 4:
            return None, "passed_out"

        # after a contract appears, bidding ends after 3 passes in a row
        if last_contract is not None and passes_in_row >= 3:
            return last_contract, "complete"

        idx += 1


def _beats(card: str, best: str, lead_suit: str, trump: Optional[str]) -> bool:
    suit = card[-1]
    best_suit = best[-1]
    if trump and suit == trump and best_suit != trump:
        return True
    if suit == best_suit:
        return RANK_ORDER[card[:-1]] > RANK_ORDER[best[:-1]]
    if best_suit == trump:
        return False
    if suit == lead_suit and best_suit != lead_suit:
        return True
    return False


def card_play_function(
    data: GameData,
    start_player: int,
    contract: Optional[Tuple[int, str, int]],
    input_fn: Callable[[str], str] = input,
) -> Dict[int, int]:
    """Play 13 tricks; trick winner starts next as in bridge."""
    hands = {player: list(data.curr_card_hold[player - 1]) for player in PLAYERS}
    tricks = {player: 0 for player in PLAYERS}
    leader = start_player
    trump = None if not contract or contract[1] == "NT" else contract[1]

    for _ in range(13):
        order = [((leader - 1 + i) % 4) + 1 for i in range(4)]
        trick: List[Tuple[int, str]] = []
        lead_suit = None

        for player in order:
            while True:
                prompt = f"Player {player}, play a card from your hand {hands[player]}: "
                card = input_fn(prompt).strip().upper()
                if card not in hands[player]:
                    print("You must play a card you hold.")
                    continue
                if lead_suit and any(c.endswith(lead_suit) for c in hands[player]) and not card.endswith(lead_suit):
                    print("You must follow suit when possible.")
                    continue
                break

            if lead_suit is None:
                lead_suit = card[-1]
            hands[player].remove(card)
            trick.append((player, card))

        winner, winning_card = trick[0]
        for player, card in trick[1:]:
            if _beats(card, winning_card, lead_suit, trump):
                winner, winning_card = player, card

        tricks[winner] += 1
        leader = winner
        print(f"Trick winner: Player {winner} with {winning_card}")

    return tricks


def calc_point_function(contract: Optional[Tuple[int, str, int]], tricks: Dict[int, int]) -> Dict[int, int]:
    """Simplified ACBL-style MVP scoring: contract side +10 per trick over book, else defenders +50 per undertrick."""
    points = {player: 0 for player in PLAYERS}
    if not contract:
        return points

    level, _suit, declarer = contract
    declarer_side = (1, 3) if declarer in (1, 3) else (2, 4)
    defenders = (2, 4) if declarer in (1, 3) else (1, 3)

    made_by_side = tricks[declarer_side[0]] + tricks[declarer_side[1]]
    target = level + 6
    if made_by_side >= target:
        earned = (made_by_side - 6) * 10
        for player in declarer_side:
            points[player] = earned
    else:
        penalty = (target - made_by_side) * 50
        for player in defenders:
            points[player] = penalty
    return points


def game(input_fn: Callable[[str], str] = input, rng: random.Random | None = None) -> GameData:
    """Play one full hand in order: preset -> display -> bid -> card play -> point calc."""
    data = GameData()
    start_positions, opening_player = preset(data, rng=rng)
    print(f"Starting order for this hand: {start_positions}")
    display_cards(data)

    contract, bid_state = bid_function(data, start_positions, input_fn=input_fn)
    if bid_state == "quit":
        print("Game ended by user during bidding.")
        return data
    if bid_state == "passed_out":
        print("All four players passed. No play, no points.")
        return data

    tricks = card_play_function(data, opening_player, contract, input_fn=input_fn)
    round_points = calc_point_function(contract, tricks)
    data.add_round_points(round_points)

    print(f"Round tricks: {tricks}")
    print(f"Round points: {data.curr_points}")
    print(f"Historical points: {data.hist_points}")
    return data


if __name__ == "__main__":
    game()
