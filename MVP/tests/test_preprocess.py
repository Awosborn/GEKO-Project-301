from MVP.ml.normalize import normalize_bid, normalize_bid_history
from MVP.ml.preprocess import compute_deal_id, reconstruct_full_hands


def test_compute_deal_id():
    snapshot = {"game_id": "g42", "board_number": 7}
    assert compute_deal_id(snapshot) == "g42:7"


def test_normalize_bid_variants():
    assert normalize_bid("pass") == "P"
    assert normalize_bid("p") == "P"
    assert normalize_bid("d") == "X"
    assert normalize_bid("r") == "XX"
    assert normalize_bid("1n") == "1NT"
    assert normalize_bid("2h") == "2H"


def test_normalize_bid_history():
    assert normalize_bid_history(["pass", "1n", "r", "2h"]) == ["P", "1NT", "XX", "2H"]


def test_reconstruct_full_hands_success():
    snapshot = {
        "curr_card_hold": [
            ["AS", "KS", "QS", "JS", "10S", "9S", "8S", "7S", "6S", "5S", "4S", "3S"],
            ["AH", "KH", "QH", "JH", "10H", "9H", "8H", "7H", "6H", "5H", "4H", "3H"],
            ["AD", "KD", "QD", "JD", "10D", "9D", "8D", "7D", "6D", "5D", "4D", "3D"],
            ["AC", "KC", "QC", "JC", "10C", "9C", "8C", "7C", "6C", "5C", "4C", "3C"],
        ],
        "curr_card_play_hist": [
            {"player": 1, "card": "2S"},
            {"player": 2, "card": "2H"},
            {"player": 3, "card": "2D"},
            {"player": 4, "card": "2C"},
        ],
    }

    result = reconstruct_full_hands(snapshot)
    assert result.is_corrupted is False
    assert all(len(cards) == 13 for cards in result.hands.values())


def test_reconstruct_full_hands_detects_bad_count():
    snapshot = {
        "curr_card_hold": [["AS"] * 11, ["KS"] * 12, ["QS"] * 12, ["JS"] * 12],
        "curr_card_play_hist": [{"player": 1, "card": "2C"}],
    }

    result = reconstruct_full_hands(snapshot)
    assert result.is_corrupted is True
    assert "expected 13 cards" in result.reason
