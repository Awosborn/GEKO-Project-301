#!/usr/bin/env python3
"""bridge hand loop based on the project comments."""

from __future__ import annotations
import json
import os
import random
import subprocess
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple

from BidRecommender import recommend_bid as recommend_bids_for_player
from CardPlayRecommender import recommend_card as recommend_card_for_player
from Coach import Coach
from Data import DoubleDummyOutcome, GameData, PLAYERS, RANKS, SUITS, build_deck
from PenaltyConfig import MAJOR_INFRACTION_PENALTIES, penalty_for_rule
from RulesChecker import acbl_open_chart_allows_bid, bid_follows_strategy
from demo_scenarios import get_demo_scenario, list_demo_scenarios
from model_registry import load_latest_stable_model

TRUMP_ORDER = {"C": 0, "D": 1, "H": 2, "S": 3, "NT": 4}
RANK_ORDER = {rank: idx for idx, rank in enumerate(RANKS)}


# Function: _hand_hcp.
def _hand_hcp(hand: Sequence[str]) -> int:
    hcp_map = {"A": 4, "K": 3, "Q": 2, "J": 1}
    return sum(hcp_map.get(card[:-1], 0) for card in hand)


# Function: _find_optimal_double_dummy_result.
def _find_optimal_double_dummy_result(data: GameData) -> DoubleDummyOutcome:
    """Resolve board double-dummy outcome through adapter, with heuristic fallback."""
    adapter = _build_double_dummy_adapter()
    try:
        return adapter.solve(data)
    except Exception as exc:
        print(f"Double-dummy solver unavailable ({exc}); using heuristic mode.")
        return _heuristic_double_dummy_outcome(data, solver_mode="heuristic_fallback", solver_name=type(adapter).__name__)


class _DoubleDummyAdapter(Protocol):
    def solve(self, data: GameData) -> DoubleDummyOutcome:
        ...


def _build_double_dummy_adapter() -> _DoubleDummyAdapter:
    solver_cmd = os.getenv("BRIDGE_DD_SOLVER_CMD", "").strip()
    if solver_cmd:
        return _CommandDoubleDummyAdapter(command=solver_cmd)

    solver_url = os.getenv("BRIDGE_DD_SOLVER_URL", "").strip()
    if solver_url:
        return _ServiceDoubleDummyAdapter(url=solver_url)

    return _HeuristicDoubleDummyAdapter()


class _HeuristicDoubleDummyAdapter:
    def solve(self, data: GameData) -> DoubleDummyOutcome:
        return _heuristic_double_dummy_outcome(data, solver_mode="heuristic", solver_name="heuristic_adapter")


class _CommandDoubleDummyAdapter:
    def __init__(self, command: str) -> None:
        self.command = command

    def solve(self, data: GameData) -> DoubleDummyOutcome:
        payload = _build_solver_payload(data)
        proc = subprocess.run(
            self.command.split(),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
        )
        response = json.loads(proc.stdout)
        return _outcome_from_solver_response(data, response, solver_name="command_adapter")


class _ServiceDoubleDummyAdapter:
    def __init__(self, url: str) -> None:
        self.url = url

    def solve(self, data: GameData) -> DoubleDummyOutcome:
        payload = _build_solver_payload(data)
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"solver service error: {exc}") from exc

        response = json.loads(body)
        return _outcome_from_solver_response(data, response, solver_name="service_adapter")


def _build_solver_payload(data: GameData) -> Dict[str, Any]:
    return {
        "hands": {str(player): list(data.curr_card_hold[player - 1]) for player in PLAYERS},
        "vulnerability": {str(player): bool(data.vulnerability[player]) for player in PLAYERS},
        "board_number": int(data.board_number),
    }


def _outcome_from_solver_response(
    data: GameData,
    response: Dict[str, Any],
    *,
    solver_name: str,
) -> DoubleDummyOutcome:
    contract = str(response["contract"]).upper()
    declarer = int(response["declarer"])
    expected_tricks = int(response["expected_tricks"])
    projected_score = int(response["projected_score"])
    par_score = int(response.get("par_score", projected_score))
    contract_alternatives = list(response.get("contract_alternatives", []))
    trick_table = dict(response.get("trick_table", {}))

    return DoubleDummyOutcome(
        contract=contract,
        declarer=declarer,
        expected_tricks=expected_tricks,
        projected_score=projected_score,
        par_score=par_score,
        contract_alternatives=contract_alternatives,
        trick_table=trick_table,
        solver_mode="solver",
        solver_name=solver_name,
        is_heuristic=False,
    )


def _heuristic_double_dummy_outcome(
    data: GameData,
    *,
    solver_mode: str,
    solver_name: str,
) -> DoubleDummyOutcome:
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
    trick_table: Dict[str, Dict[int, int]] = {
        "C": {1: 6, 2: 6, 3: 6, 4: 6},
        "D": {1: 6, 2: 6, 3: 6, 4: 6},
        "H": {1: 6, 2: 6, 3: 6, 4: 6},
        "S": {1: 6, 2: 6, 3: 6, 4: 6},
        "NT": {1: 6, 2: 6, 3: 6, 4: 6},
    }
    trick_table[denomination][declarer] = expected_tricks

    return DoubleDummyOutcome(
        contract=f"{level}{denomination}",
        declarer=declarer,
        expected_tricks=expected_tricks,
        projected_score=projected_score,
        par_score=projected_score,
        contract_alternatives=[
            {
                "contract": f"{level}{denomination}",
                "declarer": declarer,
                "expected_tricks": expected_tricks,
                "projected_score": projected_score,
            }
        ],
        trick_table=trick_table,
        solver_mode=solver_mode,
        solver_name=solver_name,
        is_heuristic=True,
    )


# Function: preset.
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


def preset_from_scenario(data: GameData, scenario: Dict[str, Any]) -> Tuple[List[int], int]:
    """Load a fixed scenario for deterministic demos."""
    data.reset_round_state()
    data.board_number = int(scenario["board_number"])
    data.set_board_vulnerability()
    for player in PLAYERS:
        cards = [str(card).upper() for card in scenario["hands"][player]]
        data.curr_card_hold[player - 1] = sorted(cards, key=lambda c: (RANK_ORDER[c[:-1]], SUITS.index(c[-1])))
    start_positions = list(scenario.get("start_positions", [1, 2, 3, 4]))
    data.double_dummy_outcome = _find_optimal_double_dummy_result(data)
    return start_positions, start_positions[0]


# Function: display_cards.
def display_cards(data: GameData) -> None:
    ns_vul = "VUL" if data.vulnerability[1] else "NV"
    ew_vul = "VUL" if data.vulnerability[2] else "NV"
    print(f"Board {data.board_number} vulnerability -> NS: {ns_vul}, EW: {ew_vul}")
    if data.double_dummy_outcome:
        dd = data.double_dummy_outcome
        print(
            "Estimated best double-dummy line: "
            f"{dd.contract} by Player {dd.declarer}, {dd.expected_tricks} tricks, "
            f"projected score {dd.projected_score} "
            f"[mode={dd.solver_mode}, solver={dd.solver_name}]"
        )
    for i, hand in enumerate(data.curr_card_hold, start=1):
        print(f"Player {i} cards: {' '.join(hand)}")


# Function: _bid_rank.
def _bid_rank(bid: str) -> Optional[int]:
    bid = bid.upper().strip()
    if bid in {"P", "X", "XX"}:
        return None
    level = int(bid[0])
    suit = bid[1:]
    return (level - 1) * 5 + TRUMP_ORDER[suit]


# Function: _partnership.
def _partnership(player: int) -> int:
    return 0 if player in (1, 3) else 1




# Function: _display_bid_recommendations.
def _display_bid_recommendations(recommendations: Sequence[Dict[str, object]], *, player: int) -> None:
    if not recommendations:
        print(f"System recommendations for Player {player}: unavailable.")
        return

    print(f"System top bid recommendations for Player {player}:")
    for rec in recommendations:
        print(
            f"  #{rec.get('rank', '?')} {rec.get('bid')} "
            f"(conf={rec.get('confidence', 0):.2f}) -> {rec.get('reason', '')}"
        )


# Function: _display_recommendation_comparison.
def _display_recommendation_comparison(
    player_bid: str,
    recommendations: Sequence[Dict[str, object]],
) -> None:
    chosen = player_bid.strip().upper()
    matches = [rec for rec in recommendations if str(rec.get("bid", "")).upper() == chosen]
    if matches:
        rec = matches[0]
        print(
            "Coaching comparison: your bid matched system recommendation "
            f"(rank #{rec.get('rank', '?')}, conf={rec.get('confidence', 0):.2f})."
        )
        return

    if recommendations:
        best = recommendations[0]
        print(
            "Coaching comparison: your bid differed from top recommendation "
            f"{best.get('bid')} (conf={best.get('confidence', 0):.2f})."
        )
    else:
        print("Coaching comparison: recommendation unavailable for this action.")


def _immediate_deviation_feedback(
    decision: str,
    user_action: str,
    recommendations: Sequence[Dict[str, object]],
) -> None:
    if not recommendations:
        print("Feedback: no near-expert recommendation available.")
        return
    key = "bid" if decision == "bid" else "card"
    top = str(recommendations[0].get(key, "")).upper()
    if user_action.strip().upper() == top:
        print("Feedback: aligned with near-expert top line.")
    else:
        print(f"Feedback: deviation detected. Near-expert preferred {top}.")


# Function: _is_opening_bid_for_player.
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


# Function: _log_bid_infraction.
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


# Function: _validate_bid.
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


# Function: bid_function.
def bid_function(
    data: GameData,
    start_order: Sequence[int],
    coach: Coach,
    decision_feedback: List[Dict[str, Any]],
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
        recommendations = recommend_bids_for_player(
            hand=data.curr_card_hold[player - 1],
            bid_history=data.curr_bid_hist,
            strategy_answers=data.strat_dec.numeric_answers,
            seat=player,
            vulnerability=data.vulnerability[player],
        )
        _display_bid_recommendations(recommendations, player=player)
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
        _display_recommendation_comparison(raw, recommendations)
        _immediate_deviation_feedback("bid", raw, recommendations)
        bid_feedback = coach.explain_bid_decision(
            user_bid=raw,
            recommended_bids=recommendations,
            context={
                "player": player,
                "auction_index": auction_index,
                "auction_history": [list(row) for row in data.curr_bid_hist],
                "double_dummy": None if data.double_dummy_outcome is None else {
                    "contract": data.double_dummy_outcome.contract,
                    "declarer": data.double_dummy_outcome.declarer,
                    "expected_tricks": data.double_dummy_outcome.expected_tricks,
                    "projected_score": data.double_dummy_outcome.projected_score,
                },
                "is_opening_bid": is_opening_bid,
                "bid_infractions": list(data.bid_infractions),
            },
        )
        decision_feedback.append(bid_feedback)
        print(f"Coach: {bid_feedback['message']}")
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


# Function: _beats.
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


# Function: card_play_function.
def card_play_function(
    data: GameData,
    start_player: int,
    contract: Optional[Tuple[int, str, int, int]],
    coach: Coach,
    decision_feedback: List[Dict[str, Any]],
    input_fn: Callable[[str], str] = input,
) -> Dict[int, int]:
    """Play 13 tricks; trick winner starts next as in bridge."""
    hands = {player: list(data.curr_card_hold[player - 1]) for player in PLAYERS}
    tricks = {player: 0 for player in PLAYERS}
    leader = start_player
    trump = None if not contract or contract[1] == "NT" else contract[1]

    for trick_number in range(1, 14):
        order = [((leader - 1 + i) % 4) + 1 for i in range(4)]
        trick: List[Tuple[int, str]] = []
        lead_suit = None

        for position_in_trick, player in enumerate(order, start=1):
            recommendations = recommend_card_for_player(
                hand=hands[player],
                trick_cards=trick,
                contract=contract,
                bid_history=data.curr_bid_hist,
                strategy_answers=data.strat_dec.numeric_answers,
                player=player,
            )
            while True:
                prompt = (
                    f"Player {player}, play a card from your hand {hands[player]} "
                    "(or ? for model advice): "
                )
                card = input_fn(prompt).strip().upper()
                if card == "?":
                    if recommendations:
                        top = recommendations[0]
                        print(
                            "Model advice: "
                            f"{top['card']} (conf={top['confidence']:.2f}) - {top['reason']} "
                            f"rationale={top['rationale']}"
                        )
                    else:
                        print("Model advice unavailable for this decision.")
                    continue
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
            data.record_card_play(
                trick_number=trick_number,
                position_in_trick=position_in_trick,
                player=player,
                card=card,
                leader=order[0],
            )
            _immediate_deviation_feedback("card", card, recommendations)
            card_feedback = coach.explain_card_play(
                user_card=card,
                recommended_cards=recommendations,
                context={
                    "player": player,
                    "trick_number": sum(tricks.values()) + 1,
                    "trick_cards": list(trick),
                    "double_dummy": None if data.double_dummy_outcome is None else {
                        "contract": data.double_dummy_outcome.contract,
                        "expected_tricks": data.double_dummy_outcome.expected_tricks,
                    },
                },
            )
            decision_feedback.append(card_feedback)
            print(f"Coach: {card_feedback['message']}")

        winner, winning_card = trick[0]
        for player, card in trick[1:]:
            if _beats(card, winning_card, lead_suit, trump):
                winner, winning_card = player, card

        tricks[winner] += 1
        leader = winner
        print(f"Trick winner: Player {winner} with {winning_card}")

    return tricks


# Function: _overtrick_points.
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


# Function: _undertrick_penalty.
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


# Function: calc_point_function.
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


def _build_end_of_hand_report(
    data: GameData,
    contract: Optional[Tuple[int, str, int, int]],
    tricks: Dict[int, int],
    adjusted_points: Dict[int, int],
    decision_feedback: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    alternatives = [item for item in decision_feedback if item.get("suggested_alternative")]
    top_alternatives = alternatives[:5]
    projected = 0
    if data.double_dummy_outcome is not None:
        projected = int(data.double_dummy_outcome.projected_score)
    actual_side = 0
    if contract is not None:
        declarer = contract[2]
        pair = (1, 3) if declarer in (1, 3) else (2, 4)
        actual_side = adjusted_points[pair[0]]
    return {
        "contract": contract,
        "tricks": tricks,
        "adjusted_points": adjusted_points,
        "recommended_alternatives": [
            {
                "decision": item.get("decision"),
                "player": item.get("player"),
                "user_action": item.get("user_action"),
                "suggested_alternative": item.get("suggested_alternative"),
                "severity": item.get("severity"),
            }
            for item in top_alternatives
        ],
        "projected_score_impact": projected - actual_side,
    }


def _display_end_of_hand_report(report: Dict[str, Any]) -> None:
    print("\n=== End-of-Hand Coaching Report ===")
    print(f"Contract: {report.get('contract')}")
    print(f"Tricks won by seat: {report.get('tricks')}")
    print(f"Adjusted points: {report.get('adjusted_points')}")
    print(f"Projected score impact vs double-dummy target: {report.get('projected_score_impact')}")
    print("Recommended alternatives:")
    for alt in report.get("recommended_alternatives", []):
        print(
            f"  {alt.get('decision')} P{alt.get('player')} "
            f"{alt.get('user_action')} -> {alt.get('suggested_alternative')} "
            f"[{alt.get('severity')}]"
        )


def _make_scripted_input(scripted_actions: Sequence[str], live_input_fn: Callable[[str], str]) -> Callable[[str], str]:
    queue = [str(item).upper() for item in scripted_actions]

    def _inner(prompt: str) -> str:
        if queue:
            action = queue.pop(0)
            print(f"{prompt}{action}  [scripted]")
            return action
        return live_input_fn(prompt)

    return _inner


def _run_mode(
    mode: str,
    *,
    input_fn: Callable[[str], str],
    rng: random.Random | None,
    scenario_name: Optional[str],
) -> GameData:
    """Run one training mode: practice_bid, practice_play, or coach_full_hand."""
    data = GameData()
    if not data.strat_dec.numeric_answers:
        data.strat_dec.load(1)
    bidding_model = load_latest_stable_model(model_type="policy", task="bidding")
    cardplay_model = load_latest_stable_model(model_type="policy", task="cardplay")
    if bidding_model and bidding_model.get("_metadata"):
        meta = bidding_model["_metadata"]
        print(f"Loaded stable bidding model: {meta.get('version')} ({meta.get('artifact_path')})")
    if cardplay_model and cardplay_model.get("_metadata"):
        meta = cardplay_model["_metadata"]
        print(f"Loaded stable card-play model: {meta.get('version')} ({meta.get('artifact_path')})")
    scenario: Optional[Dict[str, Any]] = None
    if scenario_name:
        scenario = get_demo_scenario(scenario_name)
        start_positions, opening_player = preset_from_scenario(data, scenario)
        print(f"Loaded demo scenario '{scenario_name}': {scenario.get('description', '')}")
    else:
        start_positions, opening_player = preset(data, rng=rng)

    coach = Coach(strategy_profile=data.strat_dec.numeric_answers)
    decision_feedback: List[Dict[str, Any]] = []
    print(f"Starting order for this hand: {start_positions}")
    display_cards(data)

    bid_input_fn = input_fn
    play_input_fn = input_fn
    if scenario and scenario.get("scripted_auction"):
        bid_input_fn = _make_scripted_input(scenario["scripted_auction"], input_fn)
    if scenario and scenario.get("scripted_card_prefix"):
        play_input_fn = _make_scripted_input(scenario["scripted_card_prefix"], input_fn)

    contract: Optional[Tuple[int, str, int, int]] = None
    bid_state = "complete"
    if mode in {"practice_bid", "coach_full_hand"}:
        contract, bid_state = bid_function(data, start_positions, coach, decision_feedback, input_fn=bid_input_fn)
    if bid_state == "quit":
        print("Game ended by user during bidding.")
        return data
    if bid_state == "passed_out":
        print("All four players passed. No play, no points.")
        return data

    if mode == "practice_play":
        if scenario and scenario.get("scripted_contract"):
            c = scenario["scripted_contract"]
            contract = (int(c[0]), str(c[1]).upper(), int(c[2]), int(c[3]))
            print(f"Practice play using scripted contract: {contract}")
        else:
            contract = (3, "NT", opening_player, 1)
            print(f"Practice play default contract: {contract}")

    if contract is None:
        print("No contract available for card-play mode.")
        return data

    tricks = card_play_function(data, opening_player, contract, coach, decision_feedback, input_fn=play_input_fn)
    round_points = calc_point_function(contract, tricks, data.vulnerability)
    adjusted_points = dict(round_points)
    for player, penalty in data.penalty_points_by_player.items():
        adjusted_points[player] = adjusted_points.get(player, 0) - penalty

    hand_summary_feedback = coach.summarize_hand_feedback(
        decision_feedback,
        context={
            "contract": contract,
            "double_dummy": None if data.double_dummy_outcome is None else {
                "contract": data.double_dummy_outcome.contract,
                "declarer": data.double_dummy_outcome.declarer,
                "expected_tricks": data.double_dummy_outcome.expected_tricks,
                "projected_score": data.double_dummy_outcome.projected_score,
            },
            "bid_infractions": list(data.bid_infractions),
        },
    )
    print(f"Coach hand summary: {hand_summary_feedback['message']}")

    end_of_hand_report = _build_end_of_hand_report(data, contract, tricks, adjusted_points, decision_feedback)
    _display_end_of_hand_report(end_of_hand_report)

    data.round_result_payload = {
        "contract": contract,
        "tricks": tricks,
        "card_play_history": list(data.curr_card_play_hist),
        "base_points": round_points,
        "double_dummy_outcome": None if data.double_dummy_outcome is None else {
            "contract": data.double_dummy_outcome.contract,
            "declarer": data.double_dummy_outcome.declarer,
            "expected_tricks": data.double_dummy_outcome.expected_tricks,
            "projected_score": data.double_dummy_outcome.projected_score,
            "par_score": data.double_dummy_outcome.par_score,
            "contract_alternatives": data.double_dummy_outcome.contract_alternatives,
            "trick_table": data.double_dummy_outcome.trick_table,
            "solver_mode": data.double_dummy_outcome.solver_mode,
            "solver_name": data.double_dummy_outcome.solver_name,
            "is_heuristic": data.double_dummy_outcome.is_heuristic,
        },
        "penalty_points_by_player": dict(data.penalty_points_by_player),
        "cumulative_penalty_points": sum(data.penalty_points_by_player.values()),
        "penalty_reason_breakdown": dict(data.penalty_reason_breakdown),
        "infractions": list(data.bid_infractions),
        "decision_feedback": decision_feedback,
        "hand_summary_feedback": hand_summary_feedback,
        "structured_feedback": [
            {
                "mistake_type": item.get("mistake_type"),
                "severity": item.get("severity"),
                "suggested_alternative": item.get("suggested_alternative"),
                "learning_tip": item.get("learning_tip"),
                "decision": item.get("decision"),
                "player": item.get("player"),
                "user_action": item.get("user_action"),
            }
            for item in decision_feedback
        ] + [
            {
                "mistake_type": hand_summary_feedback.get("mistake_type"),
                "severity": hand_summary_feedback.get("severity"),
                "suggested_alternative": hand_summary_feedback.get("suggested_alternative"),
                "learning_tip": hand_summary_feedback.get("learning_tip"),
                "decision": hand_summary_feedback.get("decision"),
                "player": hand_summary_feedback.get("player"),
                "user_action": hand_summary_feedback.get("user_action"),
            }
        ],
        "adjusted_points": adjusted_points,
        "penalty_table": dict(MAJOR_INFRACTION_PENALTIES),
        "end_of_hand_report": end_of_hand_report,
    }

    data.add_round_points(adjusted_points)

    print(f"Round tricks: {tricks}")
    print(f"Round points (after penalties): {data.curr_points}")
    print(f"Round result payload: {data.round_result_payload}")
    print(f"Historical points: {data.hist_points}")
    return data


# Function: game.
def game(
    input_fn: Callable[[str], str] = input,
    rng: random.Random | None = None,
    mode: str = "coach_full_hand",
    scenario_name: Optional[str] = None,
) -> GameData:
    return _run_mode(mode, input_fn=input_fn, rng=rng, scenario_name=scenario_name)


def run_interactive_orchestrator(input_fn: Callable[[str], str] = input, rng: random.Random | None = None) -> None:
    """Single flow that can demonstrate all proposal outcomes in one session."""
    print("\nAvailable demo scenarios:")
    for key, desc in list_demo_scenarios().items():
        print(f"  - {key}: {desc}")
    scenario_name = input_fn("Scenario name (enter for random deal): ").strip() or None
    run_all = input_fn("Run all modes in one session? (y/n): ").strip().lower() == "y"

    selected_modes = ["practice_bid", "practice_play", "coach_full_hand"] if run_all else [
        input_fn("Mode [practice_bid/practice_play/coach_full_hand]: ").strip()
    ]
    for mode in selected_modes:
        print(f"\n--- Running mode: {mode} ---")
        _run_mode(mode, input_fn=input_fn, rng=rng, scenario_name=scenario_name)


if __name__ == "__main__":
    run_interactive_orchestrator()
