import json

from MVP.ml.inference_service import InferenceArtifacts, predict_bid, predict_card


def _write_artifacts(path):
    path.mkdir(parents=True, exist_ok=True)
    tokenizer = {
        "token_to_id": {
            "PAD": 0,
            "UNK": 1,
            "PHASE_BID": 2,
            "PHASE_PLAY": 3,
            "TO_ACT_P1": 4,
            "BIDS": 5,
            "HAND": 6,
            "1C": 7,
            "P": 8,
            "AS": 9,
        },
        "id_to_token": {
            "0": "PAD",
            "1": "UNK",
            "2": "PHASE_BID",
            "3": "PHASE_PLAY",
            "4": "TO_ACT_P1",
            "5": "BIDS",
            "6": "HAND",
            "7": "1C",
            "8": "P",
            "9": "AS",
        },
    }
    label_map = {"label_to_id": {"X": 0, "1C": 1, "P": 2}, "id_to_label": {"0": "X", "1": "1C", "2": "P"}}
    baseline = {"majority_label_id": 0}
    path.joinpath("tokenizer_artifact.json").write_text(json.dumps(tokenizer), encoding="utf-8")
    path.joinpath("label_map.json").write_text(json.dumps(label_map), encoding="utf-8")
    path.joinpath("baseline.json").write_text(json.dumps(baseline), encoding="utf-8")


def test_predict_bid_returns_masked_topk(tmp_path):
    model_dir = tmp_path / "bid"
    _write_artifacts(model_dir)
    artifacts = InferenceArtifacts.from_model_dir(model_dir)

    out = predict_bid(artifacts, seat_to_act=1, bid_prefix=[], hand_cards=["AS"], top_k=2)
    assert out["top_k_probabilities"][0]["label"] == "X"
    assert out["masked_top_k_probabilities"][0]["label"] == "1C"
    assert all(item["label"] != "X" for item in out["masked_top_k_probabilities"])


def test_predict_card_returns_follow_suit_masked_output(tmp_path):
    model_dir = tmp_path / "card"
    _write_artifacts(model_dir)
    model_dir.joinpath("label_map.json").write_text(
        json.dumps(
            {
                "label_to_id": {"KC": 0, "AH": 1, "2H": 2},
                "id_to_label": {"0": "KC", "1": "AH", "2": "2H"},
            }
        ),
        encoding="utf-8",
    )
    artifacts = InferenceArtifacts.from_model_dir(model_dir)
    out = predict_card(
        artifacts,
        seat_to_act=1,
        auction_bids=["1C", "P"],
        play_prefix=[{"player": 2, "card": "9H"}],
        hand_cards=["KC", "AH", "2H"],
        trick_cards=["9H"],
        top_k=2,
    )
    assert out["top_k_probabilities"][0]["label"] == "KC"
    assert [row["label"] for row in out["masked_top_k_probabilities"]] == ["AH", "2H"]
