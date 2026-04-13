"""Normalization helpers for bid/card tokens.

Week-3 scope: centralize token normalization so dataset export, tokenizer, and
future training/inference code all share identical canonicalization rules.
"""

from __future__ import annotations

from typing import Iterable, List


def normalize_bid(raw: str) -> str:
    """Normalize raw bid strings to canonical bridge tokens.

    Rules:
    - pass/p -> P
    - d/x -> X
    - r/xx -> XX
    - 1N..7N -> 1NT..7NT
    - uppercase + trim
    - empty values -> UNK
    """
    token = raw.strip() if raw is not None else ""
    if not token:
        return "UNK"

    lower = token.lower()
    if lower in {"pass", "p"}:
        return "P"
    if lower in {"d", "x"}:
        return "X"
    if lower in {"r", "xx"}:
        return "XX"

    token = token.upper()
    if len(token) == 2 and token[0] in "1234567" and token[1] == "N":
        return f"{token[0]}NT"

    return token


def normalize_bid_history(raw_bids: Iterable[str]) -> List[str]:
    return [normalize_bid(bid) for bid in raw_bids]


def normalize_card(raw: str) -> str:
    token = raw.strip() if raw is not None else ""
    return token.upper() if token else "UNK"
