"""Interactive play mode: AI controls players 1-3, human controls player 4.

This command is intended to be used after training artifacts are generated.
It deals random hands each board and runs a bidding phase where AI seats
choose legality-constrained model predictions and the human chooses actions
for seat 4.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Dict, List, Sequence

from .inference_service import InferenceArtifacts, predict_bid
from .masks import legal_bids

SUITS = ["C", "D", "H", "S"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def build_deck() -> List[str]:
    return [f"{rank}{suit}" for suit in SUITS for rank in RANKS]


def random_deal(rng: random.Random) -> Dict[int, List[str]]:
    deck = build_deck()
    rng.shuffle(deck)
    hands: Dict[int, List[str]] = {seat: [] for seat in range(1, 5)}
    for idx, card in enumerate(deck):
        seat = (idx % 4) + 1
        hands[seat].append(card)
    for seat in hands:
        hands[seat].sort(key=lambda c: (SUITS.index(c[-1]), RANKS.index(c[:-1])))
    return hands


def auction_is_complete(bid_prefix: Sequence[str]) -> bool:
    if len(bid_prefix) < 4:
        return False

    if all(bid == "P" for bid in bid_prefix[:4]):
        return True

    for idx, bid in enumerate(bid_prefix):
        if bid == "P":
            continue
        if bid[0] in "1234567":
            trailing = bid_prefix[idx + 1 :]
            if len(trailing) >= 3 and trailing[-3:] == ["P", "P", "P"]:
                return True
    return False


def choose_ai_bid(
    artifacts: InferenceArtifacts,
    *,
    seat_to_act: int,
    bid_prefix: Sequence[str],
    hand_cards: Sequence[str],
    top_k: int,
) -> str:
    prediction = predict_bid(
        artifacts,
        seat_to_act=seat_to_act,
        bid_prefix=bid_prefix,
        hand_cards=hand_cards,
        top_k=top_k,
    )
    masked = prediction["masked_top_k_probabilities"]
    if masked:
        return str(masked[0]["label"])

    legal = legal_bids(seat_to_act=seat_to_act, bid_prefix=bid_prefix)
    return legal[0] if legal else "P"


def prompt_human_bid(*, seat_to_act: int, bid_prefix: Sequence[str]) -> str:
    legal = legal_bids(seat_to_act=seat_to_act, bid_prefix=bid_prefix)
    legal_set = set(legal)
    print(f"\nYour turn (Player {seat_to_act}).")
    print("Legal bids:", " ".join(legal))

    while True:
        bid = input("Enter your bid: ").strip().upper()
        if bid in legal_set:
            return bid
        print("Illegal bid for this auction state. Try again.")


def run_board(
    artifacts: InferenceArtifacts,
    *,
    board_no: int,
    rng: random.Random,
    top_k: int,
) -> None:
    hands = random_deal(rng)
    print(f"\n=== Board {board_no} (random deal) ===")
    print("You are Player 4.")
    print("Your hand:", " ".join(hands[4]))

    bid_prefix: List[str] = []
    turn_index = 0
    while not auction_is_complete(bid_prefix):
        seat_to_act = (turn_index % 4) + 1
        if seat_to_act == 4:
            bid = prompt_human_bid(seat_to_act=seat_to_act, bid_prefix=bid_prefix)
        else:
            bid = choose_ai_bid(
                artifacts,
                seat_to_act=seat_to_act,
                bid_prefix=bid_prefix,
                hand_cards=hands[seat_to_act],
                top_k=top_k,
            )
            print(f"Player {seat_to_act} (AI) bids: {bid}")

        bid_prefix.append(bid)
        turn_index += 1

    print("\nAuction complete:", " ".join(bid_prefix))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Play against trained bidding AI (players 1-3), with you as player 4.",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        required=True,
        help="Path to trained bidding model directory (contains tokenizer_artifact.json and label_map.json).",
    )
    parser.add_argument("--boards", type=int, default=1, help="Number of random boards to play.")
    parser.add_argument("--seed", type=int, default=7, help="RNG seed for reproducible random deals.")
    parser.add_argument("--top-k", type=int, default=3, help="Top-k predictions to consider for AI bids.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    artifacts = InferenceArtifacts.from_model_dir(args.model_dir)

    print("Loaded bidding artifacts from", args.model_dir)
    print("AI seats: 1, 2, 3 | Human seat: 4")

    for board_no in range(1, args.boards + 1):
        run_board(artifacts, board_no=board_no, rng=rng, top_k=args.top_k)

    print("\nSession finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
