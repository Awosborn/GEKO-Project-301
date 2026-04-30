from MVP.ml.inference import recommend_next_bid, recommend_next_card


def test_recommend_next_bid_filters_illegal_actions():
    scores = {"X": 10.0, "1C": 3.0, "P": 1.0}
    recs = recommend_next_bid(scores, seat_to_act=1, bid_prefix=[], top_k=2)
    assert recs[0]["bid"] == "1C"
    assert all(rec["bid"] != "X" for rec in recs)


def test_recommend_next_card_filters_by_follow_suit():
    scores = {"KC": 10.0, "AH": 6.0, "2H": 5.0}
    recs = recommend_next_card(scores, hand_cards=["KC", "AH", "2H"], trick_cards=["9H"], top_k=2)
    assert [rec["card"] for rec in recs] == ["AH", "2H"]

