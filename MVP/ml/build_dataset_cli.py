"""CLI for building persisted supervised datasets from snapshot JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset_export import build_datasets_from_snapshot_jsonl


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build bidding/card-play datasets from snapshot JSONL.")
    parser.add_argument("snapshot_jsonl", type=Path, help="Path to input snapshot JSONL file.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory where dataset files are written.")
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["jsonl"],
        choices=["jsonl", "parquet"],
        help="Output format(s) to persist.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    stats, persisted = build_datasets_from_snapshot_jsonl(
        snapshot_jsonl_path=args.snapshot_jsonl,
        output_dir=args.output_dir,
        formats=args.formats,
    )
    print(json.dumps({"stats": stats.__dict__, "outputs": persisted}, default=str, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
