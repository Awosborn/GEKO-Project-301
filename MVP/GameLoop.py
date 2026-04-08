#!/usr/bin/env python3
"""bridge hand loop based on the project comments."""

from __future__ import annotations
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from Data import DoubleDummyOutcome, GameData, PLAYERS, RANKS, SUITS, build_deck
from PenaltyConfig import MAJOR_INFRACTION_PENALTIES, penalty_for_rule
from RulesChecker import acbl_open_chart_allows_bid, bid_follows_strategy

TRUMP_ORDER = {"C": 0, "D": 1, "H": 2, "S": 3, "NT": 4}
RANK_ORDER = {rank: idx for idx, rank in enumerate(RANKS)}


def _hand_hcp(hand: Sequence[str]) -> int:
    hcp_map = {"A": 4, "K": 3, "Q": 2, "J": 1}
    return sum(hcp_map.get(card[:-1], 0) for card in hand)


def _find_optimal_double_dummy_result(data: GameData) -> DoubleDummyOutcome:
    """Estimate a best contract/trick result and projected score from current hands."""
    side_hcp = {
        "NS": _hand_hcp(data.curr_card_hold[0]) + _hand_hcp(data.curr_card_hold[2]),
        "EW": _hand_hcp(data.curr_card_hold[1]) + _hand_hcp(data.curr_card_hold[3]),
    }
    side = "NS" if side_hcp["NS"] >= side_hcp["EW"] else "EW"
    declarer = 1 if side == "NS" else 2

    combined_hand = data.curr_card_hold[declarer - 1] + data.curr_card_hold[declarer + 1]
    suit_lengths = {s: sum(1 for c in combined_hand if c.endswith(s)) for s in SUITS}
    best_suit = max(suit_lengths, key=suit_lengths.get)

    total_hcp = side_hcp[side]
    expected_tricks = max(7, min(13, 6 + (total_hcp - 20) // 3))
    level = max(1, min(7, expected_tricks - 6))
    denomination = "NT" if total_hcp >= 25 and suit_lengths[best_suit] < 8 else best_suit

    contract = (level, denomination, declarer, 1)
    tricks = {player: 0 for player in PLAYERS}
    winners = (1, 3) if side == "NS" else (2, 4)
    tricks[winners[0]] = expected_tricks // 2
    tricks[winners[1]] = expected_tricks - tricks[winners[0]]
    projected = calc_point_function(contract, tricks, data.vulnerability)
    projected_score = projected[winners[0]]
    return DoubleDummyOutcome(
        contract=f"{level}{denomination}",
        declarer=declarer,
        expected_tricks=expected_tricks,
        projected_score=projected_score,
    )


def preset(data: GameData, rng: random.Random | None = None) -> Tuple[List[int], int]:
    """Reset hand data, deal cards, and choose a random player-1 starting offset."""
    rng = rng or random.Random()
    data.reset_round_state()
    data.randomize_board(rng)

    deck = build_deck()
    rng.shuffle(deck)
    for i, card in enumerate(deck):
        data.curr_card_hold[i % 4].append(card)

    for hand in data.curr_card_hold:
        hand.sort(key=lambda c: (RANK_ORDER[c[:-1]], SUITS.index(c[-1])))

    start_offset = rng.randint(0, 3)
    base = [1, 2, 3, 4]
    start_positions = base[-start_offset:] + base[:-start_offset]
    data.double_dummy_outcome = _find_optimal_double_dummy_result(data)
    return start_positions, start_positions[0]


def display_cards(data: GameData) -> None:
    ns_vul = "VUL" if data.vulnerability[1] else "NV"
    ew_vul = "VUL" if data.vulnerability[2] else "NV"
    print(f"Board {data.board_number} vulnerability -> NS: {ns_vul}, EW: {ew_vul}")
    if data.double_dummy_outcome:
        dd = data.double_dummy_outcome
        print(
            "Estimated best double-dummy line: "
            f"{dd.contract} by Player {dd.declarer}, {dd.expected_tricks} tricks, "
            f"projected score {dd.projected_score}"
        )
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




def _is_opening_bid_for_player(data: GameData, player: int) -> bool:
    """Return True when player's side has not yet made any non-pass call."""
    side = _partnership(player)
    for row in data.curr_bid_hist:
        for seat, prior_bid in enumerate(row, start=1):
            if prior_bid is None or prior_bid == "P":
                continue
            if _partnership(seat) == side:
                return False
    return True


def _log_bid_infraction(
    data: GameData,
    *,
    player: int,
    bid: str,
    rule_type: str,
    message: str,
    auction_index: int,
) -> None:
    penalty_points = penalty_for_rule(rule_type)
    data.record_infraction(
        player=player,
        bid=bid,
        rule_type=rule_type,
        message=message,
        auction_index=auction_index,
        penalty_points=penalty_points,
    )
    print(
        f"INFRACTION [{rule_type}] player={player} bid={bid} idx={auction_index} "
        f"penalty={penalty_points}: {message}"
    )


def _validate_bid(
    bid: str,
    player: int,
    last_contract: Optional[Tuple[int, str, int, int]],
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
) -> Tuple[Optional[Tuple[int, str, int, int]], Optional[str]]:
    """Run bidding until contract is set or everyone passes out the hand."""
    idx = 0
    passes_in_row = 0
    total_bids = 0
    last_contract: Optional[Tuple[int, str, int, int]] = None
    last_action: Optional[Tuple[str, int]] = None

    auction_index = 0
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

        is_opening_bid = _is_opening_bid_for_player(data, player)
        chart_ok, chart_message = acbl_open_chart_allows_bid(raw, data.curr_card_hold[player - 1], is_opening_bid=is_opening_bid)
        if not chart_ok:
            _log_bid_infraction(
                data,
                player=player,
                bid=raw,
                rule_type="acbl_chart_violation",
                message=chart_message,
                auction_index=auction_index,
            )
            auction_index += 1
            continue

        strat_ok, strat_message = bid_follows_strategy(
            raw,
            data.curr_card_hold[player - 1],
            data.strat_dec.numeric_answers,
            seat=player,
            is_opening_bid=is_opening_bid,
            vulnerability=data.vulnerability[player],
        )
        if not strat_ok:
            _log_bid_infraction(
                data,
                player=player,
                bid=raw,
                rule_type="strategy_mismatch",
                message=strat_message,
                auction_index=auction_index,
            )
            auction_index += 1
            continue

        data.record_bid(player, raw)
        total_bids += 1
        auction_index += 1

        if action == "pass":
            passes_in_row += 1
        else:
            passes_in_row = 0
            last_action = (action if action in {"X", "XX"} else "contract", player)
            if action == "contract":
                last_contract = (int(raw[0]), raw[1:], player, 1)
            elif action == "double" and last_contract:
                last_contract = (last_contract[0], last_contract[1], last_contract[2], 2)
            elif action == "redouble" and last_contract:
                last_contract = (last_contract[0], last_contract[1], last_contract[2], 4)

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
    contract: Optional[Tuple[int, str, int, int]],
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


def _overtrick_points(suit: str, multiplier: int, overtricks: int, is_vulnerable: bool) -> int:
    if overtricks <= 0:
        return 0
    if multiplier == 1:
        if suit in {"C", "D"}:
            return overtricks * 20
        return overtricks * 30
    if multiplier == 2:
        return overtricks * (200 if is_vulnerable else 100)
    return overtricks * (400 if is_vulnerable else 200)


def _undertrick_penalty(undertricks: int, multiplier: int, is_vulnerable: bool) -> int:
    if multiplier == 1:
        return undertricks * (100 if is_vulnerable else 50)

    if is_vulnerable:
        raw = 200
        if undertricks > 1:
            raw += (undertricks - 1) * 300
    else:
        if undertricks == 1:
            raw = 100
        elif undertricks == 2:
            raw = 300
        elif undertricks == 3:
            raw = 500
        else:
            raw = 500 + (undertricks - 3) * 300
    return raw * (2 if multiplier == 4 else 1)


def calc_point_function(
    contract: Optional[Tuple[int, str, int, int]],
    tricks: Dict[int, int],
    vulnerability: Dict[int, bool],
) -> Dict[int, int]:
    """Compute duplicate-bridge style score with vulnerability and double/redouble handling."""
    points = {player: 0 for player in PLAYERS}
    if not contract:
        return points

    level, suit, declarer, multiplier = contract
    declarer_side = (1, 3) if declarer in (1, 3) else (2, 4)
    defenders = (2, 4) if declarer in (1, 3) else (1, 3)
    is_vulnerable = vulnerability[declarer]

    made_by_side = tricks[declarer_side[0]] + tricks[declarer_side[1]]
    target = level + 6
    if made_by_side >= target:
        bid_tricks = level
        if suit in {"C", "D"}:
            trick_score = bid_tricks * 20
        elif suit in {"H", "S"}:
            trick_score = bid_tricks * 30
        else:
            trick_score = 40 + (bid_tricks - 1) * 30
        trick_score *= multiplier

        overtricks = made_by_side - target
        overtrick_score = _overtrick_points(suit, multiplier, overtricks, is_vulnerable)

        game_bonus = 500 if is_vulnerable else 300
        if trick_score < 100:
            game_bonus = 50

        slam_bonus = 0
        if level == 6:
            slam_bonus = 750 if is_vulnerable else 500
        elif level == 7:
            slam_bonus = 1500 if is_vulnerable else 1000

        insult_bonus = 50 if multiplier == 2 else 100 if multiplier == 4 else 0
        earned = trick_score + overtrick_score + game_bonus + slam_bonus + insult_bonus
        for player in declarer_side:
            points[player] = earned
    else:
        undertricks = target - made_by_side
        penalty = _undertrick_penalty(undertricks, multiplier, is_vulnerable)
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
    round_points = calc_point_function(contract, tricks, data.vulnerability)
    adjusted_points = dict(round_points)
    for player, penalty in data.penalty_points_by_player.items():
        adjusted_points[player] = adjusted_points.get(player, 0) - penalty

    data.round_result_payload = {
        "contract": contract,
        "tricks": tricks,
        "base_points": round_points,
        "penalty_points_by_player": dict(data.penalty_points_by_player),
        "cumulative_penalty_points": sum(data.penalty_points_by_player.values()),
        "penalty_reason_breakdown": dict(data.penalty_reason_breakdown),
        "infractions": list(data.bid_infractions),
        "adjusted_points": adjusted_points,
        "penalty_table": dict(MAJOR_INFRACTION_PENALTIES),
    }

    data.add_round_points(adjusted_points)

    print(f"Round tricks: {tricks}")
    print(f"Round points (after penalties): {data.curr_points}")
    print(f"Round result payload: {data.round_result_payload}")
    print(f"Historical points: {data.hist_points}")
    return data


if __name__ == "__main__":
    game()
