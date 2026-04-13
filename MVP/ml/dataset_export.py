"""Week-2 dataset exporters for supervised next-action training.

This module implements report pipeline priorities focused on turning snapshot rows
into ML-ready examples:
- group rows by ``deal_id``
- choose one representative snapshot per deal for bidding labels
- flatten seat-ordered auction rows into temporal actions
- emit prefix -> next-bid examples
- emit prefix -> next-card examples (post-action snapshot inversion)
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .derive_contract import derive_contract_from_auction
from .normalize import normalize_bid, normalize_card
from .preprocess import compute_deal_id, reconstruct_full_hands

PLAYERS: Sequence[int] = (1, 2, 3, 4)


@dataclass(frozen=True)
class BiddingExample:
    """Single supervised next-bid training example."""

    deal_id: str
    board_number: str
    seat_to_act: int
    hand_cards: List[str]
    bid_prefix: List[str]
    label_next_bid: str


@dataclass(frozen=True)
class CardPlayExample:
    """Single supervised next-card training example."""

    deal_id: str
    board_number: str
    seat_to_act: int
    hand_cards: List[str]
    auction_bids: List[str]
    play_prefix: List[Dict[str, object]]
    label_next_card: str
    derived_contract: Dict[str, object]


@dataclass(frozen=True)
class DatasetBuildStats:
    """Reproducibility stats captured while exporting datasets."""

    total_snapshots: int
    unique_deals: int
    bidding_examples: int
    cardplay_examples: int
    bidding_corrupted_deals: int
    cardplay_corrupted_snapshots: int
    corruption_reasons: Dict[str, int]


def _count_present_bids(curr_bid_hist: object) -> int:
    if not isinstance(curr_bid_hist, list):
        return 0
    count = 0
    for row in curr_bid_hist:
        if not isinstance(row, list):
            continue
        count += sum(1 for bid in row if bid is not None and str(bid).strip())
    return count


def flatten_bid_history(curr_bid_hist: object) -> List[Dict[str, object]]:
    """Flatten row-wise auction history into chronological seat actions."""
    events: List[Dict[str, object]] = []
    if not isinstance(curr_bid_hist, list):
        return events

    for row in curr_bid_hist:
        if not isinstance(row, list):
            continue
        for seat_index, raw_bid in enumerate(row[:4], start=1):
            if raw_bid is None:
                continue
            bid_text = str(raw_bid).strip()
            if not bid_text:
                continue
            events.append({"seat_to_act": seat_index, "bid": normalize_bid(bid_text)})

    return events


def group_snapshots_by_deal_id(snapshots: Iterable[Mapping[str, object]]) -> Dict[str, List[Mapping[str, object]]]:
    grouped: Dict[str, List[Mapping[str, object]]] = {}
    for snapshot in snapshots:
        deal_id = compute_deal_id(snapshot)
        grouped.setdefault(deal_id, []).append(snapshot)
    return grouped


def select_representative_bidding_snapshot(snapshots: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    """Pick the snapshot with the largest available auction history."""
    if not snapshots:
        raise ValueError("Cannot select representative snapshot from an empty list.")
    return max(snapshots, key=lambda snap: _count_present_bids(snap.get("curr_bid_hist")))


def build_bidding_examples_from_snapshot(snapshot: Mapping[str, object]) -> List[BiddingExample]:
    """Build prefix -> next-bid examples from one deal snapshot."""
    reconstruction = reconstruct_full_hands(snapshot)
    if reconstruction.is_corrupted:
        return []

    bid_events = flatten_bid_history(snapshot.get("curr_bid_hist"))
    deal_id = compute_deal_id(snapshot)
    board_number = str(snapshot.get("board_number", ""))

    examples: List[BiddingExample] = []
    prefix: List[str] = []
    for event in bid_events:
        seat_to_act = int(event["seat_to_act"])
        label = str(event["bid"])
        examples.append(
            BiddingExample(
                deal_id=deal_id,
                board_number=board_number,
                seat_to_act=seat_to_act,
                hand_cards=list(reconstruction.hands.get(seat_to_act, [])),
                bid_prefix=list(prefix),
                label_next_bid=label,
            )
        )
        prefix.append(label)

    return examples


def build_bidding_examples(snapshots: Iterable[Mapping[str, object]]) -> List[BiddingExample]:
    """Build bidding examples with grouped-per-deal representative snapshot selection."""
    grouped = group_snapshots_by_deal_id(snapshots)
    examples: List[BiddingExample] = []
    for deal_snapshots in grouped.values():
        representative = select_representative_bidding_snapshot(deal_snapshots)
        examples.extend(build_bidding_examples_from_snapshot(representative))
    return examples


def build_cardplay_examples(snapshots: Iterable[Mapping[str, object]]) -> List[CardPlayExample]:
    """Build card-play examples from all snapshots."""
    examples: List[CardPlayExample] = []
    for snapshot in snapshots:
        examples.extend(build_cardplay_examples_from_snapshot(snapshot))
    return examples


def build_cardplay_examples_from_snapshot(snapshot: Mapping[str, object]) -> List[CardPlayExample]:
    """Build one prefix -> next-card example from a post-action snapshot.

    Uses the report's "Option A" inversion strategy:
    - label = last played card
    - pre-state hand = current hand + label card returned to actor
    - pre-state prefix = full play history without the last action
    """
    reconstruction = reconstruct_full_hands(snapshot)
    if reconstruction.is_corrupted:
        return []

    raw_play_hist = snapshot.get("curr_card_play_hist")
    if not isinstance(raw_play_hist, list) or not raw_play_hist:
        return []

    last_event = raw_play_hist[-1]
    if not isinstance(last_event, Mapping):
        return []

    seat_to_act = int(last_event.get("player", 0))
    if seat_to_act not in PLAYERS:
        return []

    label_next_card = normalize_card(str(last_event.get("card", "")))
    if label_next_card == "UNK":
        return []

    hand_cards = [normalize_card(str(card)) for card in snapshot["curr_card_hold"][seat_to_act - 1] if str(card).strip()]
    hand_cards.append(label_next_card)

    auction_bids = [event["bid"] for event in flatten_bid_history(snapshot.get("curr_bid_hist"))]
    play_prefix: List[Dict[str, object]] = []
    for event in raw_play_hist[:-1]:
        if not isinstance(event, Mapping):
            continue
        normalized_event = dict(event)
        if "card" in normalized_event:
            normalized_event["card"] = normalize_card(str(normalized_event["card"]))
        play_prefix.append(normalized_event)

    derived_contract = derive_contract_from_auction(auction_bids).to_dict()

    return [
        CardPlayExample(
            deal_id=compute_deal_id(snapshot),
            board_number=str(snapshot.get("board_number", "")),
            seat_to_act=seat_to_act,
            hand_cards=hand_cards,
            auction_bids=auction_bids,
            play_prefix=play_prefix,
            label_next_card=label_next_card,
            derived_contract=derived_contract,
        )
    ]


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    snapshots: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            snapshots.append(json.loads(line))
    return snapshots


def _as_dict_rows(examples: Iterable[object]) -> List[Dict[str, Any]]:
    return [asdict(example) for example in examples]


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            count += 1
    return count


def write_parquet(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    data = [dict(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - dependency may be absent by environment
        raise RuntimeError("Parquet export requires pandas (and a parquet engine such as pyarrow).") from exc
    pd.DataFrame(data).to_parquet(path, index=False)
    return len(data)


def build_datasets_from_snapshot_jsonl(
    snapshot_jsonl_path: Path,
    output_dir: Path,
    formats: Sequence[str] = ("jsonl",),
) -> Tuple[DatasetBuildStats, Dict[str, Dict[str, Optional[Path]]]]:
    """Build and persist bidding/card-play datasets from snapshot JSONL."""
    snapshots = _read_jsonl(snapshot_jsonl_path)
    grouped = group_snapshots_by_deal_id(snapshots)
    corruption_reasons: Counter[str] = Counter()

    bidding_examples: List[BiddingExample] = []
    for deal_snapshots in grouped.values():
        representative = select_representative_bidding_snapshot(deal_snapshots)
        reconstruction = reconstruct_full_hands(representative)
        if reconstruction.is_corrupted:
            corruption_reasons[f"bidding:{reconstruction.reason}"] += 1
            continue
        bidding_examples.extend(build_bidding_examples_from_snapshot(representative))

    cardplay_examples: List[CardPlayExample] = []
    cardplay_corrupted = 0
    for snapshot in snapshots:
        examples = build_cardplay_examples_from_snapshot(snapshot)
        if not examples:
            cardplay_corrupted += 1
            corruption_reasons["cardplay:invalid_or_incomplete_snapshot"] += 1
            continue
        cardplay_examples.extend(examples)

    persisted: Dict[str, Dict[str, Optional[Path]]] = {
        "bidding": {"jsonl": None, "parquet": None},
        "cardplay": {"jsonl": None, "parquet": None},
    }
    bidding_rows = _as_dict_rows(bidding_examples)
    cardplay_rows = _as_dict_rows(cardplay_examples)
    for fmt in formats:
        normalized = fmt.lower()
        if normalized == "jsonl":
            bidding_path = output_dir / "bidding_examples.jsonl"
            cardplay_path = output_dir / "cardplay_examples.jsonl"
            write_jsonl(bidding_path, bidding_rows)
            write_jsonl(cardplay_path, cardplay_rows)
            persisted["bidding"]["jsonl"] = bidding_path
            persisted["cardplay"]["jsonl"] = cardplay_path
        elif normalized == "parquet":
            bidding_path = output_dir / "bidding_examples.parquet"
            cardplay_path = output_dir / "cardplay_examples.parquet"
            write_parquet(bidding_path, bidding_rows)
            write_parquet(cardplay_path, cardplay_rows)
            persisted["bidding"]["parquet"] = bidding_path
            persisted["cardplay"]["parquet"] = cardplay_path
        else:
            raise ValueError(f"Unsupported dataset format: {fmt}")

    stats = DatasetBuildStats(
        total_snapshots=len(snapshots),
        unique_deals=len(grouped),
        bidding_examples=len(bidding_examples),
        cardplay_examples=len(cardplay_examples),
        bidding_corrupted_deals=sum(v for k, v in corruption_reasons.items() if k.startswith("bidding:")),
        cardplay_corrupted_snapshots=cardplay_corrupted,
        corruption_reasons=dict(corruption_reasons),
    )
    return stats, persisted
