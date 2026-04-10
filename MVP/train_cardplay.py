"""Train card-play policy artifacts from episode records."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Dict, List

from evaluation_metrics import (
    proxy_imp_score,
    proxy_mp_score,
    summarize_training_metrics,
    trick_delta_vs_double_dummy,
)
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
                    "player": int(step.get("player", 1)),
                    "trick_index": int(step.get("trick_index", 0)),
                    "card": str(step.get("card", "2C")).upper(),
                }
            )
        terminal = dict(row.get("terminal", {}))
        dd = dict(terminal.get("double_dummy_target", {}))
        labels = {
            "declarer_tricks": terminal.get("observed_declarer_tricks", 0),
            "double_dummy_tricks": dd.get("expected_tricks", 0),
            "imps_proxy": terminal.get("observed_score", 0) - dd.get("projected_score", 0),
            "mps_proxy": terminal.get("observed_score", 0),
        }
        episodes.append({"play_sequence": sequence, "labels": labels})
    return episodes


def train_cardplay_model(*, stable: bool = True, notes: str | None = None) -> Dict[str, object]:
    runner_train = _episodes_from_runner_records(DATASETS_DIR / "runner_cardplay_train.jsonl")
    runner_val = _episodes_from_runner_records(DATASETS_DIR / "runner_cardplay_val.jsonl")
    train_rows = runner_train or _read_jsonl(DATASETS_DIR / "train.jsonl")
    val_rows = runner_val or _read_jsonl(DATASETS_DIR / "val.jsonl")

    top_card_by_context: Dict[str, str] = {}
    counts: Dict[str, Counter] = defaultdict(Counter)
    for episode in train_rows:
        for step in episode.get("play_sequence", []):
            context = f"player={int(step.get('player', 1))}|trick={int(step.get('trick_index', 0))}"
            card = str(step.get("card", "2C")).upper()
            counts[context][card] += 1

    for ctx, counter in counts.items():
        if counter:
            top_card_by_context[ctx] = counter.most_common(1)[0][0]

    observed_tricks: List[float] = []
    dd_tricks: List[float] = []
    score_deltas: List[float] = []
    board_scores: List[float] = []
    for episode in val_rows:
        labels = dict(episode.get("labels", {}))
        obs = float(labels.get("declarer_tricks", 0.0))
        dd = float(labels.get("double_dummy_tricks", 0.0))
        imp_like = float(labels.get("imps_proxy", obs - dd))
        mp_like = float(labels.get("mps_proxy", imp_like))
        observed_tricks.append(obs)
        dd_tricks.append(dd)
        score_deltas.append(imp_like)
        board_scores.append(mp_like)

    metrics = summarize_training_metrics(
        bid_acc=0.0,
        trick_delta=trick_delta_vs_double_dummy(observed_tricks, dd_tricks),
        imp_proxy=proxy_imp_score(score_deltas),
        mp_proxy=proxy_mp_score(board_scores),
    )

    artifact_payload = {
        "policy_type": "frequency_cardplay",
        "top_card_by_context": top_card_by_context,
        "train_examples": len(train_rows),
        "validation_examples": len(val_rows),
        "metrics": metrics,
    }

    version = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    metadata = register_model_artifact(
        model_type="policy",
        task="cardplay",
        version=version,
        metrics=metrics,
        artifact_payload=artifact_payload,
        stable=stable,
        notes=notes or "Frequency baseline trained from card-play episode records.",
    )

    return {"artifact": artifact_payload, "metadata": metadata.__dict__}


if __name__ == "__main__":
    output = train_cardplay_model()
    print(json.dumps(output, indent=2))
