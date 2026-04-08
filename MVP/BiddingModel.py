"""Bridge bidding model utilities.

This module focuses only on bidding-state modeling.
The model differentiates:
- which exact player made each bid, and
- whether each bid came from partner side or opponent side,
relative to a configurable focus player.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


BID_VOCAB: Tuple[str, ...] = (
    "P",
    "X",
    "XX",
    "1C",
    "1D",
    "1H",
    "1S",
    "1NT",
    "2C",
    "2D",
    "2H",
    "2S",
    "2NT",
    "3C",
    "3D",
    "3H",
    "3S",
    "3NT",
    "4C",
    "4D",
    "4H",
    "4S",
    "4NT",
    "5C",
    "5D",
    "5H",
    "5S",
    "5NT",
    "6C",
    "6D",
    "6H",
    "6S",
    "6NT",
    "7C",
    "7D",
    "7H",
    "7S",
    "7NT",
)


def _partnership(player: int) -> int:
    """Players 1/3 are one side, players 2/4 are the other side."""
    return 0 if player in (1, 3) else 1


@dataclass(frozen=True)
class BidEvent:
    """One bid with bidder identity and side-relative signal."""

    bidder: int
    bid: str
    is_opponent_bid: bool


class BridgeBiddingModel:
    """Token-based bidding encoder for downstream ML training.

    Notes
    -----
    - This class intentionally models only bidding information.
    - `focus_player` is the seat whose perspective we train/infer for.
    - Each bid is encoded with player identity and opponent/partner flag.
    """

    def __init__(self, focus_player: int = 1) -> None:
        if focus_player not in (1, 2, 3, 4):
            raise ValueError("focus_player must be one of 1, 2, 3, 4.")
        self.focus_player = focus_player
        self.bid_to_id: Dict[str, int] = {bid: idx for idx, bid in enumerate(BID_VOCAB)}

    def _normalize_bid(self, bid: str) -> str:
        clean_bid = bid.strip().upper()
        if clean_bid not in self.bid_to_id:
            raise ValueError(f"Unsupported bid symbol '{bid}'.")
        return clean_bid

    def _is_opponent(self, bidder: int) -> bool:
        if bidder not in (1, 2, 3, 4):
            raise ValueError("bidder must be one of 1, 2, 3, 4.")
        return _partnership(bidder) != _partnership(self.focus_player)

    def flatten_bid_history(
        self,
        bid_history: Sequence[Sequence[Optional[str]]],
    ) -> List[BidEvent]:
        """Flatten row-based bid history into ordered BidEvent records.

        Expected input shape matches `GameData.curr_bid_hist`: rows of up to four
        bids, where each column maps to players 1..4.
        """
        events: List[BidEvent] = []
        for row in bid_history:
            if len(row) > 4:
                raise ValueError("Each bid-history row can contain at most 4 entries.")
            for col, bid in enumerate(row, start=1):
                if bid is None:
                    continue
                clean_bid = self._normalize_bid(bid)
                events.append(
                    BidEvent(
                        bidder=col,
                        bid=clean_bid,
                        is_opponent_bid=self._is_opponent(col),
                    )
                )
        return events

    def encode_bid_history(
        self,
        bid_history: Sequence[Sequence[Optional[str]]],
    ) -> List[Dict[str, int]]:
        """Encode bid history with bidder and side-aware features.

        Returns list of dict records, each including:
        - bid_token: bid symbol ID
        - bidder: exact player seat (1-4)
        - bidder_token: seat encoded as 0-3
        - is_opponent_bid: 1 if opponent, 0 if same side as focus player
        """
        events = self.flatten_bid_history(bid_history)
        encoded: List[Dict[str, int]] = []
        for event in events:
            encoded.append(
                {
                    "bid_token": self.bid_to_id[event.bid],
                    "bidder": event.bidder,
                    "bidder_token": event.bidder - 1,
                    "is_opponent_bid": int(event.is_opponent_bid),
                }
            )
        return encoded

    def next_bid_context(
        self,
        bid_history: Sequence[Sequence[Optional[str]]],
    ) -> Dict[str, object]:
        """Build a model-ready context payload for next-bid prediction."""
        encoded_sequence = self.encode_bid_history(bid_history)
        return {
            "focus_player": self.focus_player,
            "bid_sequence": encoded_sequence,
            "sequence_length": len(encoded_sequence),
            "vocab_size": len(self.bid_to_id),
        }
