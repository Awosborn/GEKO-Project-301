"""Card-play recommendation utilities for MVP coaching and model hand-off.

This module mirrors the bid recommender structure:
1) build model-consistent encodings via CardPlayModel/RunnerCardPlayModel,
2) enforce legality first (follow-suit constraints),
3) rank only legal cards with rationale metadata for coaching text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

from CardPlayModel import BridgeCardPlayModel
from RunnerCardPlayModel import CardPlayEpisodeRunner
from Data import RANKS, SUITS


RANK_ORDER = {rank: idx for idx, rank in enumerate(RANKS)}


# Data container: CardRecommendation.
@dataclass(frozen=True)
# Class: CardRecommendation.
class CardRecommendation:
    """One legal-card recommendation with confidence and coaching rationale."""

    card: str
    confidence: float
    reason: str
    rationale: Dict[str, object]


# Interface: CardRankingModel.
class CardRankingModel(Protocol):
    """Pluggable interface for future trained card-policy models."""

    # Function: rank_cards.
    def rank_cards(
        self,
        features: Dict[str, object],
        legal_cards: Sequence[str],
    ) -> List[CardRecommendation]:
        """Rank legal cards for the current trick decision."""


# Class: HeuristicBaselineCardPolicy.
class HeuristicBaselineCardPolicy:
    """Rule baseline that emits interpretable rationale tags for coaching."""

    # Function: _contract_trump.
    def _contract_trump(self, contract: Optional[Tuple[int, str, int, int]]) -> Optional[str]:
        if not contract:
            return None
        denomination = str(contract[1]).upper()
        return None if denomination == "NT" else denomination

    # Function: _is_winning_candidate.
    def _is_winning_candidate(
        self,
        candidate: str,
        trick_cards: Sequence[Tuple[int, str]],
        trump: Optional[str],
    ) -> bool:
        if not trick_cards:
            return True
        lead_suit = trick_cards[0][1][-1]
        winning = trick_cards[0][1]
        for _, card in trick_cards[1:]:
            if self._beats(card, winning, lead_suit, trump):
                winning = card
        return self._beats(candidate, winning, lead_suit, trump)

    # Function: _beats.
    def _beats(self, card: str, best: str, lead_suit: str, trump: Optional[str]) -> bool:
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

    # Function: rank_cards.
    def rank_cards(
        self,
        features: Dict[str, object],
        legal_cards: Sequence[str],
    ) -> List[CardRecommendation]:
        trick_cards = features.get("trick_cards", [])
        contract = features.get("contract")
        trump = self._contract_trump(contract if isinstance(contract, tuple) else None)
        legal_sorted = sorted(legal_cards, key=lambda c: RANK_ORDER[c[:-1]], reverse=True)

        ranked: List[CardRecommendation] = []
        for card in legal_sorted:
            rank_idx = RANK_ORDER[card[:-1]]
            is_winner = self._is_winning_candidate(card, trick_cards, trump)
            top_honor = rank_idx >= RANK_ORDER["Q"]
            score = 0.35 + (0.25 if is_winner else 0.0) + (0.15 if top_honor else 0.0)

            if is_winner and not top_honor:
                reason = "Safety play: likely wins while conserving higher honors."
                rationale = {
                    "plan": "safety_play",
                    "maximize_tricks": True,
                    "preserve_entries": True,
                }
            elif is_winner and top_honor:
                reason = "Maximize tricks now by cashing a probable winner."
                rationale = {
                    "plan": "maximize_tricks",
                    "maximize_tricks": True,
                    "preserve_entries": False,
                }
            elif not is_winner and top_honor:
                reason = "Preserve entries: avoid spending top honors on a likely losing trick."
                rationale = {
                    "plan": "preserve_entries",
                    "maximize_tricks": False,
                    "preserve_entries": True,
                }
            else:
                reason = "Low-risk continuation card under current trick pressure."
                rationale = {
                    "plan": "safety_play",
                    "maximize_tricks": False,
                    "preserve_entries": True,
                }

            ranked.append(
                CardRecommendation(
                    card=card,
                    confidence=min(0.95, round(score, 4)),
                    reason=reason,
                    rationale=rationale,
                )
            )

        ranked.sort(key=lambda item: item.confidence, reverse=True)
        return ranked


# Class: CardPlayRecommender.
class CardPlayRecommender:
    """Feature builder + legal filter + ranking adapter for card-play advice."""

    # Function: __init__.
    def __init__(self, *, policy: Optional[CardRankingModel] = None, top_k_default: int = 3) -> None:
        self.encoder = BridgeCardPlayModel(focus_player=1)
        self.episode_encoder = CardPlayEpisodeRunner(focus_player=1)
        self.policy: CardRankingModel = policy or HeuristicBaselineCardPolicy()
        self.top_k_default = top_k_default

    # Function: _normalize_trick_cards.
    def _normalize_trick_cards(self, trick_cards: Sequence[object]) -> List[Tuple[int, str]]:
        normalized: List[Tuple[int, str]] = []
        for item in trick_cards:
            if isinstance(item, tuple) and len(item) == 2:
                player = int(item[0])
                card = self.encoder._normalize_card(str(item[1]))
            elif isinstance(item, dict):
                player = int(item.get("player", 0))
                card = self.encoder._normalize_card(str(item.get("card", "")))
            else:
                raise ValueError("trick_cards items must be (player, card) tuples or dicts.")
            if player not in (1, 2, 3, 4):
                raise ValueError("trick card player must be one of 1..4")
            normalized.append((player, card))
        return normalized

    # Function: _legal_cards.
    def _legal_cards(self, hand: Sequence[str], trick_cards: Sequence[Tuple[int, str]]) -> List[str]:
        clean_hand = [self.encoder._normalize_card(card) for card in hand]
        if not trick_cards:
            return list(clean_hand)
        lead_suit = trick_cards[0][1][-1]
        suited = [card for card in clean_hand if card.endswith(lead_suit)]
        return suited or clean_hand

    # Function: _card_history_from_trick.
    def _card_history_from_trick(
        self,
        trick_cards: Sequence[Tuple[int, str]],
        contract: Optional[Tuple[int, str, int, int]],
        legal_cards: Sequence[str],
    ) -> List[List[Dict[str, object]]]:
        trump = None if not contract or contract[1] == "NT" else contract[1]
        lead_suit = trick_cards[0][1][-1] if trick_cards else None
        return [
            [
                {
                    "player": player,
                    "card": card,
                    "lead_suit": lead_suit,
                    "trump_suit": trump,
                    "legal_cards": list(legal_cards),
                }
                for player, card in trick_cards
            ]
        ]

    # Function: recommend_card.
    def recommend_card(
        self,
        hand: Sequence[str],
        trick_cards: Sequence[object],
        contract: Optional[Tuple[int, str, int, int]],
        bid_history: Sequence[Sequence[Optional[str]]],
        strategy_answers: Sequence[float],
        player: int,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, object]]:
        if player not in (1, 2, 3, 4):
            raise ValueError("player must be one of 1..4")

        self.encoder.focus_player = player
        self.episode_encoder.focus_player = player

        trick = self._normalize_trick_cards(trick_cards)
        legal_cards = self._legal_cards(hand, trick)
        card_history = self._card_history_from_trick(trick, contract, legal_cards)
        card_context = self.encoder.next_card_context(card_history)

        strategy_vector = [float(value) for value in strategy_answers] if strategy_answers else []
        strategy_features = self.episode_encoder._encode_strategy_answers(strategy_vector)
        bid_context = self.episode_encoder._build_bid_history_context(raw_bid_history=bid_history, encoded_bid_history=None)

        feature_payload: Dict[str, object] = {
            "player": player,
            "hand": list(hand),
            "trick_cards": list(trick),
            "contract": contract,
            "bid_history": [list(row) for row in bid_history],
            "legal_cards": list(legal_cards),
            "card_context": card_context,
            "bid_context": bid_context,
            "strategy_answers": strategy_vector,
            "strategy_features": strategy_features,
        }

        ranked = self.policy.rank_cards(feature_payload, legal_cards)
        k = top_k if top_k is not None else self.top_k_default
        return [
            {
                "card": rec.card,
                "confidence": round(float(rec.confidence), 4),
                "reason": rec.reason,
                "rationale": dict(rec.rationale),
                "rank": idx + 1,
            }
            for idx, rec in enumerate(ranked[: max(1, k)])
        ]


_DEFAULT_RECOMMENDER = CardPlayRecommender()


# Function: recommend_card.
def recommend_card(
    hand: Sequence[str],
    trick_cards: Sequence[object],
    contract: Optional[Tuple[int, str, int, int]],
    bid_history: Sequence[Sequence[Optional[str]]],
    strategy_answers: Sequence[float],
    player: int,
) -> List[Dict[str, object]]:
    """Module-level convenience wrapper for GameLoop integration."""
    return _DEFAULT_RECOMMENDER.recommend_card(
        hand=hand,
        trick_cards=trick_cards,
        contract=contract,
        bid_history=bid_history,
        strategy_answers=strategy_answers,
        player=player,
    )
