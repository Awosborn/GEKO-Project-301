from MVP.ml.problem_definition import (
    LOCKED_PROBLEM_DEFINITION,
    COMPASS_TO_SEAT_ID,
    SEAT_ID_TO_COMPASS,
    auction_seat_to_act,
)


def test_seat_compass_mapping_is_stable():
    assert SEAT_ID_TO_COMPASS == {1: "N", 2: "E", 3: "S", 4: "W"}
    assert COMPASS_TO_SEAT_ID == {"N": 1, "E": 2, "S": 3, "W": 4}


def test_auction_turn_order_starts_from_dealer_and_rotates_clockwise():
    # Dealer East -> E, S, W, N, E
    turns = [auction_seat_to_act(2, idx) for idx in range(5)]
    assert turns == [2, 3, 4, 1, 2]


def test_locked_problem_definition_values():
    assert LOCKED_PROBLEM_DEFINITION.seat_order == ["N", "E", "S", "W"]
    assert LOCKED_PROBLEM_DEFINITION.inference_visibility == "acting_hand_plus_public"
    assert LOCKED_PROBLEM_DEFINITION.training_visibility == "acting_hand_plus_public"
    assert LOCKED_PROBLEM_DEFINITION.label_source == "solver"
    assert LOCKED_PROBLEM_DEFINITION.derive_declarer_dummy_now is True
