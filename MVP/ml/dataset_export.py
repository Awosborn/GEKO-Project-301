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

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence

from .preprocess import compute_deal_id, normalize_bid, reconstruct_full_hands

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


def build_cardplay_examples_from_snapshot(snapshot: Mapping[str, object]) -> List[CardPlayExample]:
    """Build one prefix -> next-card example from a post-action snapshot.

    Uses the report's "Option A" inversion strategy:
    - label = last played card
    - pre-state hand = current hand + label card returned to actor
    - pre-state prefix = full play history without the last action
    """
    raw_play_hist = snapshot.get("curr_card_play_hist")
    if not isinstance(raw_play_hist, list) or not raw_play_hist:
        return []

    last_event = raw_play_hist[-1]
    if not isinstance(last_event, Mapping):
        return []

    seat_to_act = int(last_event.get("player", 0))
    if seat_to_act not in PLAYERS:
        return []

    label_next_card = str(last_event.get("card", "")).strip().upper()
    if not label_next_card:
        return []

    raw_hands = snapshot.get("curr_card_hold")
    if not isinstance(raw_hands, list) or len(raw_hands) != 4:
        return []

    hand_cards = [str(card).strip().upper() for card in raw_hands[seat_to_act - 1] if str(card).strip()]
    hand_cards.append(label_next_card)

    auction_bids = [event["bid"] for event in flatten_bid_history(snapshot.get("curr_bid_hist"))]
    play_prefix: List[Dict[str, object]] = []
    for event in raw_play_hist[:-1]:
        if not isinstance(event, Mapping):
            continue
        normalized_event = dict(event)
        if "card" in normalized_event:
            normalized_event["card"] = str(normalized_event["card"]).strip().upper()
        play_prefix.append(normalized_event)

    return [
        CardPlayExample(
            deal_id=compute_deal_id(snapshot),
            board_number=str(snapshot.get("board_number", "")),
            seat_to_act=seat_to_act,
            hand_cards=hand_cards,
            auction_bids=auction_bids,
            play_prefix=play_prefix,
            label_next_card=label_next_card,
        )
    ]
