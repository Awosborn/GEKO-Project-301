"""CLI for training and playing against GEKO models."""

from __future__ import annotations

import argparse
import json

from GameLoop import run_interactive_orchestrator
from self_play_data import generate_self_play_datasets
from train_bidding import train_bidding_model
from train_cardplay import train_cardplay_model
from train_cycle import run_training_cycle


def _cmd_train_all(*, self_play_hands: int, seed: int) -> None:
    dataset_stats = generate_self_play_datasets(hands=self_play_hands, seed=seed)
    bidding = train_bidding_model(stable=True)
    cardplay = train_cardplay_model(stable=True)
    print(json.dumps({"self_play": dataset_stats, "bidding": bidding["metadata"], "cardplay": cardplay["metadata"]}, indent=2))


def _cmd_train_cycle(cycles: int, *, self_play_hands: int, seed: int) -> None:
    dataset_stats = generate_self_play_datasets(hands=self_play_hands, seed=seed)
    cycle = run_training_cycle(cycles=cycles)
    print(json.dumps({"self_play": dataset_stats, "cycle": cycle}, indent=2))


def _cmd_generate_self_play(hands: int, seed: int) -> None:
    print(json.dumps(generate_self_play_datasets(hands=hands, seed=seed), indent=2))


def _cmd_play() -> None:
    run_interactive_orchestrator()


def main() -> None:
    parser = argparse.ArgumentParser(description="GEKO model training + play CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    train_all_parser = sub.add_parser("train-all", help="Generate self-play data, then train/publish both models.")
    train_all_parser.add_argument("--self-play-hands", type=int, default=200, help="Self-play boards to generate before training (default: 200).")
    train_all_parser.add_argument("--seed", type=int, default=301, help="RNG seed for self-play generation (default: 301).")

    cycle_parser = sub.add_parser(
        "train-cycle",
        help="Iteratively co-train bidding/card-play candidates and arena-test vs previous best models.",
    )
    cycle_parser.add_argument(
        "--cycles",
        type=int,
        default=1000,
        help="Number of co-training cycles to run (default: 1000).",
    )
    cycle_parser.add_argument("--self-play-hands", type=int, default=200, help="Self-play boards to regenerate before each cycle run (default: 200).")
    cycle_parser.add_argument("--seed", type=int, default=301, help="RNG seed for self-play generation (default: 301).")

    self_play_parser = sub.add_parser("generate-self-play", help="Generate runner training/validation datasets from self-play only.")
    self_play_parser.add_argument("--hands", type=int, default=200, help="Self-play boards to generate (default: 200).")
    self_play_parser.add_argument("--seed", type=int, default=301, help="RNG seed for generation (default: 301).")

    sub.add_parser("play", help="Run interactive gameplay against currently stable models.")

    args = parser.parse_args()
    if args.command == "train-all":
        _cmd_train_all(self_play_hands=max(2, int(args.self_play_hands)), seed=int(args.seed))
    elif args.command == "train-cycle":
        _cmd_train_cycle(cycles=max(1, int(args.cycles)), self_play_hands=max(2, int(args.self_play_hands)), seed=int(args.seed))
    elif args.command == "generate-self-play":
        _cmd_generate_self_play(hands=max(2, int(args.hands)), seed=int(args.seed))
    else:
        _cmd_play()


if __name__ == "__main__":
    main()
