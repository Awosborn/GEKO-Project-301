"""CLI for training and playing against GEKO models."""

from __future__ import annotations

import argparse
import json

from GameLoop import run_interactive_orchestrator
from train_bidding import train_bidding_model
from train_cardplay import train_cardplay_model
from train_cycle import run_training_cycle


def _cmd_train_all() -> None:
    bidding = train_bidding_model(stable=True)
    cardplay = train_cardplay_model(stable=True)
    print(json.dumps({"bidding": bidding["metadata"], "cardplay": cardplay["metadata"]}, indent=2))


def _cmd_train_cycle(cycles: int) -> None:
    print(json.dumps(run_training_cycle(cycles=cycles), indent=2))


def _cmd_play() -> None:
    run_interactive_orchestrator()


def main() -> None:
    parser = argparse.ArgumentParser(description="GEKO model training + play CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("train-all", help="Train and publish both bidding + card-play models.")

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

    sub.add_parser("play", help="Run interactive gameplay against currently stable models.")

    args = parser.parse_args()
    if args.command == "train-all":
        _cmd_train_all()
    elif args.command == "train-cycle":
        _cmd_train_cycle(cycles=max(1, int(args.cycles)))
    else:
        _cmd_play()


if __name__ == "__main__":
    main()
