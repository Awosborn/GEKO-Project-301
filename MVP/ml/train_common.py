"""Shared training helpers for supervised next-action models."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from .tokenizer import Tokenizer


@dataclass(frozen=True)
class EncodedDataset:
    features: List[List[int]]
    labels: List[int]
    label_to_id: Dict[str, int]
    id_to_label: Dict[int, str]


def read_jsonl_rows(path: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def save_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def save_tokenizer_artifact(path: Path, tokenizer: Tokenizer) -> None:
    save_json(path, {"token_to_id": tokenizer.token_to_id, "id_to_token": tokenizer.id_to_token})


def build_label_maps(labels: Sequence[str]) -> Tuple[Dict[str, int], Dict[int, str]]:
    ordered = sorted(set(labels))
    label_to_id = {label: idx for idx, label in enumerate(ordered)}
    id_to_label = {idx: label for label, idx in label_to_id.items()}
    return label_to_id, id_to_label


def encode_dataset(
    token_sequences: Sequence[Sequence[str]],
    labels: Sequence[str],
    tokenizer: Tokenizer,
) -> EncodedDataset:
    label_to_id, id_to_label = build_label_maps(labels)
    features = [tokenizer.encode(tokens) for tokens in token_sequences]
    encoded_labels = [label_to_id[label] for label in labels]
    return EncodedDataset(features=features, labels=encoded_labels, label_to_id=label_to_id, id_to_label=id_to_label)


class MajorityClassifier:
    """Baseline classifier that predicts the most frequent label."""

    def __init__(self) -> None:
        self.majority_label_id: int | None = None
        self.class_counts: Dict[int, int] = {}

    def fit(self, y: Iterable[int]) -> None:
        counts = Counter(int(v) for v in y)
        if not counts:
            raise ValueError("Cannot fit MajorityClassifier with no labels.")
        self.class_counts = dict(counts)
        self.majority_label_id = max(counts, key=counts.get)

    def predict(self, x: Sequence[Sequence[int]]) -> List[int]:
        if self.majority_label_id is None:
            raise RuntimeError("MajorityClassifier must be fitted before prediction.")
        return [self.majority_label_id for _ in x]

    def accuracy(self, x: Sequence[Sequence[int]], y_true: Sequence[int]) -> float:
        preds = self.predict(x)
        if not y_true:
            return 0.0
        correct = sum(int(p == y) for p, y in zip(preds, y_true))
        return float(correct) / float(len(y_true))
