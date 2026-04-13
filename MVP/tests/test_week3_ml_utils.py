from MVP.ml.derive_contract import derive_contract_from_auction
from MVP.ml.splits import split_by_deal
from MVP.ml.tokenizer import Tokenizer


def test_derive_contract_from_auction_tracks_level_strain_and_multiplier():
    meaning = derive_contract_from_auction(["1c", "p", "1h", "x", "2h", "p", "p", "xx", "p", "p", "p"])
    assert meaning.level == 2
    assert meaning.strain == "H"
    assert meaning.multiplier == "XX"
    assert meaning.declarer is None
    assert meaning.dummy is None


def test_split_by_deal_prevents_leakage_between_splits():
    examples = [
        {"deal_id": "d1", "x": 1},
        {"deal_id": "d1", "x": 2},
        {"deal_id": "d2", "x": 3},
        {"deal_id": "d3", "x": 4},
        {"deal_id": "d4", "x": 5},
    ]

    train, val, test = split_by_deal(examples, train_ratio=0.5, val_ratio=0.25, seed=7)

    train_deals = {row["deal_id"] for row in train}
    val_deals = {row["deal_id"] for row in val}
    test_deals = {row["deal_id"] for row in test}

    assert train_deals.isdisjoint(val_deals)
    assert train_deals.isdisjoint(test_deals)
    assert val_deals.isdisjoint(test_deals)
    assert len(train) + len(val) + len(test) == len(examples)


def test_tokenizer_loads_training_tokens_and_adds_specials():
    tokenizer = Tokenizer.from_training_tokens("MVP/training_tokens.json")
    encoded = tokenizer.encode(["P", "AS", "PHASE_BID", "NOT_A_TOKEN"])
    decoded = tokenizer.decode(encoded)

    assert "P" in tokenizer.token_to_id
    assert "AS" in tokenizer.token_to_id
    assert "PHASE_BID" in tokenizer.token_to_id
    assert encoded[-1] == tokenizer.token_to_id["UNK"]
    assert decoded[0] == "P"
