"""Training-data preparation utilities for bridge MVP.

This module turns symbolic bridge game data into numeric token IDs and embeddings
that can be consumed by a future machine-learning pipeline.

Scope intentionally excludes model layers and training loops.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Dict, List, Tuple

from Data import GameData, StrategyDeclaration, build_deck


TOKEN_STORE_PATH = Path(__file__).resolve().parent / "training_tokens.json"


def _default_bid_space() -> List[str]:
    bids: List[str] = ["P", "X", "XX"]
    for level in range(1, 8):
        for denomination in ("C", "D", "H", "S", "NT"):
            bids.append(f"{level}{denomination}")
    return bids


@dataclass
class TokenStore:
    """Persistent mapping of symbols to token IDs + random embedding vectors."""

    embedding_size: int = 16
    seed: int = 301

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        self._store = {
            "meta": {"embedding_size": self.embedding_size, "next_id": 1},
            "bids": {},
            "cards": {},
            "strategy_questions": {},
        }

    def _new_embedding(self) -> List[float]:
        return [round(self._rng.uniform(-1.0, 1.0), 6) for _ in range(self.embedding_size)]

    def _assign_token(self, category: str, symbol: str) -> int:
        bucket: Dict[str, Dict[str, object]] = self._store[category]
        if symbol in bucket:
            return int(bucket[symbol]["id"])

        token_id = int(self._store["meta"]["next_id"])
        bucket[symbol] = {"id": token_id, "vector": self._new_embedding()}
        self._store["meta"]["next_id"] = token_id + 1
        return token_id

    def load(self, path: Path = TOKEN_STORE_PATH) -> None:
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._store = payload
        self.embedding_size = int(payload.get("meta", {}).get("embedding_size", self.embedding_size))
        self._rng = random.Random(self.seed)

    def save(self, path: Path = TOKEN_STORE_PATH) -> None:
        path.write_text(json.dumps(self._store, indent=2), encoding="utf-8")

    def ensure_base_vocab(self, strategy: StrategyDeclaration) -> None:
        for bid in _default_bid_space():
            self._assign_token("bids", bid)
        for card in build_deck():
            self._assign_token("cards", card)
        for index, (question, _, _) in enumerate(strategy.question_bank, start=1):
            symbol = f"Q{index}:{question}"
            self._assign_token("strategy_questions", symbol)

    def token_for_bid(self, bid: str) -> int:
        return self._assign_token("bids", bid.upper())

    def token_for_card(self, card: str) -> int:
        return self._assign_token("cards", card.upper())

    def token_for_strategy_question(self, question_index: int, question_text: str) -> int:
        symbol = f"Q{question_index}:{question_text}"
        return self._assign_token("strategy_questions", symbol)


class BridgeTrainingPreprocessor:
    """Converts live GameData into tokenized numeric structures."""

    def __init__(self, store: TokenStore) -> None:
        self.store = store

    def encode_game_data(self, data: GameData) -> Dict[str, object]:
        strategy_tokens: List[Tuple[int, int]] = []
        for index, ((question, _, _), answer) in enumerate(
            zip(data.strat_dec.question_bank, data.strat_dec.numeric_answers),
            start=1,
        ):
            q_token = self.store.token_for_strategy_question(index, question)
            strategy_tokens.append((q_token, answer))

        hands = [
            [self.store.token_for_card(card) for card in player_hand]
            for player_hand in data.curr_card_hold
        ]

        bid_history: List[List[int]] = []
        for row in data.curr_bid_hist:
            row_tokens: List[int] = []
            for bid in row:
                if bid is None:
                    continue
                row_tokens.append(self.store.token_for_bid(bid))
            bid_history.append(row_tokens)

        return {
            "board_number": data.board_number,
            "vulnerability": data.vulnerability,
            "strategy_question_answer_pairs": strategy_tokens,
            "hand_card_tokens": hands,
            "bid_history_tokens": bid_history,
        }


def build_training_setup(
    data: GameData,
    token_path: Path = TOKEN_STORE_PATH,
    embedding_size: int = 16,
    seed: int = 301,
) -> Dict[str, object]:
    """Initialize/load/update token mappings and encode GameData for training input.

    Token assignments are persistent and updateable:
    - Existing token IDs are re-used from disk.
    - New symbols are appended with new IDs.
    - Updated mapping is saved at the end of execution.
    """

    store = TokenStore(embedding_size=embedding_size, seed=seed)
    store.load(token_path)
    store.ensure_base_vocab(data.strat_dec)

    processor = BridgeTrainingPreprocessor(store)
    encoded = processor.encode_game_data(data)

    store.save(token_path)
    return encoded


if __name__ == "__main__":
    # Example usage with strategy profile #1 to show data-prep output shape.
    game_data = GameData()
    game_data.strat_dec.load(1)
    encoded_payload = build_training_setup(game_data)

    print("Training setup complete.")
    print(f"Token store path: {TOKEN_STORE_PATH}")
    print(f"Encoded keys: {list(encoded_payload.keys())}")
