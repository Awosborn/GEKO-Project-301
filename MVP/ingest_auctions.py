"""Historical auction ingestion into shared EpisodeRecord schema."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from dataset_schema import EpisodeRecord, normalize_vulnerability


def ingest_auctions(payloads: Iterable[Dict[str, Any]], source: str = "auctions") -> List[EpisodeRecord]:
    records: List[EpisodeRecord] = []
    for idx, item in enumerate(payloads, start=1):
        bids = []
        for step_idx, step in enumerate(item.get("auction", [])):
            bids.append(
                {
                    "step": step_idx,
                    "player": int(step["player"]),
                    "bid": str(step["bid"]).upper(),
                    "is_expert": bool(step.get("is_expert", True)),
                }
            )

        records.append(
            EpisodeRecord(
                episode_id=str(item.get("episode_id", f"{source}-{idx}")),
                source=source,
                board_number=int(item.get("board_number", idx)),
                vulnerability=normalize_vulnerability(item.get("vulnerability")),
                hands_by_player={int(k): list(v) for k, v in item.get("hands", {}).items()},
                auction_sequence=bids,
                labels={"final_contract": item.get("final_contract")},
                metadata={"auction_only": True, **dict(item.get("metadata", {}))},
            )
        )
    return records
