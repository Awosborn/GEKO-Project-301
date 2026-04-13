from MVP.ml.dataset_export import (
    build_bidding_examples,
    build_cardplay_examples_from_snapshot,
    flatten_bid_history,
    select_representative_bidding_snapshot,
)


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


def test_flatten_bid_history_normalizes_and_orders_seats():
    events = flatten_bid_history([["1n", "pass", None, "d"], ["r", None, "2h", None]])
    assert [event["seat_to_act"] for event in events] == [1, 2, 4, 1, 3]
    assert [event["bid"] for event in events] == ["1NT", "P", "X", "XX", "2H"]


def test_select_representative_snapshot_uses_largest_auction():
    snapshots = [
        {"curr_bid_hist": [["1C", None, None, None]]},
        {"curr_bid_hist": [["1C", "P", "1D", "P"], ["1NT", None, None, None]]},
    ]
    representative = select_representative_bidding_snapshot(snapshots)
    assert representative is snapshots[1]


def test_build_bidding_examples_groups_by_deal_and_uses_representative():
    base = {
        "game_id": "g1",
        "board_number": "o1",
        "curr_card_hold": _valid_hands_with_one_played_card_per_player(),
        "curr_card_play_hist": _play_hist_one_card_each(),
    }
    snapshots = [
        {
            **base,
            "curr_bid_hist": [["1C", None, None, None]],
        },
        {
            **base,
            "curr_bid_hist": [["1C", "pass", "1n", "p"], ["2h", None, None, None]],
        },
    ]

    examples = build_bidding_examples(snapshots)
    assert len(examples) == 5
    assert examples[0].deal_id == "g1:o1"
    assert examples[0].seat_to_act == 1
    assert examples[0].bid_prefix == []
    assert examples[0].label_next_bid == "1C"
    assert examples[1].bid_prefix == ["1C"]
    assert examples[1].label_next_bid == "P"
    assert examples[-1].bid_prefix == ["1C", "P", "1NT", "P"]
    assert examples[-1].label_next_bid == "2H"


def test_build_cardplay_example_inverts_post_action_snapshot():
    snapshot = {
        "game_id": "g9",
        "board_number": "c23",
        "curr_card_hold": _valid_hands_with_one_played_card_per_player(),
        "curr_bid_hist": [["1C", "p", "1h", "p"]],
        "curr_card_play_hist": _play_hist_one_card_each(),
    }

    examples = build_cardplay_examples_from_snapshot(snapshot)
    assert len(examples) == 1
    example = examples[0]
    assert example.deal_id == "g9:c23"
    assert example.seat_to_act == 4
    assert example.label_next_card == "2C"
    assert len(example.play_prefix) == 3
    assert example.hand_cards[-1] == "2C"
    assert example.auction_bids == ["1C", "P", "1H", "P"]
    assert example.derived_contract == {"level": 1, "strain": "H", "multiplier": "", "declarer": None, "dummy": None}
