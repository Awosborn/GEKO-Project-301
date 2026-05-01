"""Small bridge bidding helpers.

This is intentionally not a full bridge engine. The functions here cover
normalization, contract ordering, turn order, and simplified legality checks so
the project has a clean place to grow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence


SEATS = ["north", "east", "south", "west"]
STRAINS = ["C", "D", "H", "S", "NT"]
CALL_ALIASES = {
    "P": "Pass",
    "PASS": "Pass",
    "X": "Double",
    "DBL": "Double",
    "DOUBLE": "Double",
    "XX": "Redouble",
    "RDBL": "Redouble",
    "REDOUBLE": "Redouble",
}
CONTRACT_RE = re.compile(r"^([1-7])\s*(C|D|H|S|NT)$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedCall:
    """Normalized representation of one call."""

    raw: str
    normalized: str
    kind: str
    level: Optional[int] = None
    strain: Optional[str] = None


def normalize_call(call: str) -> str:
    """Normalize pass/double/redouble aliases and contract capitalization."""
    compact = str(call).strip().replace(" ", "")
    upper = compact.upper()
    if upper in CALL_ALIASES:
        return CALL_ALIASES[upper]
    match = CONTRACT_RE.match(compact)
    if match:
        return f"{match.group(1)}{match.group(2).upper()}"
    return str(call).strip()


def parse_call(call: str) -> ParsedCall:
    """Parse a bridge call into pass/double/redouble/contract/unknown."""
    normalized = normalize_call(call)
    if normalized == "Pass":
        return ParsedCall(call, normalized, "pass")
    if normalized == "Double":
        return ParsedCall(call, normalized, "double")
    if normalized == "Redouble":
        return ParsedCall(call, normalized, "redouble")
    match = CONTRACT_RE.match(normalized)
    if match:
        return ParsedCall(call, normalized, "contract", int(match.group(1)), match.group(2).upper())
    return ParsedCall(call, normalized, "unknown")


def is_pass(call: str) -> bool:
    """Return True if call is pass."""
    return parse_call(call).kind == "pass"


def is_double(call: str) -> bool:
    """Return True if call is double."""
    return parse_call(call).kind == "double"


def is_redouble(call: str) -> bool:
    """Return True if call is redouble."""
    return parse_call(call).kind == "redouble"


def is_contract_bid(call: str) -> bool:
    """Return True if call is a contract bid such as 1NT or 4S."""
    return parse_call(call).kind == "contract"


def contract_sort_key(call: str) -> tuple[int, int]:
    """Return an order key for contract bids."""
    parsed = parse_call(call)
    if parsed.kind != "contract" or parsed.level is None or parsed.strain is None:
        raise ValueError(f"Not a contract bid: {call}")
    return parsed.level, STRAINS.index(parsed.strain)


def compare_contract_bids(left: str, right: str) -> int:
    """Compare two contract bids. Returns -1, 0, or 1."""
    left_key = contract_sort_key(left)
    right_key = contract_sort_key(right)
    return (left_key > right_key) - (left_key < right_key)


def last_contract(auction_history: Sequence[dict | object]) -> Optional[str]:
    """Return the last contract bid in an auction history."""
    for entry in reversed(auction_history):
        call = getattr(entry, "call", None) if not isinstance(entry, dict) else entry.get("call")
        if call and is_contract_bid(call):
            return normalize_call(call)
    return None


def determine_next_seat(dealer: str, auction_history: Sequence[dict | object]) -> str:
    """Determine whose turn it is from the dealer and number of calls made."""
    dealer_norm = dealer.lower()
    if dealer_norm not in SEATS:
        raise ValueError(f"Unknown dealer: {dealer}")
    index = (SEATS.index(dealer_norm) + len(auction_history)) % len(SEATS)
    return SEATS[index]


def syntactically_valid_call(call: str) -> bool:
    """Check whether a call is a recognized call form."""
    return parse_call(call).kind in {"pass", "double", "redouble", "contract"}


_HCP_VALUES: dict[str, int] = {"A": 4, "K": 3, "Q": 2, "J": 1}


def calculate_hcp(hand: str) -> int:
    """Return the exact High Card Point count for a hand string.

    Accepts the standard format: 'S AKQ H J94 D T862 C K73'
    A=4, K=3, Q=2, J=1.  All other characters (suit letters, digits,
    spaces) contribute 0.
    """
    return sum(_HCP_VALUES.get(ch.upper(), 0) for ch in hand)


def validate_legal_calls(legal_calls: Iterable[str]) -> List[str]:
    """Return calls whose syntax is not recognized."""
    return [call for call in legal_calls if not syntactically_valid_call(call)]


def is_bid_in_legal_calls(call: str, legal_calls: Iterable[str]) -> bool:
    """Check if a normalized bid appears in the current legal-call list."""
    normalized = normalize_call(call)
    return normalized in {normalize_call(item) for item in legal_calls}


def contract_bid_is_above_last(call: str, auction_history: Sequence[dict | object]) -> bool:
    """Check whether a contract bid is higher than the last contract in the auction."""
    if not is_contract_bid(call):
        return False
    previous = last_contract(auction_history)
    if previous is None:
        return True
    return compare_contract_bids(call, previous) > 0


def simple_legal_check(
    call: str,
    *,
    auction_history: Sequence[dict | object],
    legal_calls: Optional[Sequence[str]] = None,
) -> bool:
    """
    Simplified legal check.

    If the caller supplies legal_calls from a game engine, trust that list.
    Otherwise, pass and higher contract bids are allowed; double/redouble require
    a prior non-pass action and are left simplified.
    """
    if legal_calls is not None:
        return is_bid_in_legal_calls(call, legal_calls)
    parsed = parse_call(call)
    if parsed.kind == "pass":
        return True
    if parsed.kind == "contract":
        return contract_bid_is_above_last(call, auction_history)
    return bool(auction_history) and parsed.kind in {"double", "redouble"}
