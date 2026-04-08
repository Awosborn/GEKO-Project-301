"""Training cycle with arena evaluation vs previously best stable models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from model_registry import (
    load_latest_stable_model,
    promote_model_artifact,
)
from train_bidding import _episodes_from_runner_records as bidding_from_runner
from train_bidding import _read_jsonl as read_bidding_jsonl
from train_bidding import train_bidding_model
from train_cardplay import _episodes_from_runner_records as cardplay_from_runner
from train_cardplay import _read_jsonl as read_cardplay_jsonl
from train_cardplay import train_cardplay_model


ROOT = Path(__file__).resolve().parent
DATASETS_DIR = ROOT / "datasets"


def _bidding_validation_rows() -> List[Dict[str, Any]]:
    runner = bidding_from_runner(DATASETS_DIR / "runner_bidding_val.jsonl")
    return runner or read_bidding_jsonl(DATASETS_DIR / "val.jsonl")


def _cardplay_validation_rows() -> List[Dict[str, Any]]:
    runner = cardplay_from_runner(DATASETS_DIR / "runner_cardplay_val.jsonl")
    return runner or read_cardplay_jsonl(DATASETS_DIR / "val.jsonl")


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


def run_training_cycle() -> Dict[str, Any]:
    previous_bidding = load_latest_stable_model(model_type="policy", task="bidding")
    previous_cardplay = load_latest_stable_model(model_type="policy", task="cardplay")

    candidate_bidding = train_bidding_model(stable=False, notes="Candidate from self-play training cycle.")
    candidate_cardplay = train_cardplay_model(stable=False, notes="Candidate from self-play training cycle.")

    bidding_rows = _bidding_validation_rows()
    cardplay_rows = _cardplay_validation_rows()

    candidate_bid_score = _score_bidding_policy(candidate_bidding["artifact"].get("top_bid_by_context", {}), bidding_rows)
    champion_bid_score = _score_bidding_policy(
        {} if not previous_bidding else previous_bidding.get("top_bid_by_context", {}),
        bidding_rows,
    )
    bidding_winner = _arena_result(candidate_bid_score, champion_bid_score)

    candidate_card_score = _score_cardplay_policy(candidate_cardplay["artifact"].get("top_card_by_context", {}), cardplay_rows)
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
