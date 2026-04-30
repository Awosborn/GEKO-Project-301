import json
import subprocess
import sys

from MVP.ml.dataset_export import write_jsonl


def _valid_hands_with_one_played_card_per_player():
    return [
        ["AS", "KS", "QS", "JS", "10S", "9S", "8S", "7S", "6S", "5S", "4S", "3S"],
        ["AH", "KH", "QH", "JH", "10H", "9H", "8H", "7H", "6H", "5H", "4H", "3H"],
        ["AD", "KD", "QD", "JD", "10D", "9D", "8D", "7D", "6D", "5D", "4D", "3D"],
        ["AC", "KC", "QC", "JC", "10C", "9C", "8C", "7C", "6C", "5C", "4C", "3C"],
    ]


def _play_hist_one_card_each():
    return [
        {"player": 1, "card": "2S", "trick_number": 1, "position_in_trick": 1, "leader": 1},
        {"player": 2, "card": "2H", "trick_number": 1, "position_in_trick": 2, "leader": 1},
        {"player": 3, "card": "2D", "trick_number": 1, "position_in_trick": 3, "leader": 1},
        {"player": 4, "card": "2C", "trick_number": 1, "position_in_trick": 4, "leader": 1},
    ]


def test_build_dataset_cli_runs_end_to_end(tmp_path):
    snapshot = {
        "game_id": "g11",
        "board_number": "c25",
        "curr_card_hold": _valid_hands_with_one_played_card_per_player(),
        "curr_bid_hist": [["1C", "p", "1h", "p"]],
        "curr_card_play_hist": _play_hist_one_card_each(),
    }
    input_path = tmp_path / "snapshots.jsonl"
    output_dir = tmp_path / "out"
    write_jsonl(input_path, [snapshot])

    cmd = [
        sys.executable,
        "-m",
        "MVP.ml.build_dataset_cli",
        str(input_path),
        "--output-dir",
        str(output_dir),
        "--formats",
        "jsonl",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)

    assert payload["stats"]["total_snapshots"] == 1
    assert payload["stats"]["bidding_examples"] == 4
    assert output_dir.joinpath("bidding_examples.jsonl").exists()
    assert output_dir.joinpath("cardplay_examples.jsonl").exists()
