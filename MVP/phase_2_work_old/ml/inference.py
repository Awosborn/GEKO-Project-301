"""Legality-constrained inference helpers for next-action models."""

from __future__ import annotations

from typing import Dict, List, Mapping, Sequence

from .masks import legal_bids, legal_cards
from .normalize import normalize_bid, normalize_card


def _sorted_labels_from_scores(label_scores: Mapping[str, float]) -> List[str]:
    return [label for label, _ in sorted(label_scores.items(), key=lambda kv: kv[1], reverse=True)]


def recommend_next_bid(
    label_scores: Mapping[str, float],
    *,
    seat_to_act: int,
    bid_prefix: Sequence[str],
    top_k: int = 3,
) -> List[Dict[str, float | str]]:
    """Return top-k bidding recommendations filtered to legal actions only."""
    legal = set(legal_bids(seat_to_act=seat_to_act, bid_prefix=bid_prefix))
    ranked = _sorted_labels_from_scores(label_scores)
    filtered = [label for label in ranked if normalize_bid(label) in legal]
    if not filtered:
        fallback = sorted(legal)
        filtered = fallback

    out: List[Dict[str, float | str]] = []
    for label in filtered[:max(1, top_k)]:
        out.append({"bid": normalize_bid(label), "score": float(label_scores.get(label, float("-inf")))})
    return out


def recommend_next_card(
    label_scores: Mapping[str, float],
    *,
    hand_cards: Sequence[str],
    trick_cards: Sequence[str],
    top_k: int = 3,
) -> List[Dict[str, float | str]]:
    """Return top-k card recommendations filtered to legal playable cards."""
    legal = set(legal_cards(hand_cards=hand_cards, trick_cards=trick_cards))
    ranked = _sorted_labels_from_scores(label_scores)
    filtered = [label for label in ranked if normalize_card(label) in legal]
    if not filtered:
        filtered = sorted(legal)

    out: List[Dict[str, float | str]] = []
    for label in filtered[:max(1, top_k)]:
        out.append({"card": normalize_card(label), "score": float(label_scores.get(label, float("-inf")))})
    return out

