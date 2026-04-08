"""Deterministic demo scenarios for reproducible coaching runs."""

from __future__ import annotations

from typing import Any, Dict

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "balanced_game": {
        "description": "Balanced notrump auction and natural card play demo.",
        "board_number": 2,
        "start_positions": [1, 2, 3, 4],
        "hands": {
            1: ["AC", "KC", "QC", "4C", "AD", "KD", "3D", "AH", "QH", "4H", "KS", "5S", "2S"],
            2: ["JC", "10C", "8C", "7C", "10D", "9D", "5D", "KH", "10H", "8H", "AS", "JS", "9S"],
            3: ["9C", "6C", "5C", "2C", "QD", "JD", "8D", "7D", "JH", "9H", "6H", "QS", "10S"],
            4: ["3C", "2D", "6D", "4D", "2H", "7H", "5H", "3H", "8S", "7S", "6S", "4S", "3S"],
        },
        "scripted_auction": ["1NT", "P", "3NT", "P", "P", "P"],
        "scripted_contract": [3, "NT", 1, 1],
        "scripted_card_prefix": ["AC", "7C", "2C", "3C"],
    },
    "major_fit_push": {
        "description": "Major-suit fit auction with competitive pressure.",
        "board_number": 7,
        "start_positions": [2, 3, 4, 1],
        "hands": {
            1: ["AH", "KH", "QH", "JH", "9H", "4H", "AD", "KD", "2D", "AS", "8S", "6C", "4C"],
            2: ["10H", "8H", "7H", "5H", "3H", "QD", "10D", "9D", "KS", "QS", "10S", "QC", "8C"],
            3: ["6H", "2H", "JD", "8D", "7D", "6D", "5D", "JS", "9S", "7S", "AC", "KC", "9C"],
            4: ["4D", "3D", "2S", "5S", "4S", "3S", "6S", "JC", "10C", "7C", "5C", "3C", "2C"],
        },
        "scripted_auction": ["1H", "P", "2H", "P", "4H", "P", "P", "P"],
        "scripted_contract": [4, "H", 1, 1],
    },
}


def get_demo_scenario(name: str) -> Dict[str, Any]:
    key = name.strip().lower()
    if key not in SCENARIOS:
        available = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unknown demo scenario '{name}'. Available: {available}")
    return SCENARIOS[key]


def list_demo_scenarios() -> Dict[str, str]:
    return {name: payload.get("description", "") for name, payload in SCENARIOS.items()}
