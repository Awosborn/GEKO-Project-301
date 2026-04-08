"""Training/evaluation metrics for bidding and card-play policies."""

from __future__ import annotations

from typing import Dict, Iterable, Sequence


def bid_accuracy(predicted_bids: Sequence[str], expert_bids: Sequence[str]) -> float:
    if not expert_bids:
        return 0.0
    matches = sum(1 for pred, true in zip(predicted_bids, expert_bids) if pred == true)
    return matches / len(expert_bids)


def trick_delta_vs_double_dummy(observed_tricks: Sequence[float], dd_tricks: Sequence[float]) -> float:
    if not observed_tricks:
        return 0.0
    deltas = [obs - tgt for obs, tgt in zip(observed_tricks, dd_tricks)]
    return sum(deltas) / len(deltas)


def proxy_imp_score(score_deltas: Iterable[float]) -> float:
    deltas = list(score_deltas)
    if not deltas:
        return 0.0
    # Light-weight proxy: scale average score delta into IMP-like unit.
    return sum(deltas) / (len(deltas) * 20.0)


def proxy_mp_score(board_scores: Sequence[float]) -> float:
    if not board_scores:
        return 0.0
    ranked = sorted(board_scores)
    total = 0.0
    for score in board_scores:
        wins = sum(1 for other in ranked if score > other)
        ties = sum(1 for other in ranked if score == other) - 1
        total += wins + 0.5 * max(0, ties)
    max_points = max(1.0, len(board_scores) - 1)
    return total / (len(board_scores) * max_points)


def summarize_training_metrics(
    *,
    bid_acc: float,
    trick_delta: float,
    imp_proxy: float,
    mp_proxy: float,
) -> Dict[str, float]:
    return {
        "bid_accuracy": round(float(bid_acc), 6),
        "trick_delta_vs_double_dummy": round(float(trick_delta), 6),
        "imp_proxy_score": round(float(imp_proxy), 6),
        "mp_proxy_score": round(float(mp_proxy), 6),
    }
