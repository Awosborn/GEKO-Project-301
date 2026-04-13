"""Entrypoint for supervised next-card model training."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Sequence

from .tokenizer import Tokenizer
from .train_common import (
    MajorityClassifier,
    encode_dataset,
    read_jsonl_rows,
    save_json,
    save_tokenizer_artifact,
)
from .train_next_bid import _run_transformer


def _tokens_from_card_row(row: Dict[str, object]) -> List[str]:
    seat = int(row.get("seat_to_act", 0))
    hand = [str(x) for x in row.get("hand_cards", [])]
    auction = [str(x) for x in row.get("auction_bids", [])]
    play_prefix = row.get("play_prefix", [])
    play_tokens: List[str] = []
    for event in play_prefix if isinstance(play_prefix, list) else []:
        if isinstance(event, dict):
            play_tokens.append(f"P{int(event.get('player', 0))}_{str(event.get('card', ''))}")
    return ["PHASE_PLAY", f"TO_ACT_P{seat}", "BIDS", *auction, "HAND", *hand, *play_tokens]


def _labels_from_rows(rows: Sequence[Dict[str, object]]) -> List[str]:
    return [str(row["label_next_card"]) for row in rows]


def _run_baseline(out_dir: Path, x: List[List[int]], y: List[int], id_to_label: Dict[int, str]) -> Dict[str, object]:
    model = MajorityClassifier()
    model.fit(y)
    acc = model.accuracy(x, y)
    payload = {
        "model_type": "majority_classifier",
        "majority_label_id": model.majority_label_id,
        "majority_label": id_to_label[int(model.majority_label_id or 0)],
        "class_counts": model.class_counts,
        "train_accuracy": acc,
    }
    save_json(out_dir / "baseline.json", payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train next-card models (baseline + transformer).")
    parser.add_argument("dataset_jsonl", type=Path, help="Path to cardplay_examples.jsonl from dataset export.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to write artifacts.")
    parser.add_argument("--training-tokens", type=Path, default=Path("MVP/training_tokens.json"))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=5e-4)
    return parser


def main() -> int:
    args = _parser().parse_args()
    rows = read_jsonl_rows(args.dataset_jsonl)
    if not rows:
        raise ValueError("Dataset is empty; cannot train.")
    tokenizer = Tokenizer.from_training_tokens(args.training_tokens)
    token_sequences = [_tokens_from_card_row(row) for row in rows]
    labels = _labels_from_rows(rows)
    encoded = encode_dataset(token_sequences, labels, tokenizer)

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    save_tokenizer_artifact(out_dir / "tokenizer_artifact.json", tokenizer)
    save_json(out_dir / "label_map.json", {"label_to_id": encoded.label_to_id, "id_to_label": encoded.id_to_label})
    _run_baseline(out_dir, encoded.features, encoded.labels, encoded.id_to_label)
    _run_transformer(
        out_dir=out_dir,
        x=encoded.features,
        y=encoded.labels,
        vocab_size=max(tokenizer.token_to_id.values()) + 1,
        num_classes=len(encoded.label_to_id),
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
