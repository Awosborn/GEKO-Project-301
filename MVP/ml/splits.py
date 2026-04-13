"""Group-aware split helpers to avoid deal-level leakage."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, List, Mapping, Sequence, Tuple


def split_by_deal(
    examples: Sequence[Mapping[str, object]],
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    seed: int = 1337,
) -> Tuple[List[Mapping[str, object]], List[Mapping[str, object]], List[Mapping[str, object]]]:
    if train_ratio <= 0 or val_ratio < 0 or train_ratio + val_ratio >= 1:
        raise ValueError("Expected ratios satisfying train_ratio > 0, val_ratio >= 0, and train+val < 1")

    grouped: Dict[str, List[Mapping[str, object]]] = defaultdict(list)
    for ex in examples:
        grouped[str(ex["deal_id"])].append(ex)

    deal_ids = list(grouped.keys())
    random.Random(seed).shuffle(deal_ids)

    n = len(deal_ids)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)

    train_deals = set(deal_ids[:n_train])
    val_deals = set(deal_ids[n_train : n_train + n_val])

    train: List[Mapping[str, object]] = []
    val: List[Mapping[str, object]] = []
    test: List[Mapping[str, object]] = []

    for deal_id, group in grouped.items():
        if deal_id in train_deals:
            train.extend(group)
        elif deal_id in val_deals:
            val.extend(group)
        else:
            test.extend(group)

    return train, val, test
