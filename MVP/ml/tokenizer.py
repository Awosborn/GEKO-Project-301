"""Tokenizer utilities backed by ``MVP/training_tokens.json``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


SPECIAL_TOKENS = ["PAD", "BOS", "EOS", "UNK"]
CONTEXT_TOKENS = [
    "PHASE_BID",
    "PHASE_PLAY",
    "BIDS",
    "HAND",
    "TO_ACT_P1",
    "TO_ACT_P2",
    "TO_ACT_P3",
    "TO_ACT_P4",
    "NONE_VUL",
    "NS_VUL",
    "EW_VUL",
    "BOTH_VUL",
]


@dataclass(frozen=True)
class Tokenizer:
    token_to_id: Dict[str, int]
    id_to_token: Dict[int, str]

    @classmethod
    def from_training_tokens(cls, path: str | Path) -> "Tokenizer":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        token_to_id: Dict[str, int] = {}

        for group_name in ("bids", "cards", "strategy_questions"):
            for token, details in payload.get(group_name, {}).items():
                token_to_id[token] = int(details["id"])

        next_id = int(payload.get("meta", {}).get("next_id", max(token_to_id.values(), default=-1) + 1))
        for token in [*SPECIAL_TOKENS, *CONTEXT_TOKENS]:
            if token not in token_to_id:
                token_to_id[token] = next_id
                next_id += 1

        id_to_token = {idx: tok for tok, idx in token_to_id.items()}
        return cls(token_to_id=token_to_id, id_to_token=id_to_token)

    def encode(self, tokens: Iterable[str]) -> List[int]:
        unk = self.token_to_id["UNK"]
        return [self.token_to_id.get(token, unk) for token in tokens]

    def decode(self, ids: Iterable[int]) -> List[str]:
        return [self.id_to_token.get(idx, "UNK") for idx in ids]
