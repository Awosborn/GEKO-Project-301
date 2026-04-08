"""Training cycle with iterative co-training between bidding and card-play policies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from model_registry import load_latest_stable_model, promote_model_artifact
from train_bidding import _episodes_from_runner_records as bidding_from_runner
from train_bidding import _read_jsonl as read_bidding_jsonl
from train_bidding import train_bidding_model
from train_cardplay import _episodes_from_runner_records as cardplay_from_runner
from train_cardplay import _read_jsonl as read_cardplay_jsonl
from train_cardplay import train_cardplay_model


ROOT = Path(__file__).resolve().parent
DATASETS_DIR = ROOT / "datasets"
DEFAULT_CYCLES = 1000
TRICKS_TARGET = 6.0
RULE_BREAK_PENALTY = 400.0


def _bidding_validation_rows() -> List[Dict[str, Any]]:
    runner = bidding_from_runner(DATASETS_DIR / "runner_bidding_val.jsonl")
    return runner or read_bidding_jsonl(DATASETS_DIR / "val.jsonl")


def _cardplay_validation_rows() -> List[Dict[str, Any]]:
    runner = cardplay_from_runner(DATASETS_DIR / "runner_cardplay_val.jsonl")
    return runner or read_cardplay_jsonl(DATASETS_DIR / "val.jsonl")


def _runner_bidding_rows() -> List[Dict[str, Any]]:
    return read_bidding_jsonl(DATASETS_DIR / "runner_bidding_train.jsonl")


def _runner_cardplay_rows() -> List[Dict[str, Any]]:
    return read_cardplay_jsonl(DATASETS_DIR / "runner_cardplay_train.jsonl")


def _score_bidding_policy(mapping: Dict[str, str], rows: List[Dict[str, Any]]) -> float:
    wins = 0
    total = 0
    for episode in rows:
        for step in episode.get("auction_sequence", []):
            context = f"player={int(step.get('player', 1))}"
            expected = str(step.get("bid", "P")).upper()
            predicted = str(mapping.get(context, "P")).upper()
            total += 1
            if predicted == expected:
                wins += 1
    return 0.0 if total == 0 else wins / total


def _score_cardplay_policy(mapping: Dict[str, str], rows: List[Dict[str, Any]]) -> float:
    wins = 0
    total = 0
    for episode in rows:
        for step in episode.get("play_sequence", []):
            context = f"player={int(step.get('player', 1))}|trick={int(step.get('trick_index', 0))}"
            expected = str(step.get("card", "2C")).upper()
            predicted = str(mapping.get(context, "2C")).upper()
            total += 1
            if predicted == expected:
                wins += 1
    return 0.0 if total == 0 else wins / total


def _arena_result(candidate: float, champion: float) -> str:
    return "candidate" if candidate >= champion else "champion"


def _penalty_from_bidding_terminal(terminal: Dict[str, Any]) -> float:
    reward_components = dict(terminal.get("reward_components", {}))
    penalties = dict(terminal.get("penalties", {}))
    legality = dict(terminal.get("legality_flags", {}))

    explicit_penalty = float(reward_components.get("total_infraction_penalty", 0.0))
    if explicit_penalty > 0:
        return explicit_penalty

    penalty_total = sum(abs(float(v)) for v in penalties.values() if float(v) != 0.0)
    if penalty_total > 0:
        return penalty_total

    illegal_auction = not bool(legality.get("legal_auction", True))
    invalid_contract = not bool(legality.get("valid_contract", True))
    if illegal_auction or invalid_contract:
        return RULE_BREAK_PENALTY

    strategy_breaks = float(reward_components.get("strategy_break_count", 0.0))
    acbl_breaks = float(reward_components.get("acbl_break_count", 0.0))
    derived = (strategy_breaks + acbl_breaks) * RULE_BREAK_PENALTY
    return max(0.0, derived)


def _bidding_cycle_reward(
    step: Dict[str, Any],
    terminal: Dict[str, Any],
    cardplay_model: Dict[str, str],
) -> float:
    # Score component from card-play outcome (points) based on provided/derived score.
    points = float(terminal.get("score_delta", terminal.get("total_reward", 0.0)))

    # Strongly penalize rule breaking.
    rule_penalty = _penalty_from_bidding_terminal(terminal)

    # Credit for bids that align with the latest best card-play downstream model context.
    player = int(step.get("bidder", step.get("player", 1)))
    card_context = f"player={player}|trick=0"
    card_signal = 1.0 if card_context in cardplay_model else 0.0

    return points + card_signal - rule_penalty


def _cardplay_cycle_reward(
    step: Dict[str, Any],
    terminal: Dict[str, Any],
    bidding_model: Dict[str, str],
) -> float:
    # Positive shaping target: making at least 6 tricks should be positive.
    observed_tricks = float(terminal.get("observed_declarer_tricks", 0.0))
    trick_component = observed_tricks - TRICKS_TARGET

    points = float(terminal.get("observed_score", terminal.get("total_reward", 0.0)))

    # Include bidding-model signal, ensuring card play is trained using bidding outputs.
    seat = int(step.get("player", 1))
    bid_context = f"player={seat}"
    bid = str(bidding_model.get(bid_context, "P")).upper()
    bid_signal = 0.5 if bid not in {"P", "X", "XX", "Q"} else 0.0

    return points + trick_component + bid_signal


def _fit_bidding_policy_with_rewards(
    rows: List[Dict[str, Any]],
    cardplay_model: Dict[str, str],
) -> Dict[str, str]:
    weighted: Dict[str, Dict[str, float]] = {}
    for row in rows:
        terminal = dict(row.get("terminal", {}))
        for step in row.get("encoded_sequence", []):
            context = f"player={int(step.get('bidder', step.get('player', 1)))}"
            bid = str(step.get("bid", "P")).upper()
            reward = _bidding_cycle_reward(step, terminal, cardplay_model)
            weighted.setdefault(context, {})
            weighted[context][bid] = weighted[context].get(bid, 0.0) + reward

    top_bid_by_context: Dict[str, str] = {}
    for context, bid_scores in weighted.items():
        if not bid_scores:
            continue
        top_bid_by_context[context] = max(bid_scores.items(), key=lambda item: item[1])[0]
    return top_bid_by_context


def _fit_cardplay_policy_with_rewards(
    rows: List[Dict[str, Any]],
    bidding_model: Dict[str, str],
) -> Dict[str, str]:
    weighted: Dict[str, Dict[str, float]] = {}
    for row in rows:
        terminal = dict(row.get("terminal", {}))
        for step in row.get("encoded_sequence", []):
            context = f"player={int(step.get('player', 1))}|trick={int(step.get('trick_index', 0))}"
            card = str(step.get("card", "2C")).upper()
            reward = _cardplay_cycle_reward(step, terminal, bidding_model)
            weighted.setdefault(context, {})
            weighted[context][card] = weighted[context].get(card, 0.0) + reward

    top_card_by_context: Dict[str, str] = {}
    for context, card_scores in weighted.items():
        if not card_scores:
            continue
        top_card_by_context[context] = max(card_scores.items(), key=lambda item: item[1])[0]
    return top_card_by_context


def run_training_cycle(*, cycles: int = DEFAULT_CYCLES) -> Dict[str, Any]:
    total_cycles = max(1, int(cycles))
    previous_bidding = load_latest_stable_model(model_type="policy", task="bidding")
    previous_cardplay = load_latest_stable_model(model_type="policy", task="cardplay")

    champion_bidding_map = {} if not previous_bidding else dict(previous_bidding.get("top_bid_by_context", {}))
    champion_cardplay_map = {} if not previous_cardplay else dict(previous_cardplay.get("top_card_by_context", {}))

    bidding_runner_rows = _runner_bidding_rows()
    cardplay_runner_rows = _runner_cardplay_rows()

    for _ in range(total_cycles):
        # Train bidding from double-dummy/terminal outcomes against latest best opponents.
        candidate_bidding_map = _fit_bidding_policy_with_rewards(bidding_runner_rows, champion_cardplay_map)

        # Train card-play using input from bidding model and six-trick-positive shaping.
        candidate_cardplay_map = _fit_cardplay_policy_with_rewards(cardplay_runner_rows, candidate_bidding_map)

        # Re-train bidding using outcomes after running with candidate card play.
        refreshed_bidding_map = _fit_bidding_policy_with_rewards(bidding_runner_rows, candidate_cardplay_map)

        # Re-train card play again from refreshed bidding model.
        refreshed_cardplay_map = _fit_cardplay_policy_with_rewards(cardplay_runner_rows, refreshed_bidding_map)

        champion_bidding_map = refreshed_bidding_map or champion_bidding_map
        champion_cardplay_map = refreshed_cardplay_map or champion_cardplay_map

    candidate_bidding = train_bidding_model(
        stable=False,
        notes=(
            "Candidate from iterative bidding/card-play co-training cycle with double-dummy reward shaping, "
            f"{total_cycles} iterations, and heavy rule-break penalties."
        ),
    )
    candidate_cardplay = train_cardplay_model(
        stable=False,
        notes=(
            "Candidate from iterative bidding/card-play co-training cycle using bidding-input conditioning, "
            f"{total_cycles} iterations, six-trick-positive shaping, and point rewards."
        ),
    )

    # Override baseline frequency mappings with cyclic, reward-shaped mappings.
    candidate_bidding["artifact"]["top_bid_by_context"] = champion_bidding_map
    candidate_cardplay["artifact"]["top_card_by_context"] = champion_cardplay_map

    bidding_rows = _bidding_validation_rows()
    cardplay_rows = _cardplay_validation_rows()

    candidate_bid_score = _score_bidding_policy(champion_bidding_map, bidding_rows)
    champion_bid_score = _score_bidding_policy(
        {} if not previous_bidding else previous_bidding.get("top_bid_by_context", {}),
        bidding_rows,
    )
    bidding_winner = _arena_result(candidate_bid_score, champion_bid_score)

    candidate_card_score = _score_cardplay_policy(champion_cardplay_map, cardplay_rows)
    champion_card_score = _score_cardplay_policy(
        {} if not previous_cardplay else previous_cardplay.get("top_card_by_context", {}),
        cardplay_rows,
    )
    cardplay_winner = _arena_result(candidate_card_score, champion_card_score)

    promoted: Dict[str, bool] = {"bidding": False, "cardplay": False}
    if bidding_winner == "candidate":
        promoted["bidding"] = promote_model_artifact(
            model_type="policy",
            task="bidding",
            version=str(candidate_bidding["metadata"]["version"]),
        )
    if cardplay_winner == "candidate":
        promoted["cardplay"] = promote_model_artifact(
            model_type="policy",
            task="cardplay",
            version=str(candidate_cardplay["metadata"]["version"]),
        )

    return {
        "cycles": total_cycles,
        "candidates": {
            "bidding": candidate_bidding["metadata"],
            "cardplay": candidate_cardplay["metadata"],
        },
        "arena": {
            "bidding": {
                "candidate_score": candidate_bid_score,
                "champion_score": champion_bid_score,
                "winner": bidding_winner,
                "promoted": promoted["bidding"],
            },
            "cardplay": {
                "candidate_score": candidate_card_score,
                "champion_score": champion_card_score,
                "winner": cardplay_winner,
                "promoted": promoted["cardplay"],
            },
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_training_cycle(), indent=2))
