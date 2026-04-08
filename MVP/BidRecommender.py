"""Bid recommendation flow for MVP coaching and future ML extension.

This module provides:
1) a rule-based baseline recommender for immediate coaching value,
2) a pluggable model interface for future near-expert upgrades,
3) top-k ranked bid outputs with confidence and reasoning metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

from BiddingModel import BID_VOCAB, BridgeBiddingModel
from RunnerBiddingModel import AuctionEpisodeRunner


TRUMP_ORDER = {"C": 0, "D": 1, "H": 2, "S": 3, "NT": 4}


# Data container: BidRecommendation.
@dataclass(frozen=True)
# Class: BidRecommendation.
class BidRecommendation:
    """One ranked bid recommendation with confidence and reason text."""

    bid: str
    confidence: float
    reason: str


# Interface: BidRankingModel.
class BidRankingModel(Protocol):
    """Pluggable ML model interface for future bidding-policy upgrades."""

    # Function: rank_bids.
    def rank_bids(self, features: Dict[str, object], legal_bids: Sequence[str]) -> List[BidRecommendation]:
        """Return ranked legal bids for the current state."""


# Class: HeuristicBaselineBidPolicy.
class HeuristicBaselineBidPolicy:
    """Simple rule-based policy intended as MVP phase-1 baseline."""

    # Function: _hand_hcp.
    def _hand_hcp(self, hand: Sequence[str]) -> int:
        hcp_map = {"A": 4, "K": 3, "Q": 2, "J": 1}
        return sum(hcp_map.get(card[:-1], 0) for card in hand)

    # Function: _suit_lengths.
    def _suit_lengths(self, hand: Sequence[str]) -> Dict[str, int]:
        lengths = {suit: 0 for suit in ("C", "D", "H", "S")}
        for card in hand:
            lengths[card[-1]] += 1
        return lengths

    # Function: _is_auction_opening_for_side.
    def _is_auction_opening_for_side(self, bid_history: Sequence[Sequence[Optional[str]]], seat: int) -> bool:
        side = 0 if seat in (1, 3) else 1
        for row in bid_history:
            for bidder, bid in enumerate(row, start=1):
                if not bid or bid == "P":
                    continue
                bidder_side = 0 if bidder in (1, 3) else 1
                if bidder_side == side:
                    return False
        return True

    # Function: _preferred_opening_bid.
    def _preferred_opening_bid(self, hand: Sequence[str]) -> Tuple[str, str]:
        hcp = self._hand_hcp(hand)
        suit_lengths = self._suit_lengths(hand)
        best_major = "S" if suit_lengths["S"] >= suit_lengths["H"] else "H"
        best_minor = "D" if suit_lengths["D"] >= suit_lengths["C"] else "C"

        if 15 <= hcp <= 17 and max(suit_lengths.values()) <= 5:
            return "1NT", "Balanced 15-17 HCP profile points to a 1NT opening."
        if suit_lengths["S"] >= 5 or suit_lengths["H"] >= 5:
            return f"1{best_major}", "5+ card major with opening values suggests a 1-major opening."
        return f"1{best_minor}", "No 5-card major; choose a natural 1-minor opening."

    # Function: rank_bids.
    def rank_bids(self, features: Dict[str, object], legal_bids: Sequence[str]) -> List[BidRecommendation]:
        hand = features.get("hand", [])
        bid_history = features.get("bid_history", [])
        seat = int(features.get("seat", 1))
        vulnerability = bool(features.get("vulnerability", False))

        if not isinstance(hand, list):
            hand = []
        if not isinstance(bid_history, list):
            bid_history = []

        hcp = self._hand_hcp(hand)
        is_opening_for_side = self._is_auction_opening_for_side(bid_history, seat)

        scored: List[BidRecommendation] = []
        if is_opening_for_side:
            opening_bid, opening_reason = self._preferred_opening_bid(hand)
            if opening_bid in legal_bids:
                scored.append(
                    BidRecommendation(
                        bid=opening_bid,
                        confidence=0.72 if not vulnerability else 0.68,
                        reason=opening_reason,
                    )
                )

        pass_confidence = 0.80 if hcp < 11 else 0.55 if hcp < 13 else 0.35
        scored.append(
            BidRecommendation(
                bid="P",
                confidence=pass_confidence,
                reason="Conservative baseline fallback while auction/fit information is limited.",
            )
        )

        if hcp >= 13:
            for candidate in ("1C", "1D", "1H", "1S", "1NT"):
                if candidate in legal_bids and candidate not in {rec.bid for rec in scored}:
                    scored.append(
                        BidRecommendation(
                            bid=candidate,
                            confidence=0.42,
                            reason="Opening values present; this is a secondary natural call option.",
                        )
                    )

        legal_missing = [bid for bid in legal_bids if bid not in {rec.bid for rec in scored}]
        for bid in legal_missing:
            scored.append(
                BidRecommendation(
                    bid=bid,
                    confidence=0.1,
                    reason="Legal but low-priority under current baseline heuristics.",
                )
            )

        return sorted(scored, key=lambda item: item.confidence, reverse=True)


# Class: BidRecommender.
class BidRecommender:
    """Feature builder + policy adapter returning ranked top-k bid candidates."""

    # Function: __init__.
    def __init__(
        self,
        *,
        policy: Optional[BidRankingModel] = None,
        top_k_default: int = 3,
    ) -> None:
        self.encoder = BridgeBiddingModel(focus_player=1)
        self.episode_encoder = AuctionEpisodeRunner(focus_player=1)
        self.policy: BidRankingModel = policy or HeuristicBaselineBidPolicy()
        self.top_k_default = top_k_default

    # Function: _partnership.
    def _partnership(self, player: int) -> int:
        return 0 if player in (1, 3) else 1

    # Function: _bid_rank.
    def _bid_rank(self, bid: str) -> Optional[int]:
        clean = bid.strip().upper()
        if clean in {"P", "X", "XX"}:
            return None
        return (int(clean[0]) - 1) * 5 + TRUMP_ORDER[clean[1:]]

    # Function: _last_contract.
    def _last_contract(self, bid_history: Sequence[Sequence[Optional[str]]]) -> Optional[str]:
        last_contract_bid: Optional[str] = None
        for row in bid_history:
            for bid in row:
                if bid is None:
                    continue
                clean = bid.strip().upper()
                if clean not in {"P", "X", "XX"}:
                    last_contract_bid = clean
        return last_contract_bid

    # Function: _legal_bids.
    def _legal_bids(self, bid_history: Sequence[Sequence[Optional[str]]]) -> List[str]:
        legal = ["P"]
        last_contract = self._last_contract(bid_history)
        threshold = self._bid_rank(last_contract) if last_contract else None
        for bid in BID_VOCAB:
            if bid in {"P", "X", "XX"}:
                continue
            rank = self._bid_rank(bid)
            if threshold is None or (rank is not None and rank > threshold):
                legal.append(bid)
        return legal

    # Function: recommend_bid.
    def recommend_bid(
        self,
        hand: Sequence[str],
        bid_history: Sequence[Sequence[Optional[str]]],
        strategy_answers: Sequence[float],
        seat: int,
        vulnerability: bool,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, object]]:
        """Return ranked top-k bid recommendations for coaching and policy hooks."""
        if seat not in (1, 2, 3, 4):
            raise ValueError("seat must be one of 1, 2, 3, 4")

        self.encoder.focus_player = seat
        self.episode_encoder.focus_player = seat

        bid_context = self.encoder.next_bid_context(bid_history)
        strategy_vector = [float(value) for value in strategy_answers] if strategy_answers else []
        strategy_features = self.episode_encoder._encode_strategy_answers(strategy_vector)

        legal_bids = self._legal_bids(bid_history)
        feature_payload: Dict[str, object] = {
            "hand": list(hand),
            "seat": seat,
            "vulnerability": bool(vulnerability),
            "bid_history": [list(row) for row in bid_history],
            "bid_context": bid_context,
            "sequence_length": bid_context["sequence_length"],
            "strategy_answers": strategy_vector,
            "strategy_features": strategy_features,
            "partnership": self._partnership(seat),
        }

        ranked = self.policy.rank_bids(feature_payload, legal_bids)
        k = top_k if top_k is not None else self.top_k_default

        return [
            {
                "bid": rec.bid,
                "confidence": round(float(rec.confidence), 4),
                "reason": rec.reason,
                "rank": idx + 1,
            }
            for idx, rec in enumerate(ranked[: max(1, k)])
        ]


_DEFAULT_RECOMMENDER = BidRecommender()


# Function: recommend_bid.
def recommend_bid(
    hand: Sequence[str],
    bid_history: Sequence[Sequence[Optional[str]]],
    strategy_answers: Sequence[float],
    seat: int,
    vulnerability: bool,
) -> List[Dict[str, object]]:
    """Module-level convenience wrapper required by MVP integration."""
    return _DEFAULT_RECOMMENDER.recommend_bid(
        hand=hand,
        bid_history=bid_history,
        strategy_answers=strategy_answers,
        seat=seat,
        vulnerability=vulnerability,
    )
