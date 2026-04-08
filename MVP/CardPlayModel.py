"""Bridge card-play model utilities.

This module mirrors ``BiddingModel.py`` patterns for play-of-the-hand modeling.
It encodes ordered card-play events with:
- exact player identity,
- partner/opponent side markers relative to a focus player,
- trick context (trick index, lead suit, trump), and
- legal-card metadata for supervised next-card prediction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from Data import RANKS, SUITS


CARD_VOCAB: Tuple[str, ...] = tuple(f"{rank}{suit}" for rank in RANKS for suit in SUITS)
CARD_TO_ID: Dict[str, int] = {card: idx for idx, card in enumerate(CARD_VOCAB)}


def _partnership(player: int) -> int:
    """Players 1/3 are one side, players 2/4 are the other side."""
    return 0 if player in (1, 3) else 1


@dataclass(frozen=True)
class CardPlayEvent:
    """One played card with bidder-side style markers for card play."""

    trick_index: int
    seat_in_trick: int
    player: int
    card: str
    is_opponent_play: bool
    lead_suit: Optional[str]
    trump_suit: Optional[str]
    legal_card_count: int


class BridgeCardPlayModel:
    """Token-based card-play encoder for downstream ML training."""

    def __init__(self, focus_player: int = 1) -> None:
        if focus_player not in (1, 2, 3, 4):
            raise ValueError("focus_player must be one of 1, 2, 3, 4.")
        self.focus_player = focus_player
        self.card_to_id: Dict[str, int] = dict(CARD_TO_ID)

    def _normalize_card(self, card: str) -> str:
        clean_card = card.strip().upper()
        if clean_card not in self.card_to_id:
            raise ValueError(f"Unsupported card symbol '{card}'.")
        return clean_card

    def _normalize_suit(self, suit: Optional[str]) -> Optional[str]:
        if suit is None:
            return None
        clean_suit = suit.strip().upper()
        if clean_suit not in SUITS:
            raise ValueError(f"Unsupported suit '{suit}'.")
        return clean_suit

    def _is_opponent(self, player: int) -> bool:
        if player not in (1, 2, 3, 4):
            raise ValueError("player must be one of 1, 2, 3, 4.")
        return _partnership(player) != _partnership(self.focus_player)

    def encode_card_play_history(
        self,
        card_play_history: Sequence[Sequence[Dict[str, object]]],
    ) -> List[Dict[str, int]]:
        """Encode trick-ordered card play into flat model-ready tokens.

        Parameters
        ----------
        card_play_history:
            Sequence of tricks. Each trick is a sequence of dict records with keys:
            ``player`` (1-4), ``card`` (e.g., "AS"), optional ``lead_suit``,
            optional ``trump_suit``, and optional ``legal_cards`` list.
        """
        encoded: List[Dict[str, int]] = []
        for trick_index, trick in enumerate(card_play_history):
            for seat_in_trick, play in enumerate(trick):
                player = int(play["player"])
                card = self._normalize_card(str(play["card"]))
                lead_suit = self._normalize_suit(play.get("lead_suit"))
                trump_suit = self._normalize_suit(play.get("trump_suit"))
                legal_cards_raw = play.get("legal_cards") or []
                legal_card_count = len(list(legal_cards_raw)) if legal_cards_raw else 0

                encoded.append(
                    {
                        "trick_index": trick_index,
                        "seat_in_trick": seat_in_trick,
                        "player": player,
                        "player_token": player - 1,
                        "card_token": self.card_to_id[card],
                        "is_opponent_play": int(self._is_opponent(player)),
                        "lead_suit_token": SUITS.index(lead_suit) if lead_suit else -1,
                        "trump_suit_token": SUITS.index(trump_suit) if trump_suit else -1,
                        "legal_card_count": legal_card_count,
                    }
                )
        return encoded

    def next_card_context(
        self,
        card_play_history: Sequence[Sequence[Dict[str, object]]],
    ) -> Dict[str, object]:
        """Build a model-ready context payload for next-card prediction."""
        encoded_sequence = self.encode_card_play_history(card_play_history)
        return {
            "focus_player": self.focus_player,
            "play_sequence": encoded_sequence,
            "sequence_length": len(encoded_sequence),
            "vocab_size": len(self.card_to_id),
        }
