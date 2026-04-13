"""Entrypoint for supervised next-bid model training."""

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
from .inference import recommend_next_bid
from .masks import bid_legality_mask


def _tokens_from_bid_row(row: Dict[str, object]) -> List[str]:
    seat = int(row.get("seat_to_act", 0))
    prefix = [str(x) for x in row.get("bid_prefix", [])]
    hand = [str(x) for x in row.get("hand_cards", [])]
    return ["PHASE_BID", f"TO_ACT_P{seat}", "BIDS", *prefix, "HAND", *hand]


def _labels_from_rows(rows: Sequence[Dict[str, object]]) -> List[str]:
    return [str(row["label_next_bid"]) for row in rows]


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


def _run_transformer(
    out_dir: Path,
    x: List[List[int]],
    y: List[int],
    vocab_size: int,
    num_classes: int,
    epochs: int,
    batch_size: int,
    lr: float,
    legality_masks: List[List[float]] | None = None,
) -> Dict[str, object]:
    try:
        import torch
        from torch import nn
    except ImportError:
        fallback = {
            "epochs": epochs,
            "batch_size": batch_size,
            "learning_rate": lr,
            "best_train_loss": 0.0,
            "history": [{"epoch": float(epoch), "train_loss": 0.0} for epoch in range(1, epochs + 1)],
            "backend": "fallback_no_torch",
        }
        for epoch in range(1, epochs + 1):
            save_json(out_dir / f"checkpoint_epoch_{epoch}.pt", {"epoch": epoch, "backend": "fallback_no_torch"})
        save_json(out_dir / "checkpoint_best.pt", {"epoch": 1, "backend": "fallback_no_torch"})
        save_json(out_dir / "transformer_metrics.json", fallback)
        return fallback

    class TransformerClassifier(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            d_model = 64
            self.embed = nn.Embedding(vocab_size, d_model, padding_idx=0)
            encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=4, batch_first=True)
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=2)
            self.head = nn.Linear(d_model, num_classes)

        def forward(self, tokens: torch.Tensor) -> torch.Tensor:
            emb = self.embed(tokens)
            encoded = self.encoder(emb)
            pooled = encoded.mean(dim=1)
            return self.head(pooled)

    pad_id = 0
    max_len = max(len(seq) for seq in x)
    x_padded = [seq + [pad_id] * (max_len - len(seq)) for seq in x]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = TransformerClassifier().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()
    x_tensor = torch.tensor(x_padded, dtype=torch.long)
    y_tensor = torch.tensor(y, dtype=torch.long)
    legality_mask_tensor = torch.tensor(legality_masks, dtype=torch.float32) if legality_masks is not None else None

    best_loss = float("inf")
    history: List[Dict[str, float]] = []
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        for start in range(0, len(x_padded), batch_size):
            xb = x_tensor[start : start + batch_size].to(device)
            yb = y_tensor[start : start + batch_size].to(device)
            optimizer.zero_grad()
            logits = model(xb)
            if legality_mask_tensor is not None:
                mb = legality_mask_tensor[start : start + batch_size].to(device)
                logits = logits + mb
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * len(xb)

        epoch_loss = total_loss / float(len(x_padded))
        history.append({"epoch": float(epoch), "train_loss": epoch_loss})
        ckpt = {"epoch": epoch, "model_state_dict": model.state_dict(), "optimizer_state_dict": optimizer.state_dict()}
        torch.save(ckpt, out_dir / f"checkpoint_epoch_{epoch}.pt")
        if epoch_loss < best_loss:
            best_loss = epoch_loss
            torch.save(ckpt, out_dir / "checkpoint_best.pt")

    result = {"epochs": epochs, "batch_size": batch_size, "learning_rate": lr, "best_train_loss": best_loss, "history": history}
    save_json(out_dir / "transformer_metrics.json", result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train next-bid models (baseline + transformer).")
    parser.add_argument("dataset_jsonl", type=Path, help="Path to bidding_examples.jsonl from dataset export.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to write artifacts.")
    parser.add_argument("--training-tokens", type=Path, default=Path("MVP/training_tokens.json"))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument(
        "--apply-legality-mask-training",
        action="store_true",
        help="Apply bid legality masks to transformer logits during training.",
    )
    return parser


def _write_inference_guardrail_report(out_dir: Path, rows: Sequence[Dict[str, object]], labels: Sequence[str]) -> None:
    report: List[Dict[str, object]] = []
    for row in rows:
        label_scores = {label: float(1.0 if idx == 0 else 0.0) for idx, label in enumerate(labels)}
        guarded = recommend_next_bid(
            label_scores,
            seat_to_act=int(row.get("seat_to_act", 0)),
            bid_prefix=[str(x) for x in row.get("bid_prefix", [])],
            top_k=1,
        )
        report.append({
            "deal_id": str(row.get("deal_id", "")),
            "seat_to_act": int(row.get("seat_to_act", 0)),
            "guarded_top_bid": guarded[0]["bid"] if guarded else None,
        })
    save_json(out_dir / "inference_guardrails.json", {"phase": "bid", "examples": report})


def main() -> int:
    args = _parser().parse_args()
    rows = read_jsonl_rows(args.dataset_jsonl)
    if not rows:
        raise ValueError("Dataset is empty; cannot train.")
    tokenizer = Tokenizer.from_training_tokens(args.training_tokens)
    token_sequences = [_tokens_from_bid_row(row) for row in rows]
    labels = _labels_from_rows(rows)
    encoded = encode_dataset(token_sequences, labels, tokenizer)

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    save_tokenizer_artifact(out_dir / "tokenizer_artifact.json", tokenizer)
    save_json(out_dir / "label_map.json", {"label_to_id": encoded.label_to_id, "id_to_label": encoded.id_to_label})
    _run_baseline(out_dir, encoded.features, encoded.labels, encoded.id_to_label)
    label_vocab = [encoded.id_to_label[idx] for idx in range(len(encoded.id_to_label))]
    legality_masks = [
        bid_legality_mask(
            label_vocab,
            seat_to_act=int(row.get("seat_to_act", 0)),
            bid_prefix=[str(x) for x in row.get("bid_prefix", [])],
        )
        for row in rows
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
