"""Historical card-play ingestion into shared EpisodeRecord schema."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from dataset_schema import EpisodeRecord, normalize_vulnerability


def ingest_plays(payloads: Iterable[Dict[str, Any]], source: str = "plays") -> List[EpisodeRecord]:
    records: List[EpisodeRecord] = []
    for idx, item in enumerate(payloads, start=1):
        plays = []
        for step_idx, step in enumerate(item.get("plays", [])):
            plays.append(
                {
                    "step": step_idx,
                    "trick_index": int(step.get("trick_index", step_idx // 4)),
                    "player": int(step["player"]),
                    "card": str(step["card"]).upper(),
                }
            )

        records.append(
            EpisodeRecord(
                episode_id=str(item.get("episode_id", f"{source}-{idx}")),
                source=source,
                board_number=int(item.get("board_number", idx)),
                vulnerability=normalize_vulnerability(item.get("vulnerability")),
                hands_by_player={int(k): list(v) for k, v in item.get("hands", {}).items()},
                auction_sequence=list(item.get("auction", [])),
                play_sequence=plays,
                labels={
                    "declarer_tricks": int(item.get("declarer_tricks", 0)),
                    "double_dummy_tricks": int(item.get("double_dummy_tricks", 0)),
                    "imps_proxy": float(item.get("imps_proxy", 0.0)),
                    "mps_proxy": float(item.get("mps_proxy", 0.0)),
                },
                metadata={"play_only": True, **dict(item.get("metadata", {}))},
            )
        )
    return records
