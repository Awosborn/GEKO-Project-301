"""Entrypoint for supervised next-card model training."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Sequence

from .tokenizer import Tokenizer
from .evaluation import card_error_buckets, classification_metrics
from .splits import split_by_deal
from .train_common import (
    MajorityClassifier,
    encode_dataset,
    read_jsonl_rows,
    save_json,
    save_tokenizer_artifact,
)
from .inference import recommend_next_card
from .masks import card_legality_mask
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


def _baseline_probs(majority_label_id: int, n_classes: int, n_rows: int) -> List[List[float]]:
    probs: List[List[float]] = []
    for _ in range(n_rows):
        row = [0.0 for _ in range(n_classes)]
        row[int(majority_label_id)] = 1.0
        probs.append(row)
    return probs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train next-card models (baseline + transformer).")
    parser.add_argument("dataset_jsonl", type=Path, help="Path to cardplay_examples.jsonl from dataset export.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to write artifacts.")
    parser.add_argument("--training-tokens", type=Path, default=Path("MVP/training_tokens.json"))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--split-seed", type=int, default=1337)
    parser.add_argument(
        "--apply-legality-mask-training",
        action="store_true",
        help="Apply card legality masks to transformer logits during training.",
    )
    return parser


def _trick_cards_from_play_prefix(play_prefix: object) -> List[str]:
    events = play_prefix if isinstance(play_prefix, list) else []
    cards = [str(event.get("card", "")) for event in events if isinstance(event, dict)]
    trick_len = len(cards) % 4
    return cards[-trick_len:] if trick_len else []


def _write_inference_guardrail_report(out_dir: Path, rows: Sequence[Dict[str, object]], labels: Sequence[str]) -> None:
    report: List[Dict[str, object]] = []
    for row in rows:
        label_scores = {label: float(1.0 if idx == 0 else 0.0) for idx, label in enumerate(labels)}
        guarded = recommend_next_card(
            label_scores,
            hand_cards=[str(x) for x in row.get("hand_cards", [])],
            trick_cards=_trick_cards_from_play_prefix(row.get("play_prefix", [])),
            top_k=1,
        )
        report.append({
            "deal_id": str(row.get("deal_id", "")),
            "seat_to_act": int(row.get("seat_to_act", 0)),
            "guarded_top_card": guarded[0]["card"] if guarded else None,
        })
    save_json(out_dir / "inference_guardrails.json", {"phase": "card", "examples": report})


def main() -> int:
    args = _parser().parse_args()
    rows = read_jsonl_rows(args.dataset_jsonl)
    if not rows:
        raise ValueError("Dataset is empty; cannot train.")
    train_rows, val_rows, test_rows = split_by_deal(
        rows,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        seed=args.split_seed,
    )
    if not train_rows:
        raise ValueError("Training split is empty; adjust split ratios.")
    tokenizer = Tokenizer.from_training_tokens(args.training_tokens)
    token_sequences = [_tokens_from_card_row(row) for row in train_rows]
    labels = _labels_from_rows(train_rows)
    encoded = encode_dataset(token_sequences, labels, tokenizer)

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    save_tokenizer_artifact(out_dir / "tokenizer_artifact.json", tokenizer)
    save_json(out_dir / "label_map.json", {"label_to_id": encoded.label_to_id, "id_to_label": encoded.id_to_label})
    baseline = _run_baseline(out_dir, encoded.features, encoded.labels, encoded.id_to_label)
    label_vocab = [encoded.id_to_label[idx] for idx in range(len(encoded.id_to_label))]
    legality_masks = [
        card_legality_mask(
            label_vocab,
            hand_cards=[str(x) for x in row.get("hand_cards", [])],
            trick_cards=_trick_cards_from_play_prefix(row.get("play_prefix", [])),
        )
        for row in train_rows
    ]
    _run_transformer(
        out_dir=out_dir,
        x=encoded.features,
        y=encoded.labels,
        vocab_size=max(tokenizer.token_to_id.values()) + 1,
        num_classes=len(encoded.label_to_id),
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        legality_masks=legality_masks if args.apply_legality_mask_training else None,
    )
    _write_inference_guardrail_report(out_dir, rows, label_vocab)

    eval_rows = list(val_rows) + list(test_rows)
    eval_rows = [row for row in eval_rows if str(row.get("label_next_card", "")) in encoded.label_to_id]
    eval_labels = [encoded.label_to_id[str(row["label_next_card"])] for row in eval_rows]
    majority_id = int(baseline["majority_label_id"])
    baseline_probs = _baseline_probs(majority_id, len(label_vocab), len(eval_rows))
    baseline_preds = [majority_id for _ in eval_rows]
    eval_payload = {
        "split_summary": {"train": len(train_rows), "val": len(val_rows), "test": len(test_rows), "evaluated": len(eval_rows)},
        "metrics": classification_metrics(baseline_probs, eval_labels, top_k_values=(1, 3, 5)),
        "error_analysis": card_error_buckets(eval_rows, eval_labels, baseline_preds, encoded.id_to_label),
    }
    save_json(out_dir / "evaluation_report.json", eval_payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
