"""Core data storage for one contract bridge game loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

SUITS: Tuple[str, ...] = ("C", "D", "H", "S")
RANKS: Tuple[str, ...] = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
PLAYERS: Tuple[int, ...] = (1, 2, 3, 4)


def build_deck() -> List[str]:
    """Create a standard ordered deck from 2C to AS."""
    return [f"{rank}{suit}" for rank in RANKS for suit in SUITS]


@dataclass
class GameData:
    """Stores all current and historical values used by the MVP game loop."""

    # Ignoring StratDec matrix for now as requested.
    curr_card_hold: List[List[str]] = field(default_factory=lambda: [[] for _ in PLAYERS])
    curr_bid_hist: List[List[Optional[str]]] = field(default_factory=list)
    curr_points: Dict[int, int] = field(default_factory=lambda: {player: 0 for player in PLAYERS})
    hist_points: Dict[int, int] = field(default_factory=lambda: {player: 0 for player in PLAYERS})

    def reset_round_state(self) -> None:
        """Clear all hand-specific data before a new hand is dealt."""
        self.curr_card_hold = [[] for _ in PLAYERS]
        self.curr_bid_hist = []
        self.curr_points = {player: 0 for player in PLAYERS}

    def record_bid(self, player: int, bid: str) -> None:
        """Append bids in rows of four columns that map to players 1-4."""
        if not self.curr_bid_hist or all(cell is not None for cell in self.curr_bid_hist[-1]):
            self.curr_bid_hist.append([None, None, None, None])
        self.curr_bid_hist[-1][player - 1] = bid

    def add_round_points(self, round_points: Dict[int, int]) -> None:
        """Save points earned this round and update historical totals."""
        for player in PLAYERS:
            delta = round_points.get(player, 0)
            self.curr_points[player] = delta
            self.hist_points[player] += delta
