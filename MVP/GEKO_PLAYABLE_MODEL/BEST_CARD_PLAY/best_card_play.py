"""Standalone runner for the selected GEKO Bridge card-play model.

This file intentionally contains only the card-play inference path.  It does
not import the full MVP codebase, bidding code, training code, or planner code.
Runtime dependency: torch.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple


PLAYERS = (1, 2, 3, 4)
SUITS = ("C", "D", "H", "S")
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
ALL_CARDS = [f"{rank}{suit}" for suit in SUITS for rank in RANKS]
CARD_TO_INDEX = {card: idx for idx, card in enumerate(ALL_CARDS)}


def normalize_card(raw: object) -> str:
    token = str(raw).strip().upper() if raw is not None else ""
    if not token:
        return "UNK"
    if len(token) == 2 and token[0] == "T":
        return f"10{token[1]}"
    return token


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def one_hot(index: int, size: int) -> List[float]:
    values = [0.0] * size
    if 0 <= index < size:
        values[index] = 1.0
    return values


def card_set_vector(cards: Sequence[str]) -> List[float]:
    values = [0.0] * len(ALL_CARDS)
    for raw_card in cards:
        idx = CARD_TO_INDEX.get(normalize_card(raw_card))
        if idx is not None:
            values[idx] = 1.0
    return values


def current_trick_cards_from_play_prefix(play_prefix: object) -> List[str]:
    if not isinstance(play_prefix, list):
        return []
    cards: List[str] = []
    for event in play_prefix:
        if not isinstance(event, Mapping):
            continue
        card = normalize_card(event.get("card"))
        if card != "UNK":
            cards.append(card)
    trick_len = len(cards) % 4
    return cards[-trick_len:] if trick_len else []


def legal_cards(*, hand_cards: Sequence[str], trick_cards: Sequence[str]) -> List[str]:
    hand = [normalize_card(card) for card in hand_cards]
    trick = [normalize_card(card) for card in trick_cards]
    trick = [card for card in trick if card != "UNK"]
    if not trick:
        return [card for card in hand if card != "UNK"]

    lead_suit = trick[0][-1]
    same_suit = [card for card in hand if card.endswith(lead_suit)]
    if same_suit:
        return same_suit
    return [card for card in hand if card != "UNK"]


def normalized_play_events(play_prefix: object) -> List[Dict[str, object]]:
    if not isinstance(play_prefix, list):
        return []
    events: List[Dict[str, object]] = []
    for raw_event in play_prefix:
        if not isinstance(raw_event, Mapping):
            continue
        player = safe_int(raw_event.get("player"), 0)
        card = normalize_card(raw_event.get("card"))
        if player not in PLAYERS or card == "UNK":
            continue
        events.append({"player": player, "card": card})
    return events


def current_trick_events(play_prefix: object) -> List[Tuple[int, str]]:
    events = normalized_play_events(play_prefix)
    remainder = len(events) % 4
    if remainder == 0:
        return []
    return [(safe_int(event.get("player"), 0), str(event.get("card"))) for event in events[-remainder:]]


def partner_of(seat: int) -> int:
    return ((int(seat) + 1) % 4) + 1


def declarer_side(contract: Mapping[str, object]) -> set[int]:
    declarer = safe_int(contract.get("declarer"), 0)
    if declarer not in PLAYERS:
        return set()
    return {declarer, partner_of(declarer)}


def actor_prefers_declarer_tricks(row: Mapping[str, object]) -> bool:
    seat = safe_int(row.get("seat_to_act"), 0)
    contract = row.get("derived_contract", {})
    contract = contract if isinstance(contract, Mapping) else {}
    side = declarer_side(contract)
    return bool(side and seat in side)


def contract_trump(contract: Mapping[str, object]) -> str | None:
    strain = str(contract.get("strain") or "").upper()
    return None if strain in {"", "NT", "NONE"} else strain


def beats(card: str, best: str, *, lead_suit: str, trump: str | None) -> bool:
    card = normalize_card(card)
    best = normalize_card(best)
    if card == "UNK" or best == "UNK":
        return False
    card_suit = card[-1]
    best_suit = best[-1]
    if trump and card_suit == trump and best_suit != trump:
        return True
    if trump and best_suit == trump and card_suit != trump:
        return False
    if card_suit != best_suit:
        return False
    if card_suit != lead_suit and (not trump or card_suit != trump):
        return False
    return RANKS.index(card[:-1]) > RANKS.index(best[:-1])


def trick_winner(trick: Sequence[Tuple[int, str]], *, trump: str | None) -> int:
    if not trick:
        return 0
    winner, winning_card = int(trick[0][0]), normalize_card(trick[0][1])
    lead_suit = winning_card[-1]
    for player, card in trick[1:]:
        candidate = normalize_card(card)
        if beats(candidate, winning_card, lead_suit=lead_suit, trump=trump):
            winner, winning_card = int(player), candidate
    return winner


def completed_tricks_by_seat(play_prefix: object, *, trump: str | None) -> Dict[int, int]:
    events = normalized_play_events(play_prefix)
    tricks = {seat: 0 for seat in PLAYERS}
    for start in range(0, len(events) - (len(events) % 4), 4):
        trick = [(safe_int(event.get("player"), 0), str(event.get("card"))) for event in events[start : start + 4]]
        if len(trick) != 4:
            continue
        winner = trick_winner(trick, trump=trump)
        if winner in PLAYERS:
            tricks[winner] += 1
    return tricks


def side_vulnerability(vulnerability: object, seat: int) -> bool:
    if not isinstance(vulnerability, Mapping):
        return False
    value = vulnerability.get(str(seat), vulnerability.get(seat, False))
    return bool(value)


def public_state_features(row: Mapping[str, object]) -> List[float]:
    seat = safe_int(row.get("seat_to_act"), 0)
    contract = row.get("derived_contract", {})
    contract = contract if isinstance(contract, Mapping) else {}
    trump = contract_trump(contract)
    level = safe_int(contract.get("level"), 0)
    target = level + 6 if level else 0
    play_prefix = row.get("play_prefix", [])
    events = normalized_play_events(play_prefix)
    current_trick = current_trick_events(play_prefix)
    completed = len(events) // 4
    tricks_by_seat = completed_tricks_by_seat(play_prefix, trump=trump)
    declarer_seats = declarer_side(contract)
    declarer_tricks = sum(tricks_by_seat.get(player, 0) for player in declarer_seats)
    defender_tricks = completed - declarer_tricks
    winner = trick_winner(current_trick, trump=trump) if current_trick else 0
    winner_side = 0
    if winner in declarer_seats:
        winner_side = 1
    elif winner in PLAYERS:
        winner_side = 2

    vulnerability = row.get("vulnerability", {})
    declarer = safe_int(contract.get("declarer"), 0)
    defender = next((player for player in PLAYERS if player not in declarer_seats), 0)
    hand = row.get("hand_cards", [])

    return [
        level / 7.0,
        target / 13.0,
        completed / 13.0,
        len(current_trick) / 4.0,
        len(hand if isinstance(hand, list) else []) / 13.0,
        declarer_tricks / 13.0,
        defender_tricks / 13.0,
        1.0 if actor_prefers_declarer_tricks(row) else 0.0,
        1.0 if side_vulnerability(vulnerability, seat) else 0.0,
        1.0 if declarer and side_vulnerability(vulnerability, declarer) else 0.0,
        1.0 if defender and side_vulnerability(vulnerability, defender) else 0.0,
        *one_hot(max(0, len(current_trick)), 4),
        *one_hot(winner - 1, 4),
        *one_hot(winner_side, 3),
    ]


def card_slots(cards: Sequence[str], slots: int = 4) -> List[float]:
    values: List[float] = []
    normalized = [normalize_card(card) for card in cards]
    for slot in range(slots):
        card = normalized[slot] if slot < len(normalized) else ""
        values.extend(one_hot(CARD_TO_INDEX.get(card, -1), len(ALL_CARDS)))
    return values


def seat_one_hot(seat: int) -> List[float]:
    return one_hot(int(seat) - 1, 4)


def strain_one_hot(strain: object) -> List[float]:
    order = ["C", "D", "H", "S", "NT", "UNKNOWN"]
    value = str(strain or "UNKNOWN").upper()
    return one_hot(order.index(value) if value in order else order.index("UNKNOWN"), len(order))


def role_one_hot(role: str) -> List[float]:
    order = ["ROLE_DECLARER", "ROLE_DUMMY", "ROLE_DEFENDER", "ROLE_UNKNOWN"]
    value = role if role in order else "ROLE_UNKNOWN"
    return one_hot(order.index(value), len(order))


def contract_level_one_hot(level: object) -> List[float]:
    return one_hot(safe_int(level, 0), 8)


def role_token(seat: int, contract: Mapping[str, object]) -> str:
    declarer = safe_int(contract.get("declarer"), 0)
    dummy = safe_int(contract.get("dummy"), 0)
    if seat == declarer:
        return "ROLE_DECLARER"
    if seat == dummy:
        return "ROLE_DUMMY"
    if seat in PLAYERS and declarer in PLAYERS:
        return "ROLE_DEFENDER"
    return "ROLE_UNKNOWN"


def played_cards_from_prefix(play_prefix: object) -> List[str]:
    if not isinstance(play_prefix, list):
        return []
    cards: List[str] = []
    for event in play_prefix:
        if isinstance(event, Mapping):
            card = normalize_card(event.get("card"))
            if card != "UNK":
                cards.append(card)
    return cards


def card_feature_vector(row: Mapping[str, object]) -> List[float]:
    seat = safe_int(row.get("seat_to_act"), 0)
    hand = [normalize_card(card) for card in row.get("hand_cards", [])]
    visible_dummy = [
        normalize_card(card)
        for card in row.get("visible_dummy_hand", [])
        if normalize_card(card) != "UNK"
    ]
    play_prefix = row.get("play_prefix", [])
    current_trick = current_trick_cards_from_play_prefix(play_prefix)
    legal = legal_cards(hand_cards=hand, trick_cards=current_trick)
    played = played_cards_from_prefix(play_prefix)
    contract = row.get("derived_contract", {})
    contract = contract if isinstance(contract, Mapping) else {}
    role = role_token(seat, contract)

    features: List[float] = []
    features.extend(seat_one_hot(seat))
    features.extend(card_set_vector(hand))
    features.extend(card_set_vector(legal))
    features.extend(card_slots(current_trick, slots=4))
    features.extend(card_set_vector(played))
    features.extend([len(hand) / 13.0, len(legal) / 13.0, len(current_trick) / 4.0])
    features.extend(one_hot(len(current_trick), 4))
    lead_suit = current_trick[0][-1] if current_trick else "NONE"
    lead_order = ["NONE", "C", "D", "H", "S"]
    features.extend(one_hot(lead_order.index(lead_suit), len(lead_order)))
    suit_counts = {suit: 0 for suit in SUITS}
    for card in hand:
        if card != "UNK":
            suit_counts[card[-1]] += 1
    features.extend([suit_counts[suit] / 13.0 for suit in SUITS])
    features.extend(contract_level_one_hot(contract.get("level")))
    features.extend(strain_one_hot(contract.get("strain")))
    features.extend(role_one_hot(role))
    features.extend(card_set_vector(visible_dummy))
    features.extend([len(visible_dummy) / 13.0, 1.0 if visible_dummy else 0.0])
    dummy_suit_counts = {suit: 0 for suit in SUITS}
    for card in visible_dummy:
        dummy_suit_counts[card[-1]] += 1
    features.extend([dummy_suit_counts[suit] / 13.0 for suit in SUITS])
    features.extend(public_state_features(row))
    return features


def resize_feature_vector(values: Sequence[float], input_dim: int) -> List[float]:
    row = list(values)
    if len(row) == input_dim:
        return row
    if len(row) < input_dim:
        return row + [0.0] * (input_dim - len(row))
    return row[:input_dim]


def softmax(values: Sequence[float]) -> List[float]:
    if not values:
        return []
    max_value = max(values)
    weights = [math.exp(max(-80.0, min(80.0, float(value) - max_value))) for value in values]
    total = sum(weights)
    return [weight / total for weight in weights] if total > 0.0 else [0.0 for _ in values]


def masked_softmax(logits: Sequence[float], legal: Sequence[bool]) -> List[float]:
    legal_logits = [float(logit) for logit, is_legal in zip(logits, legal) if is_legal]
    if not legal_logits:
        return [0.0 for _ in logits]
    max_logit = max(legal_logits)
    weights = [
        math.exp(max(-80.0, min(80.0, float(logit) - max_logit))) if is_legal else 0.0
        for logit, is_legal in zip(logits, legal)
    ]
    total = sum(weights)
    if total <= 0.0:
        legal_count = sum(1 for is_legal in legal if is_legal)
        return [(1.0 / legal_count) if is_legal and legal_count else 0.0 for is_legal in legal]
    return [weight / total for weight in weights]


class BestCardPlayModel:
    """Load and run the packaged best card-play policy model."""

    def __init__(self, model_dir: str | Path | None = None) -> None:
        self.model_dir = Path(model_dir) if model_dir else Path(__file__).resolve().parent / "model"
        self.label_vocab = self._read_labels(self.model_dir / "label_map.json")
        self.config = json.loads((self.model_dir / "card_feature_config.json").read_text(encoding="utf-8"))
        self.input_dim = int(self.config.get("input_dim", 482))
        self.hidden_dim = int(self.config.get("hidden_dim", 512))
        self.model = self._load_model()

    @staticmethod
    def _read_labels(path: Path) -> List[str]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        labels = payload["id_to_label"]
        return [str(labels[str(index)]) for index in range(len(labels))]

    def _load_model(self):
        try:
            import torch
            from torch import nn
        except ImportError as exc:
            raise RuntimeError("This streamlined card-play model requires torch to run.") from exc

        checkpoint_path = self.model_dir / "card_feature_checkpoint_best.pt"
        checkpoint = torch.load(checkpoint_path, map_location="cpu")
        input_dim = int(checkpoint.get("input_dim", self.input_dim))
        hidden_dim = int(checkpoint.get("hidden_dim", self.hidden_dim))
        num_classes = len(self.label_vocab)

        class _CardFeatureMLP(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.net = nn.Sequential(
                    nn.Linear(input_dim, hidden_dim),
                    nn.ReLU(),
                    nn.Dropout(0.05),
                    nn.Linear(hidden_dim, hidden_dim),
                    nn.ReLU(),
                    nn.Linear(hidden_dim, num_classes),
                )

            def forward(self, features):  # type: ignore[no-untyped-def]
                return self.net(features)

        model = _CardFeatureMLP()
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        return model

    def logits_for_row(self, row: Mapping[str, object]) -> List[float]:
        import torch

        vector = resize_feature_vector(card_feature_vector(row), self.input_dim)
        x = torch.tensor([vector], dtype=torch.float32)
        with torch.no_grad():
            logits = self.model(x)[0]
        return [float(value) for value in logits.tolist()]

    def predict(
        self,
        *,
        seat_to_act: int,
        hand_cards: Sequence[str],
        play_prefix: Sequence[Mapping[str, object]] | None = None,
        trick_cards: Sequence[str] | None = None,
        auction_bids: Sequence[str] | None = None,
        derived_contract: Mapping[str, object] | None = None,
        visible_dummy_hand: Sequence[str] | None = None,
        vulnerability: Mapping[str, bool] | None = None,
        top_k: int = 5,
    ) -> Dict[str, object]:
        prefix = list(play_prefix or [])
        if not prefix and trick_cards:
            prefix = [{"player": index + 1, "card": card} for index, card in enumerate(trick_cards)]
        current_trick = list(trick_cards or current_trick_cards_from_play_prefix(prefix))
        hand = [normalize_card(card) for card in hand_cards]
        legal = set(legal_cards(hand_cards=hand, trick_cards=current_trick))
        row = {
            "seat_to_act": int(seat_to_act),
            "auction_bids": list(auction_bids or []),
            "play_prefix": prefix,
            "hand_cards": hand,
            "derived_contract": dict(derived_contract or {}),
            "visible_dummy_hand": [normalize_card(card) for card in (visible_dummy_hand or [])],
            "vulnerability": dict(vulnerability or {}),
        }
        logits = self.logits_for_row(row)
        raw_probs = softmax(logits)
        legal_mask = [label in legal for label in self.label_vocab]
        legal_probs = masked_softmax(logits, legal_mask)
        legal_logits = [logit for logit, is_legal in zip(logits, legal_mask) if is_legal]
        max_legal_logit = max(legal_logits) if legal_logits else 0.0

        rows: List[Dict[str, object]] = []
        for label, probability, raw_probability, logit, is_legal in zip(
            self.label_vocab, legal_probs, raw_probs, logits, legal_mask
        ):
            if not is_legal:
                continue
            rows.append(
                {
                    "card": label,
                    "probability": float(probability),
                    "raw_model_probability": float(raw_probability),
                    "raw_model_logit": float(logit),
                    "relative_policy_weight": float(math.exp(max(-80.0, min(80.0, logit - max_legal_logit)))),
                }
            )
        rows.sort(key=lambda item: float(item["probability"]), reverse=True)
        return {
            "recommended_card": rows[0]["card"] if rows else None,
            "top_k": rows[: max(1, int(top_k))],
            "legal_cards": sorted(legal, key=ALL_CARDS.index),
            "model_type": str(self.config.get("model_type", "card_outcome_policy_mlp")),
            "source": "BEST_CARD_PLAY/model",
        }


def parse_cards(raw: str | None) -> List[str]:
    if not raw:
        return []
    tokens = raw.replace(",", " ").split()
    return [normalize_card(token) for token in tokens if normalize_card(token) != "UNK"]


def parse_play_prefix(raw: str | None) -> List[Dict[str, object]]:
    if not raw:
        return []
    candidate = Path(raw)
    try:
        is_path = candidate.exists()
    except OSError:
        is_path = False
    text = candidate.read_text(encoding="utf-8") if is_path else raw
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise ValueError("--play-prefix-json must be a JSON list of {player, card} objects")
    events: List[Dict[str, object]] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        events.append({"player": safe_int(item.get("player"), 0), "card": normalize_card(item.get("card"))})
    return events


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the packaged best GEKO card-play model.")
    parser.add_argument("--model-dir", type=Path, default=Path(__file__).resolve().parent / "model")
    parser.add_argument("--seat", type=int, required=True, help="Seat to act: 1, 2, 3, or 4.")
    parser.add_argument("--hand", required=True, help='Cards in hand, for example "5C 8C 10C".')
    parser.add_argument("--trick", default="", help='Current trick cards if no play-prefix JSON is supplied.')
    parser.add_argument("--play-prefix-json", default="", help="JSON string or path with full play prefix events.")
    parser.add_argument("--auction", default="", help='Auction bids, for example "1NT P 3NT P P P".')
    parser.add_argument("--visible-dummy", default="", help="Visible dummy cards, if dummy is exposed.")
    parser.add_argument("--contract-level", type=int, default=0)
    parser.add_argument("--contract-strain", default="", choices=["", "C", "D", "H", "S", "NT"])
    parser.add_argument("--declarer", type=int, default=0)
    parser.add_argument("--dummy", type=int, default=0)
    parser.add_argument("--top-k", type=int, default=5)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    contract = {
        key: value
        for key, value in {
            "level": args.contract_level or None,
            "strain": args.contract_strain or None,
            "declarer": args.declarer or None,
            "dummy": args.dummy or None,
        }.items()
        if value is not None
    }
    model = BestCardPlayModel(args.model_dir)
    result = model.predict(
        seat_to_act=args.seat,
        hand_cards=parse_cards(args.hand),
        trick_cards=parse_cards(args.trick),
        play_prefix=parse_play_prefix(args.play_prefix_json),
        auction_bids=args.auction.split() if args.auction else [],
        derived_contract=contract,
        visible_dummy_hand=parse_cards(args.visible_dummy),
        top_k=args.top_k,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
