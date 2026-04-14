from MVP.ml.play_vs_ai import auction_is_complete, random_deal


def test_random_deal_gives_13_cards_per_player():
    import random

    hands = random_deal(random.Random(11))
    assert all(len(hand) == 13 for hand in hands.values())
    all_cards = [card for hand in hands.values() for card in hand]
    assert len(set(all_cards)) == 52


def test_auction_completion_detects_passout():
    assert auction_is_complete(["P", "P", "P", "P"])


def test_auction_completion_detects_three_passes_after_contract():
    assert auction_is_complete(["1C", "P", "P", "P"])
    assert not auction_is_complete(["1C", "P", "P"])
