from MVP.ml.evaluation import bid_confusion_report, card_error_buckets, classification_metrics
from MVP.ml.splits import split_by_deal


def test_classification_metrics_include_topk_and_ce():
    probs = [[0.7, 0.2, 0.1], [0.1, 0.3, 0.6]]
    labels = [0, 1]
    metrics = classification_metrics(probs, labels, top_k_values=(1, 2))
    assert metrics["top_1_accuracy"] == 0.5
    assert metrics["top_2_accuracy"] == 1.0
    assert metrics["cross_entropy"] > 0.0
    assert metrics["nll"] == metrics["cross_entropy"]


def test_split_by_deal_prevents_leakage():
    rows = [
        {"deal_id": "d1", "x": 1},
        {"deal_id": "d1", "x": 2},
        {"deal_id": "d2", "x": 3},
        {"deal_id": "d3", "x": 4},
    ]
    train, val, test = split_by_deal(rows, train_ratio=0.34, val_ratio=0.33, seed=7)
    train_deals = {r["deal_id"] for r in train}
    val_deals = {r["deal_id"] for r in val}
    test_deals = {r["deal_id"] for r in test}
    assert train_deals.isdisjoint(val_deals)
    assert train_deals.isdisjoint(test_deals)
    assert val_deals.isdisjoint(test_deals)


def test_bid_and_card_error_analysis_reports():
    id_to_label = {0: "1C", 1: "P", 2: "AS"}
    bid_rows = [{"seat_to_act": 1, "bid_prefix": []}, {"seat_to_act": 1, "bid_prefix": []}]
    bid_conf = bid_confusion_report([0, 1], [1, 1], id_to_label)
    assert bid_conf["total_errors"] == 1

    card_rows = [
        {"hand_cards": ["AS", "KH"], "play_prefix": []},
        {"hand_cards": ["AS", "KH"], "play_prefix": [{"player": 1, "card": "2H"}]},
    ]
    report = card_error_buckets(card_rows, [2, 2], [2, 2], id_to_label)
    assert set(report) == {"card_legality", "trick_stage"}
