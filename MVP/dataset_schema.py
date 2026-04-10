"""Shared training schema for historical bridge records."""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional


@dataclass
class EpisodeRecord:
    episode_id: str
    source: str
    board_number: int
    vulnerability: Dict[int, bool]
    hands_by_player: Dict[int, List[str]]
    auction_sequence: List[Dict[str, Any]] = field(default_factory=list)
    play_sequence: List[Dict[str, Any]] = field(default_factory=list)
    labels: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_player_key(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int(str(value).replace("player", "").strip())


def normalize_vulnerability(raw: Optional[Dict[Any, Any]]) -> Dict[int, bool]:
    default = {1: False, 2: False, 3: False, 4: False}
    if raw is None:
        return default
    return {normalize_player_key(k): bool(v) for k, v in raw.items()}
