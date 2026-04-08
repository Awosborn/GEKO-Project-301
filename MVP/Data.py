"""Core data storage for one contract bridge game loop."""

from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Dict, List, Optional, Tuple

SUITS: Tuple[str, ...] = ("C", "D", "H", "S")
RANKS: Tuple[str, ...] = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
PLAYERS: Tuple[int, ...] = (1, 2, 3, 4)


def build_deck() -> List[str]:
    """Create a standard ordered deck from 2C to AS."""
    return [f"{rank}{suit}" for rank in RANKS for suit in SUITS]


@dataclass
class DoubleDummyOutcome:
    """Projected best contract and score from a double-dummy style estimate."""

    contract: str
    declarer: int
    expected_tricks: int
    projected_score: int


@dataclass
class GameData:
    """Stores all current and historical values used by the MVP game loop."""

    # Ignoring StratDec matrix for now as requested.
    curr_card_hold: List[List[str]] = field(default_factory=lambda: [[] for _ in PLAYERS])
    curr_bid_hist: List[List[Optional[str]]] = field(default_factory=list)
    curr_points: Dict[int, int] = field(default_factory=lambda: {player: 0 for player in PLAYERS})
    hist_points: Dict[int, int] = field(default_factory=lambda: {player: 0 for player in PLAYERS})
    board_number: int = 0
    vulnerability: Dict[int, bool] = field(default_factory=lambda: {player: False for player in PLAYERS})
    double_dummy_outcome: Optional[DoubleDummyOutcome] = None

    def reset_round_state(self) -> None:
        """Clear all hand-specific data before a new hand is dealt."""
        self.curr_card_hold = [[] for _ in PLAYERS]
        self.curr_bid_hist = []
        self.curr_points = {player: 0 for player in PLAYERS}
        self.double_dummy_outcome = None

    def set_board_vulnerability(self) -> None:
        """Apply duplicate-bridge vulnerability pattern based on board number."""
        # Standard 16-board cycle:
        # 1 None, 2 N-S, 3 E-W, 4 All, 5 N-S, 6 E-W, 7 All, 8 None,
        # 9 E-W, 10 All, 11 None, 12 N-S, 13 All, 14 None, 15 N-S, 16 E-W
        cycle = [
            (False, False),
            (True, False),
            (False, True),
            (True, True),
            (True, False),
            (False, True),
            (True, True),
            (False, False),
            (False, True),
            (True, True),
            (False, False),
            (True, False),
            (True, True),
            (False, False),
            (True, False),
            (False, True),
        ]
        ns_vul, ew_vul = cycle[(self.board_number - 1) % 16]
        self.vulnerability = {1: ns_vul, 3: ns_vul, 2: ew_vul, 4: ew_vul}

    def next_board(self) -> None:
        """Advance to the next board and update vulnerability."""
        self.board_number += 1
        self.set_board_vulnerability()

    def randomize_board(self, rng: random.Random | None = None) -> None:
        """Pick a random board number (1-16) and apply its vulnerability."""
        rng = rng or random.Random()
        self.board_number = rng.randint(1, 16)
        self.set_board_vulnerability()

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
