"""Train bidding policy artifacts from episode records."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Dict, List

from evaluation_metrics import bid_accuracy, summarize_training_metrics
from model_registry import register_model_artifact


ROOT = Path(__file__).resolve().parent
DATASETS_DIR = ROOT / "datasets"
def _read_jsonl(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    rows: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows




def _episodes_from_runner_records(path: Path) -> List[Dict[str, object]]:
    rows = _read_jsonl(path)
    episodes: List[Dict[str, object]] = []
    for row in rows:
        sequence = []
        for step in row.get("encoded_sequence", []):
            sequence.append(
                {
                    "player": int(step.get("bidder", step.get("player", 1))),
                    "bid": str(step.get("bid", "P")).upper(),
                }
            )
        episodes.append({"auction_sequence": sequence, "labels": row.get("terminal", {})})
    return episodes


def train_bidding_model() -> Dict[str, object]:
    runner_train = _episodes_from_runner_records(DATASETS_DIR / "runner_bidding_train.jsonl")
    runner_val = _episodes_from_runner_records(DATASETS_DIR / "runner_bidding_val.jsonl")
    train_rows = runner_train or _read_jsonl(DATASETS_DIR / "train.jsonl")
    val_rows = runner_val or _read_jsonl(DATASETS_DIR / "val.jsonl")

    counts_by_context: Dict[str, Counter] = defaultdict(Counter)
    for episode in train_rows:
        for step in episode.get("auction_sequence", []):
            context = f"player={int(step.get('player', 1))}"
            bid = str(step.get("bid", "P")).upper()
            counts_by_context[context][bid] += 1

    top_bid_by_context = {
        ctx: counter.most_common(1)[0][0]
        for ctx, counter in counts_by_context.items()
        if counter
    }

    predicted: List[str] = []
    expected: List[str] = []
    for episode in val_rows:
        for step in episode.get("auction_sequence", []):
            context = f"player={int(step.get('player', 1))}"
            expected_bid = str(step.get("bid", "P")).upper()
            predicted_bid = top_bid_by_context.get(context, "P")
            predicted.append(predicted_bid)
            expected.append(expected_bid)

    metrics = summarize_training_metrics(
        bid_acc=bid_accuracy(predicted, expected),
        trick_delta=0.0,
        imp_proxy=0.0,
        mp_proxy=0.0,
    )

    artifact_payload = {
        "policy_type": "frequency_bidding",
        "top_bid_by_context": top_bid_by_context,
        "train_examples": len(train_rows),
        "validation_examples": len(val_rows),
        "metrics": metrics,
    }

    version = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    metadata = register_model_artifact(
        model_type="policy",
        task="bidding",
        version=version,
        metrics=metrics,
        artifact_payload=artifact_payload,
        stable=True,
        notes="Frequency baseline trained from auction episode records.",
    )

    return {"artifact": artifact_payload, "metadata": metadata.__dict__}


if __name__ == "__main__":
    output = train_bidding_model()
    print(json.dumps(output, indent=2))
