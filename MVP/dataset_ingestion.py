"""Pipeline utilities to combine hand/auction/play historical data."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from dataset_schema import EpisodeRecord
from ingest_auctions import ingest_auctions
from ingest_hands import ingest_hands
from ingest_plays import ingest_plays


def build_shared_episode_dataset(
    *,
    hands_payloads: Iterable[Dict[str, Any]],
    auction_payloads: Iterable[Dict[str, Any]],
    play_payloads: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    records: List[EpisodeRecord] = []
    records.extend(ingest_hands(hands_payloads, source="historical_hands"))
    records.extend(ingest_auctions(auction_payloads, source="historical_auctions"))
    records.extend(ingest_plays(play_payloads, source="historical_plays"))

    merged: Dict[str, EpisodeRecord] = {}
    for record in records:
        existing = merged.get(record.episode_id)
        if existing is None:
            merged[record.episode_id] = record
            continue

        existing.hands_by_player.update(record.hands_by_player)
        if record.auction_sequence:
            existing.auction_sequence = record.auction_sequence
        if record.play_sequence:
            existing.play_sequence = record.play_sequence
        existing.labels.update(record.labels)
        existing.metadata.update(record.metadata)

    return [item.to_dict() for item in merged.values()]
