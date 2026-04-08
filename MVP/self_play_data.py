"""Generate runner training datasets via simple self-play episodes."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List

from RunnerBiddingModel import AuctionEpisodeRunner
from RunnerCardPlayModel import CardPlayEpisodeRunner


ROOT = Path(__file__).resolve().parent
DATASETS_DIR = ROOT / "datasets"
_BID_CHOICES = ["P", "X", "XX"] + [f"{level}{suit}" for level in range(1, 8) for suit in ("C", "D", "H", "S", "NT")]


def _write_jsonl(path: Path, rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _safe_train_count(total: int, train_ratio: float) -> int:
    if total <= 1:
        return total
    raw = int(total * train_ratio)
    return min(total - 1, max(1, raw))


def generate_self_play_datasets(*, hands: int = 200, seed: int = 301, train_ratio: float = 0.8) -> Dict[str, int]:
    """Create runner_bidding/cardplay train+val files by having agents play themselves."""
    total_hands = max(2, int(hands))
    rng = random.Random(seed)

    bidding_runner = AuctionEpisodeRunner(focus_player=1)
    cardplay_runner = CardPlayEpisodeRunner(focus_player=1)

    bidding_rows: List[Dict[str, object]] = []
    cardplay_rows: List[Dict[str, object]] = []

    for index in range(total_hands):
        epoch_id = f"self-play-{index + 1:05d}"
        board_id = f"board-{index + 1:05d}"
        strategy_answers = [rng.randint(0, 2) for _ in range(12)]

        # Auction self-play (all four seats produced from same policy family).
        bidding_runner.start_epoch(
            epoch_id=epoch_id,
            strategy_answers=strategy_answers,
            board_hand_id=board_id,
            strategy_profile_name="self_play",
            strategy_profile_version="v1",
        )
        auction_len = rng.randint(4, 12)
        bidder = 1
        last_non_pass = "1C"
        for _ in range(auction_len):
            bid = rng.choice(_BID_CHOICES)
            if bid not in {"P", "X", "XX"}:
                last_non_pass = bid
            bidding_runner.record_bid_step(
                player=bidder,
                bid=bid,
                strategy_answers=strategy_answers,
                context_features={"aggression": float(strategy_answers[0]), "tempo": float(strategy_answers[1])},
            )
            bidder = 1 + (bidder % 4)

        expected_tricks = rng.randint(6, 11)
        projected_score = rng.randint(-400, 620)
        observed_score = projected_score + rng.randint(-120, 120)
        bidding_rows.append(
            bidding_runner.close_auction_and_learn(
                final_contract=last_non_pass,
                reward_components={
                    "score_delta": float(observed_score - projected_score),
                    "observed_score": float(observed_score),
                    "strategy_break_count": float(rng.randint(0, 1)),
                    "acbl_break_count": 0.0,
                    "total_infraction_penalty": 0.0,
                    "valid_contract": 1.0,
                    "legal_auction": 1.0,
                },
                double_dummy_target={
                    "contract": last_non_pass,
                    "declarer": 1,
                    "expected_tricks": expected_tricks,
                    "projected_score": projected_score,
                    "par_score": projected_score,
                    "contract_alternatives": [{"contract": last_non_pass, "projected_score": projected_score}],
                    "solver_mode": "self_play",
                    "is_heuristic": False,
                },
            )
        )

        # Card-play self-play (same agent family on every seat).
        cardplay_runner.start_epoch(
            epoch_id=epoch_id,
            strategy_answers=strategy_answers,
            board_hand_id=board_id,
            strategy_profile_name="self_play",
            strategy_profile_version="v1",
        )
        for step_idx in range(52):
            player = 1 + (step_idx % 4)
            trick_index = step_idx // 4
            rank = rng.choice(["A", "K", "Q", "J", "10", "9", "8", "7", "6", "5", "4", "3", "2"])
            suit = rng.choice(["C", "D", "H", "S"])
            card = f"{rank}{suit}"
            cardplay_runner.record_card_step(
                player=player,
                card=card,
                strategy_answers=strategy_answers,
                trick_index=trick_index,
                legal_cards=[card],
                context_features={"tempo": float(strategy_answers[2]), "plan": float(strategy_answers[3])},
            )

        observed_tricks = rng.randint(5, 11)
        card_score = rng.randint(-500, 700)
        dd_score = card_score + rng.randint(-100, 100)
        cardplay_rows.append(
            cardplay_runner.close_hand_and_learn(
                observed_declarer_tricks=observed_tricks,
                observed_score=float(card_score),
                double_dummy_target={
                    "expected_tricks": float(expected_tricks),
                    "projected_score": float(dd_score),
                    "par_score": float(dd_score),
                    "solver_mode": "self_play",
                    "is_heuristic": False,
                },
            )
        )

    train_count = _safe_train_count(total_hands, train_ratio)
    _write_jsonl(DATASETS_DIR / "runner_bidding_train.jsonl", bidding_rows[:train_count])
    _write_jsonl(DATASETS_DIR / "runner_bidding_val.jsonl", bidding_rows[train_count:])
    _write_jsonl(DATASETS_DIR / "runner_cardplay_train.jsonl", cardplay_rows[:train_count])
    _write_jsonl(DATASETS_DIR / "runner_cardplay_val.jsonl", cardplay_rows[train_count:])

    return {
        "hands": total_hands,
        "train_examples": train_count,
        "validation_examples": total_hands - train_count,
        "seed": seed,
    }


if __name__ == "__main__":
    print(json.dumps(generate_self_play_datasets(), indent=2))
