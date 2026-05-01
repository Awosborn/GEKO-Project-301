"""Helpers for checking and ranking candidate bids."""

from __future__ import annotations

from typing import Any, Iterable, List

from .bridge_rules import normalize_call


def candidate_to_bid(candidate: Any) -> str:
    """Extract a bid string from a string, dict, or Pydantic candidate model."""
    if isinstance(candidate, str):
        return candidate
    if isinstance(candidate, dict):
        return str(candidate.get("bid", ""))
    return str(getattr(candidate, "bid", ""))


def candidate_score(candidate: Any) -> float:
    """Extract a candidate score, defaulting to 0.0."""
    if isinstance(candidate, dict):
        return float(candidate.get("score") or 0.0)
    return float(getattr(candidate, "score", 0.0) or 0.0)


def top_candidate_bids(candidates: Iterable[Any], limit: int = 3) -> List[str]:
    """Return normalized bid strings for the top candidates."""
    return [normalize_call(candidate_to_bid(item)) for item in list(candidates)[:limit]]


def user_bid_in_top_n(user_bid: str, candidates: Iterable[Any], n: int = 3) -> bool:
    """Check whether the user's bid appears in the top N candidate bids."""
    normalized_user = normalize_call(user_bid)
    return normalized_user in top_candidate_bids(candidates, n)


def rank_candidate_bids(candidates: Iterable[Any]) -> List[Any]:
    """Rank candidates with score fields descending. Unscored candidates keep order."""
    candidate_list = list(candidates)
    if not any(candidate_score(item) for item in candidate_list):
        return candidate_list
    return sorted(candidate_list, key=candidate_score, reverse=True)


def recommended_bid(candidates: Iterable[Any]) -> str | None:
    """Return the best candidate bid, if present."""
    ranked = rank_candidate_bids(candidates)
    if not ranked:
        return None
    return normalize_call(candidate_to_bid(ranked[0]))
