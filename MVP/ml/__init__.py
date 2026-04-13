"""ML helpers for GEKO MVP."""

from .dataset_export import (
    BiddingExample,
    CardPlayExample,
    DatasetBuildStats,
    build_cardplay_examples,
    build_bidding_examples,
    build_bidding_examples_from_snapshot,
    build_datasets_from_snapshot_jsonl,
    build_cardplay_examples_from_snapshot,
    flatten_bid_history,
    group_snapshots_by_deal_id,
    select_representative_bidding_snapshot,
    write_jsonl,
    write_parquet,
)
from .derive_contract import ContractMeaning, derive_contract_from_auction
from .inference import recommend_next_bid, recommend_next_card
from .masks import bid_legality_mask, card_legality_mask, is_legal_bid, legal_bids, legal_cards
from .normalize import normalize_bid, normalize_bid_history, normalize_card
from .problem_definition import (
    COMPASS_TO_SEAT_ID,
    LOCKED_PROBLEM_DEFINITION,
    SEAT_ID_TO_COMPASS,
    LabelSource,
    ProblemDefinition,
    VisibilityPolicy,
    auction_seat_to_act,
)
from .preprocess import ReconstructionResult, compute_deal_id, reconstruct_full_hands
from .splits import split_by_deal
from .tokenizer import Tokenizer
from .train_common import MajorityClassifier
from .train_next_bid import main as train_next_bid_main
from .train_next_card import main as train_next_card_main

__all__ = [
    "bid_legality_mask",
    "card_legality_mask",
    "recommend_next_bid",
    "recommend_next_card",
    "is_legal_bid",
    "legal_bids",
    "legal_cards",
    "BiddingExample",
    "CardPlayExample",
    "DatasetBuildStats",
    "ContractMeaning",
    "ReconstructionResult",
    "Tokenizer",
    "MajorityClassifier",
    "train_next_bid_main",
    "train_next_card_main",
    "ProblemDefinition",
    "VisibilityPolicy",
    "LabelSource",
    "LOCKED_PROBLEM_DEFINITION",
    "SEAT_ID_TO_COMPASS",
    "COMPASS_TO_SEAT_ID",
    "auction_seat_to_act",
    "build_bidding_examples",
    "build_bidding_examples_from_snapshot",
    "build_cardplay_examples",
    "build_cardplay_examples_from_snapshot",
    "build_datasets_from_snapshot_jsonl",
    "compute_deal_id",
    "derive_contract_from_auction",
    "flatten_bid_history",
    "group_snapshots_by_deal_id",
    "normalize_bid",
    "normalize_bid_history",
    "normalize_card",
    "reconstruct_full_hands",
    "select_representative_bidding_snapshot",
    "split_by_deal",
    "write_jsonl",
    "write_parquet",
]
