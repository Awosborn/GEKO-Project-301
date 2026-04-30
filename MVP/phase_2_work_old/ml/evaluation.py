"""Evaluation suite for next-action models."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Dict, List, Mapping, Sequence

from .masks import is_legal_bid, legal_cards


def _top_k_indices(scores: Sequence[float], k: int) -> List[int]:
    return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]


def classification_metrics(
    probs: Sequence[Sequence[float]],
    labels: Sequence[int],
    *,
    top_k_values: Sequence[int] = (1, 3, 5),
    eps: float = 1e-12,
) -> Dict[str, float]:
    if not labels:
        empty = {"count": 0.0, "nll": 0.0, "cross_entropy": 0.0}
        for k in top_k_values:
            empty[f"top_{int(k)}_accuracy"] = 0.0
        return empty

    k_hits = {int(k): 0 for k in top_k_values}
    nll = 0.0
    for row_probs, target in zip(probs, labels):
        sorted_indices = _top_k_indices(row_probs, max(top_k_values))
        for k in top_k_values:
            if int(target) in sorted_indices[: int(k)]:
                k_hits[int(k)] += 1
        p_target = float(row_probs[int(target)]) if int(target) < len(row_probs) else 0.0
        nll += -math.log(max(p_target, eps))

    denom = float(len(labels))
    metrics: Dict[str, float] = {"count": denom, "nll": nll / denom, "cross_entropy": nll / denom}
    for k, hits in k_hits.items():
        metrics[f"top_{k}_accuracy"] = float(hits) / denom
    return metrics


def bid_confusion_report(y_true: Sequence[int], y_pred: Sequence[int], id_to_label: Mapping[int, str]) -> Dict[str, object]:
    confusion: Dict[str, int] = defaultdict(int)
    for true_id, pred_id in zip(y_true, y_pred):
        if int(true_id) == int(pred_id):
            continue
        key = f"{id_to_label[int(true_id)]}->{id_to_label[int(pred_id)]}"
        confusion[key] += 1
    most_common = sorted(confusion.items(), key=lambda kv: kv[1], reverse=True)[:20]
    return {"total_errors": int(sum(confusion.values())), "top_confusions": [{"pair": k, "count": v} for k, v in most_common]}


def bid_legality_error_buckets(
    rows: Sequence[Mapping[str, object]],
    y_true: Sequence[int],
    y_pred: Sequence[int],
    id_to_label: Mapping[int, str],
) -> Dict[str, int]:
    buckets = Counter({"legal_correct": 0, "legal_incorrect": 0, "illegal_prediction": 0})
    for row, true_id, pred_id in zip(rows, y_true, y_pred):
        pred_bid = id_to_label[int(pred_id)]
        is_legal = is_legal_bid(
            pred_bid,
            seat_to_act=int(row.get("seat_to_act", 0)),
            bid_prefix=[str(x) for x in row.get("bid_prefix", [])],
        )
        if not is_legal:
            buckets["illegal_prediction"] += 1
        elif int(true_id) == int(pred_id):
            buckets["legal_correct"] += 1
        else:
            buckets["legal_incorrect"] += 1
    return dict(buckets)


def card_error_buckets(
    rows: Sequence[Mapping[str, object]],
    y_true: Sequence[int],
    y_pred: Sequence[int],
    id_to_label: Mapping[int, str],
) -> Dict[str, object]:
    legality = Counter({"legal_correct": 0, "legal_incorrect": 0, "illegal_prediction": 0})
    trick_stage = Counter({"lead": 0, "second": 0, "third": 0, "fourth": 0})
    for row, true_id, pred_id in zip(rows, y_true, y_pred):
        play_prefix = row.get("play_prefix", [])
        cards_played = len(play_prefix) if isinstance(play_prefix, list) else 0
        stage = cards_played % 4
        stage_name = ["lead", "second", "third", "fourth"][stage]
        trick_stage[stage_name] += 1

        trick_cards = [str(x.get("card", "")) for x in (play_prefix if isinstance(play_prefix, list) else []) if isinstance(x, dict)]
        trick_cards = trick_cards[-(cards_played % 4) :] if cards_played % 4 else []
        predicted = id_to_label[int(pred_id)]
        legal = set(legal_cards(hand_cards=[str(x) for x in row.get("hand_cards", [])], trick_cards=trick_cards))
        if predicted not in legal:
            legality["illegal_prediction"] += 1
        elif int(true_id) == int(pred_id):
            legality["legal_correct"] += 1
        else:
            legality["legal_incorrect"] += 1
    return {"card_legality": dict(legality), "trick_stage": dict(trick_stage)}
