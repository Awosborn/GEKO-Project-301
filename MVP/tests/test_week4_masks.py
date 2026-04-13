from MVP.ml.masks import bid_legality_mask, card_legality_mask, is_legal_bid, legal_bids, legal_cards


def test_is_legal_bid_contract_order_and_double_redouble_rules():
    prefix = ["1H", "P", "P"]
    assert is_legal_bid("X", seat_to_act=4, bid_prefix=prefix)
    assert not is_legal_bid("X", seat_to_act=1, bid_prefix=prefix)
    assert not is_legal_bid("1D", seat_to_act=4, bid_prefix=prefix)
    assert is_legal_bid("1S", seat_to_act=4, bid_prefix=prefix)

    doubled_prefix = ["1H", "P", "P", "X"]
    assert is_legal_bid("XX", seat_to_act=1, bid_prefix=doubled_prefix)
    assert not is_legal_bid("XX", seat_to_act=2, bid_prefix=doubled_prefix)


def test_legal_bids_includes_pass_and_filters_illegal_actions():
    opening_legal = legal_bids(seat_to_act=1, bid_prefix=[])
    assert "P" in opening_legal
    assert "X" not in opening_legal
    assert "1C" in opening_legal


def test_bid_legality_mask_marks_allowed_tokens_only():
    vocab = ["P", "X", "XX", "1C", "1D", "1H"]
    mask = bid_legality_mask(vocab, seat_to_act=2, bid_prefix=["1H", "P", "P"])

    as_map = dict(zip(vocab, mask))
    assert as_map["P"] == 0.0
    assert as_map["X"] == 0.0
    assert as_map["XX"] != 0.0
    assert as_map["1H"] != 0.0


def test_legal_cards_requires_follow_suit_when_possible():
    hand = ["AH", "2H", "KC", "QS"]
    trick = ["9H"]
    assert legal_cards(hand_cards=hand, trick_cards=trick) == ["AH", "2H"]

    trick_spade = ["5S"]
    assert legal_cards(hand_cards=hand, trick_cards=trick_spade) == ["QS"]

    no_spade_hand = ["AH", "2H", "KC"]
    assert set(legal_cards(hand_cards=no_spade_hand, trick_cards=trick_spade)) == {"AH", "2H", "KC"}


def test_card_legality_mask_respects_follow_suit():
    vocab = ["AH", "2H", "KC", "QS", "9D"]
    mask = card_legality_mask(vocab, hand_cards=["AH", "2H", "KC", "QS"], trick_cards=["9H"])
    as_map = dict(zip(vocab, mask))

    assert as_map["AH"] == 0.0
    assert as_map["2H"] == 0.0
    assert as_map["KC"] != 0.0
    assert as_map["9D"] != 0.0
