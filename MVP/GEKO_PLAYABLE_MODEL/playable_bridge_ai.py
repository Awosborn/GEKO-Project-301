"""Playable standalone GEKO Bridge AI package.

This runner loads the packaged bidding model and card-play model without
importing the full MVP training tree.

Examples:
  python playable_bridge_ai.py --mode ai-only --boards 1 --strategy-profile 1 --show-hands
  python playable_bridge_ai.py --mode bid --strategy-profile 1 --seat 1 --hand "AS KS QS JS 2H 3H 4D 5D 6C 7C 8C 9C 10C"
  python playable_bridge_ai.py --mode card --seat 1 --hand "5C 8C 10C JC" --trick "2C AC 3C"
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

PACKAGE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_ROOT))

from BEST_CARD_PLAY.best_card_play import (  # noqa: E402
    ALL_CARDS,
    BestCardPlayModel,
    legal_cards,
    normalize_card,
    trick_winner,
)


PLAYERS = (1, 2, 3, 4)
SUITS = ("C", "D", "H", "S")
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
HCP_BY_RANK = {"A": 4, "K": 3, "Q": 2, "J": 1}
TRUMP_ORDER = {"C": 0, "D": 1, "H": 2, "S": 3, "NT": 4}
CONTRACT_BIDS = [f"{level}{strain}" for level in range(1, 8) for strain in ("C", "D", "H", "S", "NT")]
ALL_BIDS = ["P", "X", "XX", *CONTRACT_BIDS]
BIDDING_PHASES = ("opening", "response", "rebid", "competitive", "game_slam", "unknown")

STRATEGY_ANSWER_COUNT = 75
IDX_OPEN_MIN_1ST = 0
IDX_OPEN_MIN_2ND = 1
IDX_OPEN_MIN_3RD = 2
IDX_OPEN_MIN_4TH = 3
IDX_MAJOR_STYLE = 4
IDX_MINOR_STYLE = 5
IDX_1NT_MIN = 6
IDX_1NT_MAX = 7
IDX_MEANING_2D = 12
IDX_MEANING_2H = 13
IDX_MEANING_2S = 14
IDX_WEAK_TWO_STYLE = 15
IDX_3_LEVEL_PREEMPT_STYLE = 16
IDX_PREEMPT_VULN_ADJUSTMENT = 17
IDX_MAJOR_OPEN_LENGTH = 18


def normalize_bid(raw: object) -> str:
    token = str(raw).strip() if raw is not None else ""
    if not token:
        return "UNK"
    lower = token.lower()
    if lower in {"pass", "p"}:
        return "P"
    if lower in {"d", "x"}:
        return "X"
    if lower in {"r", "xx"}:
        return "XX"
    token = token.upper()
    if len(token) == 2 and token[0] in "1234567" and token[1] == "N":
        return f"{token[0]}NT"
    return token


def parse_cards(raw: str | None) -> List[str]:
    if not raw:
        return []
    return [normalize_card(part) for part in raw.replace(",", " ").split() if normalize_card(part) != "UNK"]


def parse_bids(raw: str | None) -> List[str]:
    if not raw:
        return []
    return [normalize_bid(part) for part in raw.replace(",", " ").split() if normalize_bid(part) != "UNK"]


def partnership(seat: int) -> int:
    return 0 if int(seat) in {1, 3} else 1


def partner_of(seat: int) -> int:
    return ((int(seat) + 1) % 4) + 1


def seat_after_calls(dealer: int, call_count: int) -> int:
    return ((int(dealer) - 1 + int(call_count)) % 4) + 1


def seat_relative_to_dealer(seat: int, dealer: int) -> int:
    return (int(seat) - int(dealer)) % 4


def _bid_rank(contract_bid: str) -> int:
    return (int(contract_bid[0]) - 1) * 5 + TRUMP_ORDER[contract_bid[1:]]


def _last_contract(prefix: Sequence[str]) -> Tuple[str, int] | None:
    for idx in range(len(prefix) - 1, -1, -1):
        bid = normalize_bid(prefix[idx])
        if len(bid) >= 2 and bid[0] in "1234567" and bid[1:] in TRUMP_ORDER:
            return bid, (idx % 4) + 1
    return None


def _last_non_pass_action(prefix: Sequence[str]) -> Tuple[str, int] | None:
    for idx in range(len(prefix) - 1, -1, -1):
        bid = normalize_bid(prefix[idx])
        if bid != "P":
            return bid, (idx % 4) + 1
    return None


def is_legal_bid(candidate_bid: str, *, seat_to_act: int, bid_prefix: Sequence[str]) -> bool:
    bid = normalize_bid(candidate_bid)
    if bid == "P":
        return True

    last_contract = _last_contract(bid_prefix)
    last_non_pass = _last_non_pass_action(bid_prefix)

    if bid == "X":
        if not last_contract:
            return False
        _, contract_player = last_contract
        if partnership(seat_to_act) == partnership(contract_player):
            return False
        if last_non_pass and last_non_pass[0] in {"X", "XX"}:
            return False
        return True

    if bid == "XX":
        if not last_non_pass or last_non_pass[0] != "X" or not last_contract:
            return False
        _, contract_player = last_contract
        return partnership(seat_to_act) == partnership(contract_player)

    if len(bid) < 2 or bid[0] not in "1234567" or bid[1:] not in TRUMP_ORDER:
        return False
    if last_contract and _bid_rank(bid) <= _bid_rank(last_contract[0]):
        return False
    return True


def legal_bids(*, seat_to_act: int, bid_prefix: Sequence[str]) -> List[str]:
    return [bid for bid in ALL_BIDS if is_legal_bid(bid, seat_to_act=seat_to_act, bid_prefix=bid_prefix)]


def is_contract_bid(token: str) -> bool:
    bid = normalize_bid(token)
    return len(bid) >= 2 and bid[0] in "1234567" and bid[1:] in TRUMP_ORDER


def auction_complete(bids: Sequence[str]) -> bool:
    normalized = [normalize_bid(bid) for bid in bids]
    if len(normalized) >= 4 and all(bid == "P" for bid in normalized[:4]):
        return True
    for index, bid in enumerate(normalized):
        if is_contract_bid(bid):
            return len(normalized[index + 1 :]) >= 3 and normalized[-3:] == ["P", "P", "P"]
    return False


def bidding_phase_from_prefix(bid_prefix: Sequence[str], *, seat_to_act: int, dealer: int) -> str:
    normalized = [normalize_bid(bid) for bid in bid_prefix]
    contract_events: List[Tuple[int, str, int]] = []
    for index, bid in enumerate(normalized):
        if is_contract_bid(bid):
            contract_events.append((index, bid, seat_after_calls(dealer, index)))

    if not contract_events:
        return "opening"

    last_level = int(contract_events[-1][1][0])
    if last_level >= 4 or (last_level == 3 and contract_events[-1][1][1:] == "NT"):
        return "game_slam"

    sides = {partnership(seat) for _, _, seat in contract_events}
    bidder_side = partnership(seat_to_act)
    opener_side = partnership(contract_events[0][2])
    if len(sides) > 1 or bidder_side != opener_side:
        return "competitive"

    if len(contract_events) == 1 and seat_to_act == partner_of(contract_events[0][2]):
        return "response"
    return "rebid"


def derive_final_contract(bids: Sequence[str], *, dealer: int) -> Dict[str, object]:
    contracts: List[Tuple[int, str, int]] = []
    for index, bid in enumerate(bids):
        normalized = normalize_bid(bid)
        if is_contract_bid(normalized):
            contracts.append((index, normalized, seat_after_calls(dealer, index)))

    if not contracts:
        return {"level": None, "strain": None, "multiplier": "", "contract_seat": None, "declarer": None, "dummy": None}

    last_index, final_bid, contract_seat = contracts[-1]
    strain = final_bid[1:]
    declarer_side = partnership(contract_seat)
    declarer = contract_seat
    for _, earlier_bid, earlier_seat in contracts:
        if earlier_bid[1:] == strain and partnership(earlier_seat) == declarer_side:
            declarer = earlier_seat
            break
    after_contract = [normalize_bid(bid) for bid in bids[last_index + 1 :]]
    multiplier = "XX" if "XX" in after_contract else "X" if "X" in after_contract else ""
    return {
        "level": int(final_bid[0]),
        "strain": strain,
        "multiplier": multiplier,
        "contract_seat": contract_seat,
        "declarer": declarer,
        "dummy": partner_of(declarer),
    }


def load_strategy_profiles() -> List[Dict[str, object]]:
    path = PACKAGE_ROOT / "strategy_profiles_numeric.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("profiles", []))


def strategy_answers_for_profile(profile_index: int | None) -> List[int]:
    if profile_index is None:
        return []
    for profile in load_strategy_profiles():
        if int(profile.get("index", 0)) == int(profile_index):
            return [int(value) for value in profile.get("numeric_answers", [])]
    raise ValueError(f"Unknown strategy profile {profile_index}. Use --list-profiles.")


def strategy_feature_values(strategy_answers: Sequence[int]) -> List[float]:
    answers = [int(value) for value in strategy_answers]
    complete = len(answers) >= STRATEGY_ANSWER_COUNT
    padded = answers[:STRATEGY_ANSWER_COUNT] + [0] * max(0, STRATEGY_ANSWER_COUNT - len(answers))
    values = [1.0 if complete else 0.0, len(answers[:STRATEGY_ANSWER_COUNT]) / float(STRATEGY_ANSWER_COUNT)]
    values.extend(max(-1.0, min(1.0, float(value) / 30.0)) for value in padded)
    return values


def hand_hcp(hand: Sequence[str]) -> int:
    return sum(HCP_BY_RANK.get(normalize_card(card)[:-1], 0) for card in hand)


def suit_length(hand: Sequence[str], suit: str) -> int:
    return sum(1 for card in hand if normalize_card(card).endswith(suit))


def opening_minimum_for_seat(strategy_answers: Sequence[int], seat: int) -> int:
    mapping = {1: IDX_OPEN_MIN_1ST, 2: IDX_OPEN_MIN_2ND, 3: IDX_OPEN_MIN_3RD, 4: IDX_OPEN_MIN_4TH}
    return int(strategy_answers[mapping[int(seat)]])


def side_has_non_pass_call(bid_prefix: Sequence[str], *, seat_to_act: int, dealer: int) -> bool:
    side = partnership(seat_to_act)
    for index, raw_bid in enumerate(bid_prefix):
        bid = normalize_bid(raw_bid)
        if bid in {"", "P", "UNK"}:
            continue
        prior_seat = seat_after_calls(dealer, index)
        if partnership(prior_seat) == side:
            return True
    return False


def bid_follows_strategy(
    bid: str,
    hand: Sequence[str],
    strategy_answers: Sequence[int],
    *,
    seat: int,
    is_opening_bid: bool,
    vulnerability: bool = False,
) -> Tuple[bool, str]:
    answers = [int(value) for value in strategy_answers]
    normalized = normalize_bid(bid)
    if not answers:
        return True, "No strategy declaration supplied."
    if len(answers) < STRATEGY_ANSWER_COUNT:
        return False, "Strategy declaration is incomplete."
    if normalized in {"P", "X", "XX"}:
        return True, f"{normalized} accepted."
    if len(normalized) < 2 or normalized[0] not in "1234567":
        return False, "Invalid contract bid."

    level = int(normalized[0])
    strain = normalized[1:]
    hcp = hand_hcp(hand)
    if is_opening_bid:
        open_min = opening_minimum_for_seat(answers, seat)
        if hcp < open_min:
            return False, f"{hcp} HCP below seat-{seat} opening minimum {open_min}."

    if normalized == "1NT":
        nt_min = int(answers[IDX_1NT_MIN])
        nt_max = int(answers[IDX_1NT_MAX])
        if not (nt_min <= hcp <= nt_max):
            return False, f"{hcp} HCP outside 1NT range {nt_min}-{nt_max}."

    if is_opening_bid and level == 1 and strain in {"H", "S"}:
        min_len = 5 if int(answers[IDX_MAJOR_OPEN_LENGTH]) == 1 else 4
        held = suit_length(hand, strain)
        if held < min_len:
            return False, f"{strain} length {held} below required {min_len}+."

    if is_opening_bid and level == 2 and strain in {"D", "H", "S"}:
        meaning_idx = {"D": IDX_MEANING_2D, "H": IDX_MEANING_2H, "S": IDX_MEANING_2S}[strain]
        if int(answers[meaning_idx]) != 1:
            return False, f"{normalized} not defined as weak two."
        cap = {2: 11, 3: 10, 4: 9}.get(int(answers[IDX_WEAK_TWO_STYLE]), 10)
        if hcp > cap:
            return False, f"Weak-two HCP {hcp} exceeds cap {cap}."
        if vulnerability and int(answers[IDX_PREEMPT_VULN_ADJUSTMENT]) == 1 and hcp > max(6, cap - 1):
            return False, "Vulnerable preempt too heavy for style."

    if is_opening_bid and level == 3 and strain in SUITS:
        if suit_length(hand, strain) < 7:
            return False, "3-level preempt requires 7+ cards."
        cap = {1: 9, 2: 8, 3: 8, 4: 7}.get(int(answers[IDX_3_LEVEL_PREEMPT_STYLE]), 8)
        if hcp > cap:
            return False, f"3-level preempt HCP {hcp} exceeds cap {cap}."

    if is_opening_bid and level == 1 and strain in SUITS:
        style_idx = IDX_MAJOR_STYLE if strain in {"H", "S"} else IDX_MINOR_STYLE
        penalty = {1: 1, 2: 0, 3: -1, 4: -2, 5: -2}.get(int(answers[style_idx]), 0)
        required = opening_minimum_for_seat(answers, seat) + penalty
        if hcp < required:
            return False, f"{hcp} HCP below style-adjusted minimum {required}."

    return True, "Compatible with strategy declaration."


def vulnerability_by_seat(raw: object) -> Dict[int, bool]:
    vulnerability = {seat: False for seat in PLAYERS}
    if not isinstance(raw, Mapping):
        return vulnerability
    for seat in PLAYERS:
        vulnerability[seat] = bool(raw.get(str(seat), raw.get(seat, False)))
    return vulnerability


def trailing_passes(bid_prefix: Sequence[str]) -> float:
    count = 0
    for raw_bid in reversed(bid_prefix):
        if normalize_bid(raw_bid) != "P":
            break
        count += 1
    return float(min(count, 4))


def last_action_features(bid_prefix: Sequence[str]) -> List[float]:
    if not bid_prefix:
        action = "NONE"
    else:
        last = normalize_bid(bid_prefix[-1])
        action = last if last in {"P", "X", "XX"} else "CONTRACT"
    return [1.0 if action == candidate else 0.0 for candidate in ("NONE", "P", "X", "XX", "CONTRACT")]


def last_contract_features(bid_prefix: Sequence[str]) -> List[float]:
    last_contract = None
    for raw_bid in reversed(bid_prefix):
        bid = normalize_bid(raw_bid)
        if is_contract_bid(bid):
            last_contract = bid
            break
    if last_contract is None:
        return [0.0] * 8
    level = int(last_contract[0])
    strain = last_contract[1:]
    rank = ((level - 1) * 5 + TRUMP_ORDER[strain] + 1) / 35.0
    return [1.0, level / 7.0, rank, *[1.0 if strain == candidate else 0.0 for candidate in ("C", "D", "H", "S", "NT")]]


def legal_bid_features(legal: set[str]) -> List[float]:
    levels = [int(bid[0]) for bid in legal if is_contract_bid(bid)]
    return [
        len(legal) / float(len(ALL_BIDS)),
        1.0 if "P" in legal else 0.0,
        1.0 if "X" in legal else 0.0,
        1.0 if "XX" in legal else 0.0,
        (min(levels) / 7.0) if levels else 0.0,
    ]


def context_features(row: Mapping[str, object], seat: int) -> List[float]:
    dealer = int(row.get("dealer", 1))
    relative_position = int(row.get("seat_relative_to_dealer", seat_relative_to_dealer(seat, dealer))) % 4
    vuln = vulnerability_by_seat(row.get("vulnerability", {}))
    partner = partner_of(seat) if seat in PLAYERS else 0
    opponents = [candidate for candidate in PLAYERS if candidate not in {seat, partner}]
    seat_vulnerable = vuln.get(seat, False)
    partner_vulnerable = vuln.get(partner, False)
    opponents_vulnerable = any(vuln.get(candidate, False) for candidate in opponents)
    phase = str(row.get("bidding_phase", "unknown"))
    if phase not in BIDDING_PHASES:
        phase = "unknown"
    auction_index = int(row.get("auction_index", len(row.get("bid_prefix", []))))
    values: List[float] = []
    values.extend(1.0 if dealer == candidate else 0.0 for candidate in PLAYERS)
    values.extend(1.0 if relative_position == candidate else 0.0 for candidate in range(4))
    values.extend(1.0 if vuln.get(candidate, False) else 0.0 for candidate in PLAYERS)
    values.extend(
        [
            1.0 if seat_vulnerable else 0.0,
            1.0 if partner_vulnerable else 0.0,
            1.0 if opponents_vulnerable else 0.0,
            1.0 if seat_vulnerable and opponents_vulnerable else 0.0,
            1.0 if not seat_vulnerable and not opponents_vulnerable else 0.0,
        ]
    )
    values.extend(1.0 if phase == candidate else 0.0 for candidate in BIDDING_PHASES)
    values.append(min(max(auction_index, 0), 64) / 64.0)
    return values


def bid_feature_vector(row: Mapping[str, object]) -> List[float]:
    seat = int(row.get("seat_to_act", 0))
    hand_cards = [normalize_card(card) for card in row.get("hand_cards", [])]
    bid_prefix = [normalize_bid(bid) for bid in row.get("bid_prefix", [])]
    suit_lengths = {suit: 0 for suit in SUITS}
    suit_hcp = {suit: 0 for suit in SUITS}
    hand_set = set(hand_cards)
    hcp = 0
    card_bits: List[float] = []
    for suit in SUITS:
        for rank in RANKS:
            card = f"{rank}{suit}"
            present = 1.0 if card in hand_set else 0.0
            card_bits.append(present)
            if present:
                suit_lengths[suit] += 1
                points = HCP_BY_RANK.get(rank, 0)
                hcp += points
                suit_hcp[suit] += points

    sorted_lengths = sorted(suit_lengths.values(), reverse=True)
    balanced = tuple(sorted_lengths) in {(4, 3, 3, 3), (4, 4, 3, 2), (5, 3, 3, 2)}
    legal = set(legal_bids(seat_to_act=seat, bid_prefix=bid_prefix))

    features: List[float] = []
    features.extend(1.0 if seat == candidate else 0.0 for candidate in PLAYERS)
    features.extend(card_bits)
    features.append(hcp / 40.0)
    features.extend(suit_lengths[suit] / 13.0 for suit in SUITS)
    features.extend(suit_hcp[suit] / 10.0 for suit in SUITS)
    features.extend(length / 13.0 for length in sorted_lengths)
    features.append(1.0 if balanced else 0.0)
    features.append(min(len(bid_prefix), 64) / 64.0)
    features.append(trailing_passes(bid_prefix) / 4.0)
    features.extend(last_action_features(bid_prefix))
    features.extend(last_contract_features(bid_prefix))
    features.extend(legal_bid_features(legal))
    features.extend(context_features(row, seat))
    features.extend(strategy_feature_values(row.get("strategy_answers", [])))
    return features


def resize_feature_vector(features: Sequence[float], target_dim: int) -> List[float]:
    values = [float(value) for value in features]
    if len(values) >= target_dim:
        return values[:target_dim]
    return values + [0.0] * (target_dim - len(values))


def softmax(values: Sequence[float]) -> List[float]:
    if not values:
        return []
    max_value = max(float(value) for value in values)
    weights = [math.exp(max(-80.0, min(80.0, float(value) - max_value))) for value in values]
    total = sum(weights)
    return [weight / total for weight in weights] if total > 0 else [0.0 for _ in values]


def calibration_bucket(bid_prefix: Sequence[str]) -> str:
    bids = [normalize_bid(bid) for bid in bid_prefix]
    if not bids or all(bid == "P" for bid in bids):
        return "unopened"
    last_contract_index = -1
    last_contract_level = 0
    for index, bid in enumerate(bids):
        if is_contract_bid(bid):
            last_contract_index = index
            last_contract_level = int(bid[0])
    if last_contract_level >= 3:
        return "high_contract"
    if last_contract_index >= 0 and any(bid in {"X", "XX"} for bid in bids[last_contract_index + 1 :]):
        return "doubled"
    if len(bids) >= 6:
        return "late_auction"
    return "competitive"


def select_label_biases(calibration: Mapping[str, object] | None, bid_prefix: Sequence[str]) -> Mapping[str, float]:
    if not calibration:
        return {}
    aggregate = calibration.get("aggregate", {})
    aggregate_biases = aggregate.get("biases", {}) if isinstance(aggregate, Mapping) else {}
    buckets = calibration.get("buckets", {})
    bucket_name = calibration_bucket(bid_prefix)
    if isinstance(buckets, Mapping):
        bucket = buckets.get(bucket_name)
        if isinstance(bucket, Mapping) and int(bucket.get("count", 0)) >= int(calibration.get("min_bucket_count", 200)):
            biases = bucket.get("biases", {})
            if isinstance(biases, Mapping):
                return {str(label): float(value) for label, value in biases.items()}
    if isinstance(aggregate_biases, Mapping):
        return {str(label): float(value) for label, value in aggregate_biases.items()}
    return {}


def apply_label_biases(probabilities: Sequence[float], labels: Sequence[str], label_biases: Mapping[str, float]) -> List[float]:
    if not label_biases:
        return [float(probability) for probability in probabilities]
    adjusted = [
        max(0.0, float(probability)) * math.exp(float(label_biases.get(str(label), 0.0)))
        for probability, label in zip(probabilities, labels)
    ]
    total = sum(adjusted)
    return [value / total for value in adjusted] if total > 0 else [float(probability) for probability in probabilities]


def masked_probs(probabilities: Sequence[float], legal_mask: Sequence[bool]) -> List[float]:
    values = [float(probability) if is_legal else 0.0 for probability, is_legal in zip(probabilities, legal_mask)]
    total = sum(values)
    if total > 0:
        return [value / total for value in values]
    legal_count = sum(1 for is_legal in legal_mask if is_legal)
    return [(1.0 / legal_count) if is_legal and legal_count else 0.0 for is_legal in legal_mask]


class BiddingModel:
    def __init__(self, model_dir: str | Path | None = None) -> None:
        self.model_dir = Path(model_dir) if model_dir else PACKAGE_ROOT / "BEST_BIDDING" / "model"
        self.label_vocab = self._read_labels(self.model_dir / "label_map.json")
        self.config = json.loads((self.model_dir / "bid_feature_config.json").read_text(encoding="utf-8"))
        self.calibration = self._read_optional_json(self.model_dir / "calibration.json")
        self.input_dim = int(self.config.get("input_dim", 191))
        self.hidden_dim = int(self.config.get("hidden_dim", 512))
        self.model = self._load_model()

    @staticmethod
    def _read_labels(path: Path) -> List[str]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        labels = payload["id_to_label"]
        return [str(labels[str(index)]) for index in range(len(labels))]

    @staticmethod
    def _read_optional_json(path: Path) -> Mapping[str, object] | None:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, Mapping) else None

    def _load_model(self):
        try:
            import torch
            from torch import nn
        except ImportError as exc:
            raise RuntimeError("This playable package requires torch. Run: pip install -r requirements.txt") from exc

        checkpoint = torch.load(self.model_dir / "bid_feature_checkpoint_best.pt", map_location="cpu")
        input_dim = int(checkpoint.get("input_dim", self.input_dim))
        hidden_dim = int(checkpoint.get("hidden_dim", self.hidden_dim))
        num_classes = len(self.label_vocab)

        class _BidFeatureMLP(nn.Module):
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

        model = _BidFeatureMLP()
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        return model

    def logits_for_row(self, row: Mapping[str, object]) -> List[float]:
        import torch

        vector = resize_feature_vector(bid_feature_vector(row), self.input_dim)
        x = torch.tensor([vector], dtype=torch.float32)
        with torch.no_grad():
            logits = self.model(x)[0]
        return [float(value) for value in logits.tolist()]

    def predict(
        self,
        *,
        seat_to_act: int,
        hand_cards: Sequence[str],
        bid_prefix: Sequence[str],
        dealer: int,
        vulnerability: Mapping[str, bool] | None,
        strategy_answers: Sequence[int],
        top_k: int = 5,
    ) -> Dict[str, object]:
        prefix = [normalize_bid(bid) for bid in bid_prefix]
        hand = [normalize_card(card) for card in hand_cards]
        row = {
            "dealer": int(dealer),
            "seat_to_act": int(seat_to_act),
            "seat_relative_to_dealer": seat_relative_to_dealer(seat_to_act, dealer),
            "auction_index": len(prefix),
            "bid_prefix": prefix,
            "hand_cards": hand,
            "vulnerability": dict(vulnerability or {}),
            "bidding_phase": bidding_phase_from_prefix(prefix, seat_to_act=seat_to_act, dealer=dealer),
            "strategy_answers": [int(value) for value in strategy_answers],
        }
        raw_probs = softmax(self.logits_for_row(row))
        raw_probs = apply_label_biases(raw_probs, self.label_vocab, select_label_biases(self.calibration, prefix))
        legal_set = set(legal_bids(seat_to_act=seat_to_act, bid_prefix=prefix))
        strategy_complete = len(strategy_answers) >= STRATEGY_ANSWER_COUNT
        legal_mask: List[bool] = []
        rejections: Dict[str, str] = {}
        vuln = vulnerability_by_seat(vulnerability or {})
        for label in self.label_vocab:
            legal = normalize_bid(label) in legal_set
            if legal and strategy_complete:
                follows, reason = bid_follows_strategy(
                    label,
                    hand,
                    strategy_answers,
                    seat=seat_to_act,
                    is_opening_bid=not side_has_non_pass_call(prefix, seat_to_act=seat_to_act, dealer=dealer),
                    vulnerability=vuln.get(seat_to_act, False),
                )
                if not follows:
                    rejections[str(label)] = reason
                    legal = False
            legal_mask.append(legal)
        constrained = masked_probs(raw_probs, legal_mask)
        rows = [
            {"bid": str(label), "probability": float(probability), "raw_model_probability": float(raw)}
            for label, probability, raw, is_legal in zip(self.label_vocab, constrained, raw_probs, legal_mask)
            if is_legal
        ]
        rows.sort(key=lambda item: float(item["probability"]), reverse=True)
        return {
            "recommended_bid": rows[0]["bid"] if rows else "P",
            "top_k": rows[: max(1, int(top_k))],
            "legal_bids": [bid for bid in self.label_vocab if normalize_bid(bid) in legal_set],
            "strategy_guardrails_applied": strategy_complete,
            "strategy_rejections": rejections,
        }


def sort_hand(cards: Sequence[str]) -> List[str]:
    order = {card: index for index, card in enumerate(ALL_CARDS)}
    return sorted([normalize_card(card) for card in cards], key=lambda card: order.get(card, 999))


def deal_hands(seed: int) -> Dict[int, List[str]]:
    deck = list(ALL_CARDS)
    rng = random.Random(seed)
    rng.shuffle(deck)
    return {seat: sort_hand(deck[(seat - 1) * 13 : seat * 13]) for seat in PLAYERS}


def print_hands(hands: Mapping[int, Sequence[str]]) -> None:
    for seat in PLAYERS:
        print(f"Player {seat}: {' '.join(hands[seat])}")


def play_bidding(
    bidding_model: BiddingModel,
    hands: Mapping[int, Sequence[str]],
    *,
    dealer: int,
    vulnerability: Mapping[str, bool],
    strategy_answers: Sequence[int],
    top_k: int,
) -> List[str]:
    bids: List[str] = []
    print("\nBidding")
    while not auction_complete(bids) and len(bids) < 64:
        seat = seat_after_calls(dealer, len(bids))
        result = bidding_model.predict(
            seat_to_act=seat,
            hand_cards=hands[seat],
            bid_prefix=bids,
            dealer=dealer,
            vulnerability=vulnerability,
            strategy_answers=strategy_answers,
            top_k=top_k,
        )
        bid = str(result["recommended_bid"])
        bids.append(bid)
        probs = ", ".join(f"{row['bid']}:{float(row['probability']) * 100:.1f}%" for row in result["top_k"])
        print(f"P{seat}: {bid}   model: {probs}")
    print(f"Auction: {' '.join(bids)}")
    return bids


def play_cards(
    card_model: BestCardPlayModel,
    hands: Mapping[int, Sequence[str]],
    *,
    contract: Mapping[str, object],
    bids: Sequence[str],
    vulnerability: Mapping[str, bool],
    top_k: int,
) -> Dict[int, int]:
    declarer = int(contract.get("declarer") or 0)
    dummy = int(contract.get("dummy") or 0)
    if declarer not in PLAYERS:
        return {seat: 0 for seat in PLAYERS}
    leader = seat_after_calls(declarer, 1)
    active = {seat: list(hands[seat]) for seat in PLAYERS}
    play_prefix: List[Dict[str, object]] = []
    tricks = {seat: 0 for seat in PLAYERS}
    trump = None if str(contract.get("strain") or "NT") == "NT" else str(contract.get("strain"))

    print("\nCard Play")
    print(f"Contract: {contract.get('level')}{contract.get('strain')} by Player {declarer}; dummy Player {dummy}")
    for trick_no in range(1, 14):
        order = [seat_after_calls(leader, offset) for offset in range(4)]
        trick: List[Tuple[int, str]] = []
        print(f"\nTrick {trick_no} order: {' '.join('P' + str(seat) for seat in order)}")
        for seat in order:
            visible_dummy = active[dummy] if play_prefix else []
            result = card_model.predict(
                seat_to_act=seat,
                hand_cards=active[seat],
                play_prefix=play_prefix,
                auction_bids=bids,
                derived_contract=contract,
                visible_dummy_hand=visible_dummy,
                vulnerability=vulnerability,
                top_k=top_k,
            )
            card = str(result["recommended_card"])
            if card not in active[seat]:
                legal = legal_cards(hand_cards=active[seat], trick_cards=[card for _, card in trick])
                card = legal[0]
            active[seat].remove(card)
            play_prefix.append({"player": seat, "card": card})
            trick.append((seat, card))
            probs = ", ".join(f"{row['card']}:{float(row['probability']) * 100:.1f}%" for row in result["top_k"])
            print(f"P{seat}: {card}   model: {probs}")
            if seat == leader and dummy in PLAYERS and active[dummy]:
                print(f"Dummy hand P{dummy}: {' '.join(active[dummy])}")
        winner = trick_winner(trick, trump=trump)
        tricks[winner] += 1
        print(f"Trick winner: Player {winner}")
        leader = winner
    ns = tricks[1] + tricks[3]
    ew = tricks[2] + tricks[4]
    side = {declarer, partner_of(declarer)}
    declarer_tricks = sum(tricks[seat] for seat in side)
    target = int(contract.get("level") or 0) + 6
    delta = declarer_tricks - target
    print(f"\nTricks by seat: {tricks}")
    print(f"Partnership tricks: NS={ns} EW={ew}")
    print(f"Contract result: declarer side took {declarer_tricks}/{target} tricks ({'made' if delta >= 0 else 'down'} {abs(delta) if delta else ''})")
    return tricks


def list_profiles() -> None:
    for profile in load_strategy_profiles():
        print(f"{int(profile['index']):2d}. {profile['name']}")


def run_ai_only(args: argparse.Namespace) -> None:
    bidding_model = BiddingModel()
    card_model = BestCardPlayModel(PACKAGE_ROOT / "BEST_CARD_PLAY" / "model")
    strategy_answers = strategy_answers_for_profile(args.strategy_profile)
    for board in range(1, int(args.boards) + 1):
        print(f"\n=== Board {board} ===")
        hands = deal_hands(int(args.seed) + board - 1)
        dealer = ((board - 1) % 4) + 1
        vulnerability = {str(seat): False for seat in PLAYERS}
        if args.show_hands:
            print_hands(hands)
        bids = play_bidding(
            bidding_model,
            hands,
            dealer=dealer,
            vulnerability=vulnerability,
            strategy_answers=strategy_answers,
            top_k=args.top_k,
        )
        contract = derive_final_contract(bids, dealer=dealer)
        if contract.get("declarer") is None:
            print("Board passed out.")
            continue
        play_cards(card_model, hands, contract=contract, bids=bids, vulnerability=vulnerability, top_k=args.top_k)


def run_bid(args: argparse.Namespace) -> None:
    model = BiddingModel()
    strategy_answers = strategy_answers_for_profile(args.strategy_profile)
    result = model.predict(
        seat_to_act=args.seat,
        hand_cards=parse_cards(args.hand),
        bid_prefix=parse_bids(args.bid_prefix),
        dealer=args.dealer,
        vulnerability={str(seat): False for seat in PLAYERS},
        strategy_answers=strategy_answers,
        top_k=args.top_k,
    )
    print(json.dumps(result, indent=2))


def run_card(args: argparse.Namespace) -> None:
    model = BestCardPlayModel(PACKAGE_ROOT / "BEST_CARD_PLAY" / "model")
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
    result = model.predict(
        seat_to_act=args.seat,
        hand_cards=parse_cards(args.hand),
        trick_cards=parse_cards(args.trick),
        auction_bids=parse_bids(args.auction),
        derived_contract=contract,
        visible_dummy_hand=parse_cards(args.visible_dummy),
        vulnerability={str(seat): False for seat in PLAYERS},
        top_k=args.top_k,
    )
    print(json.dumps(result, indent=2))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Play with the packaged GEKO bidding and card-play models.")
    parser.add_argument("--mode", choices=("ai-only", "bid", "card"), default="ai-only")
    parser.add_argument("--list-profiles", action="store_true")
    parser.add_argument("--strategy-profile", type=int, default=1)
    parser.add_argument("--boards", type=int, default=1)
    parser.add_argument("--seed", type=int, default=31)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--show-hands", action="store_true")

    parser.add_argument("--seat", type=int, default=1)
    parser.add_argument("--dealer", type=int, default=1)
    parser.add_argument("--hand", default="")
    parser.add_argument("--bid-prefix", default="")

    parser.add_argument("--trick", default="")
    parser.add_argument("--auction", default="")
    parser.add_argument("--visible-dummy", default="")
    parser.add_argument("--contract-level", type=int, default=0)
    parser.add_argument("--contract-strain", default="", choices=("", "C", "D", "H", "S", "NT"))
    parser.add_argument("--declarer", type=int, default=0)
    parser.add_argument("--dummy", type=int, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.list_profiles:
        list_profiles()
        return 0
    if args.mode == "bid":
        run_bid(args)
    elif args.mode == "card":
        run_card(args)
    else:
        run_ai_only(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

