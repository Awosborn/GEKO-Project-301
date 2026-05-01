"""Interactive single-hand test for the bridge bid coach."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from bridge_bid_coach.coach import coach_game_state
from bridge_bid_coach.schemas import GameState

MODEL_DIR = str(Path(__file__).parent / "model")

print("\n=== Bridge Bid Coach — Quick Test ===\n")
print("Hand format example:  S AKQ H J94 D T862 C K73")
print("Bid format examples:  1H  2NT  Pass  Double  Redouble\n")

hand        = input("Your hand            : ").strip()
seat        = input("Your seat (N/S/E/W)  : ").strip().lower()
dealer      = input("Dealer (N/S/E/W)     : ").strip().lower()
vuln        = input("Vulnerability (none/NS/EW/both): ").strip().lower()
user_bid    = input("Bid you made         : ").strip()
legal_raw   = input("Legal bids (space-separated, or Enter to skip): ").strip()
auction_raw = input("Auction so far (e.g. '1H Pass 2H' or Enter to skip): ").strip()
top3_raw    = input("Model's top-3 bids (space-separated, or Enter to skip): ").strip()

seat_map = {"n": "north", "s": "south", "e": "east", "w": "west"}
seat   = seat_map.get(seat, seat)
dealer = seat_map.get(dealer, dealer)

legal_bids = legal_raw.split() if legal_raw else []
top_3      = top3_raw.split() if top3_raw else []

seats_cycle = ["north", "east", "south", "west"]
auction_history = []
if auction_raw:
    calls = auction_raw.split()
    dealer_idx = seats_cycle.index(dealer) if dealer in seats_cycle else 0
    for i, call in enumerate(calls):
        auction_history.append({
            "seat": seats_cycle[(dealer_idx + i) % 4],
            "call": call
        })

state = GameState(
    dealer=dealer,
    vulnerability=vuln,
    current_seat=seat,
    auction_history=auction_history,
    legal_bids=legal_bids,
    user_bid=user_bid,
    top_3_model_bids=top_3,
    hand=hand,
)

print("\n--- Running model... ---\n")
response = coach_game_state(state, model_dir=MODEL_DIR)
print(json.dumps(response.model_dump(exclude={"raw_model_text"}), indent=2))
