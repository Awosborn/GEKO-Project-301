import json
import subprocess
import sys

from MVP.ml.dataset_export import write_jsonl


def _write_bidding_dataset(path):
    rows = [
        {
            "deal_id": "d1",
            "board_number": "1",
            "seat_to_act": 1,
            "hand_cards": ["AS", "KS", "QS"],
            "bid_prefix": ["1C", "P"],
            "label_next_bid": "1H",
        },
        {
            "deal_id": "d2",
            "board_number": "2",
            "seat_to_act": 2,
            "hand_cards": ["AH", "KH", "QH"],
            "bid_prefix": ["1D", "P"],
            "label_next_bid": "1H",
        },
    ]
    write_jsonl(path, rows)


def _write_card_dataset(path):
    rows = [
        {
            "deal_id": "d1",
            "board_number": "1",
            "seat_to_act": 1,
            "hand_cards": ["AS", "KS", "QS"],
            "auction_bids": ["1C", "P", "1H"],
            "play_prefix": [{"player": 1, "card": "2S"}],
            "label_next_card": "AS",
            "derived_contract": {"level": 1, "strain": "H", "multiplier": "", "declarer": None, "dummy": None},
        },
        {
            "deal_id": "d2",
            "board_number": "2",
            "seat_to_act": 2,
            "hand_cards": ["AH", "KH", "QH"],
            "auction_bids": ["1D", "P", "1H"],
            "play_prefix": [{"player": 2, "card": "2H"}],
            "label_next_card": "AH",
            "derived_contract": {"level": 1, "strain": "H", "multiplier": "", "declarer": None, "dummy": None},
        },
    ]
    write_jsonl(path, rows)


def test_train_next_bid_cli_writes_artifacts(tmp_path):
    dataset = tmp_path / "bidding_examples.jsonl"
    out_dir = tmp_path / "bid_model"
    _write_bidding_dataset(dataset)
    cmd = [
        sys.executable,
        "-m",
        "MVP.ml.train_next_bid",
        str(dataset),
        "--output-dir",
        str(out_dir),
        "--epochs",
        "1",
        "--batch-size",
        "2",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    assert out_dir.joinpath("baseline.json").exists()
    assert out_dir.joinpath("tokenizer_artifact.json").exists()
    assert out_dir.joinpath("checkpoint_epoch_1.pt").exists()
    assert out_dir.joinpath("inference_guardrails.json").exists()
    baseline = json.loads(out_dir.joinpath("baseline.json").read_text(encoding="utf-8"))
    assert baseline["model_type"] == "majority_classifier"


def test_train_next_card_cli_writes_artifacts(tmp_path):
    dataset = tmp_path / "cardplay_examples.jsonl"
    out_dir = tmp_path / "card_model"
    _write_card_dataset(dataset)
    cmd = [
        sys.executable,
        "-m",
        "MVP.ml.train_next_card",
        str(dataset),
        "--output-dir",
        str(out_dir),
        "--epochs",
        "1",
        "--batch-size",
        "2",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    assert out_dir.joinpath("baseline.json").exists()
    assert out_dir.joinpath("tokenizer_artifact.json").exists()
    assert out_dir.joinpath("checkpoint_epoch_1.pt").exists()
    assert out_dir.joinpath("inference_guardrails.json").exists()
