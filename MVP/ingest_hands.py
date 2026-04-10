"""Historical hand ingestion into shared EpisodeRecord schema."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from dataset_schema import EpisodeRecord, normalize_player_key, normalize_vulnerability


def ingest_hands(payloads: Iterable[Dict[str, Any]], source: str = "hands") -> List[EpisodeRecord]:
    records: List[EpisodeRecord] = []
    for idx, item in enumerate(payloads, start=1):
        hands_raw = item.get("hands", {})
        hands = {normalize_player_key(k): list(v) for k, v in hands_raw.items()}
        records.append(
            EpisodeRecord(
                episode_id=str(item.get("episode_id", f"{source}-{idx}")),
                source=source,
                board_number=int(item.get("board_number", idx)),
                vulnerability=normalize_vulnerability(item.get("vulnerability")),
                hands_by_player=hands,
                metadata={"hand_only": True, **dict(item.get("metadata", {}))},
            )
        )
    return records
