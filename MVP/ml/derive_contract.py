"""Auction meaning derivation helpers for card-play supervision."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List

from .normalize import normalize_bid


@dataclass(frozen=True)
class ContractMeaning:
    level: int | None
    strain: str | None
    multiplier: str
    declarer: int | None
    dummy: int | None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _is_contract_bid(token: str) -> bool:
    return len(token) in {2, 3} and token[0] in "1234567" and token[1:] in {"C", "D", "H", "S", "NT"}


def derive_contract_from_auction(auction_bids: Iterable[str]) -> ContractMeaning:
    """Derive contract-level meaning from an ordered auction.

    Declarer/dummy depend on dealer-relative partnership order, which is currently
    unspecified in this repository. They are intentionally returned as ``None``.
    """
    normalized: List[str] = [normalize_bid(b) for b in auction_bids]

    last_contract_idx: int | None = None
    level: int | None = None
    strain: str | None = None

    for idx, bid in enumerate(normalized):
        if _is_contract_bid(bid):
            last_contract_idx = idx
            level = int(bid[0])
            strain = bid[1:]

    multiplier = ""
    if last_contract_idx is not None:
        after_contract = normalized[last_contract_idx + 1 :]
        if "XX" in after_contract:
            multiplier = "XX"
        elif "X" in after_contract:
            multiplier = "X"

    return ContractMeaning(
        level=level,
        strain=strain,
        multiplier=multiplier,
        declarer=None,
        dummy=None,
    )
