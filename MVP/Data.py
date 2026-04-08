"""Core data storage for one contract bridge game loop."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Tuple

SUITS: Tuple[str, ...] = ("C", "D", "H", "S")
RANKS: Tuple[str, ...] = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
PLAYERS: Tuple[int, ...] = (1, 2, 3, 4)


def build_deck() -> List[str]:
    """Create a standard ordered deck from 2C to AS."""
    return [f"{rank}{suit}" for rank in RANKS for suit in SUITS]


@dataclass
class DoubleDummyOutcome:
    """Projected best contract and score from a double-dummy style estimate."""

    contract: str
    declarer: int
    expected_tricks: int
    projected_score: int


@dataclass
class StrategyDeclaration:
    """Stores partnership-system preferences as numeric answers."""

    question_bank: List[Tuple[str, str, Tuple[str, ...]]] = field(
        default_factory=lambda: [
            ("Opening minimum in 1st seat", "numeric", ("HCP",)),
            ("Opening minimum in 2nd seat", "numeric", ("HCP",)),
            ("Opening minimum in 3rd seat", "numeric", ("HCP",)),
            ("Opening minimum in 4th seat", "numeric", ("HCP",)),
            ("Major-suit opening style", "choice", ("Very sound", "Sound", "Normal", "Light", "Very light")),
            ("Minor-suit opening style", "choice", ("Very sound", "Sound", "Normal", "Light", "Very light")),
            ("1NT opening minimum", "numeric", ("HCP",)),
            ("1NT opening maximum", "numeric", ("HCP",)),
            ("Open 1NT with a 5-card major", "choice", ("Yes", "No", "Sometimes")),
            ("2NT opening minimum", "numeric", ("HCP",)),
            ("2NT opening maximum", "numeric", ("HCP",)),
            ("Meaning of 2♣ opening", "choice", ("Strong artificial", "Strong but natural", "Game forcing", "Other fixed meaning")),
            ("Meaning of 2♦ opening", "choice", ("Weak two", "Flannery", "Multi", "Strong artificial", "Natural", "Other fixed meaning")),
            ("Meaning of 2♥ opening", "choice", ("Weak two", "Intermediate", "Strong", "Natural forcing", "Other fixed meaning")),
            ("Meaning of 2♠ opening", "choice", ("Weak two", "Intermediate", "Strong", "Natural forcing", "Other fixed meaning")),
            ("Weak-two style", "choice", ("None", "Sound", "Normal", "Aggressive")),
            ("3-level preempt style", "choice", ("Sound", "Normal", "Aggressive", "Very aggressive")),
            ("Preempting adjusted by vulnerability", "choice", ("Strongly adjusted", "Somewhat adjusted", "Barely adjusted", "Not adjusted")),
            ("Major opening length requirement", "choice", ("Always 5", "Usually 5", "Can be 4")),
            ("Minor opening with 3-3 minors", "choice", ("Open clubs", "Open diamonds", "Depends on strength")),
            ("Open clubs with longer diamonds sometimes", "choice", ("Yes", "No", "Sometimes")),
            ("Single raise of partner’s major", "choice", ("6-9 support", "6-10 support", "7-10 support", "Constructive", "Mixed style")),
            ("Single raise of partner’s minor", "choice", ("Weak", "Constructive", "Invitational", "Mixed style")),
            ("Raise structure in majors", "choice", ("Standard", "Limit+", "Mixed raises", "Bergen", "Other fixed structure")),
            ("Jump raise of partner’s major", "choice", ("Preemptive", "Invitational", "Mixed", "Limit", "Game forcing")),
            ("Jump raise of partner’s minor", "choice", ("Weak", "Invitational", "Preemptive", "Mixed")),
            ("Inverted minors", "choice", ("Yes", "No")),
            ("Support with invitational strength after major opening", "choice", ("Direct raise", "New suit then raise", "2NT", "Mixed methods")),
            ("Support with game-forcing strength after major opening", "choice", ("Jacoby 2NT", "New suit then support", "Splinter", "Mixed methods")),
            ("1NT response structure", "choice", ("Stayman + transfers", "Stayman only", "Transfers only", "Custom structure")),
            ("Stayman usage", "choice", ("4-card major only", "Any invitational hand", "Includes weak hands", "Includes non-major hands")),
            ("Transfer usage over 1NT", "choice", ("Jacoby only", "Texas only", "Both", "None")),
            ("Slam try method after 1NT", "choice", ("Quantitative", "Texas then cue-bid", "Gerber", "RKC-based", "Mixed methods")),
            ("Structure after 2NT opening", "choice", ("Puppet Stayman + transfers", "Stayman + transfers", "Natural", "Custom structure")),
            ("Structure after strong 2♣ opening", "choice", ("Waiting 2♦", "Positive-response style", "Kokish", "Custom structure")),
            ("Jacoby 2NT over major opening", "choice", ("Yes", "No")),
            ("Splinters", "choice", ("Yes", "No", "Limited use")),
            ("Fourth-suit forcing", "choice", ("1 round", "Game forcing", "Not played")),
            ("Two-over-one", "choice", ("Game forcing", "Invitational", "Mixed", "Not played")),
            ("New suit by responder", "choice", ("Always forcing", "Forcing 1 round", "Non-forcing at 1-level", "Depends on sequence")),
            ("Opener rebid style with extra values", "choice", ("Conservative", "Normal", "Aggressive")),
            ("Balanced rebid style after 1-level opening", "choice", ("Strictly by range", "Flexible by shape", "Flexible by stopper quality")),
            ("Jump shifts by opener", "choice", ("Strong", "Weak", "Splinter", "Fit-showing", "Not used")),
            ("Jump shifts by responder", "choice", ("Weak", "Strong", "Bergen", "Fit-showing", "Not used")),
            ("Reverses by opener", "choice", ("Strict extras", "Normal extras", "Aggressive")),
            ("Cue bid in competition", "choice", ("Limit raise or better", "Michaels", "Stopper ask", "Fit-showing", "Mixed by position")),
            ("Double in direct seat", "choice", ("Takeout", "Penalty", "Either depending on context", "Custom")),
            ("Double in balancing seat", "choice", ("Takeout", "Optional", "Penalty", "Custom")),
            ("1-level overcall style", "choice", ("Sound", "Normal", "Aggressive")),
            ("2-level overcall style", "choice", ("Sound", "Normal", "Aggressive")),
            ("1NT overcall range minimum", "numeric", ("HCP",)),
            ("1NT overcall range maximum", "numeric", ("HCP",)),
            ("Defense versus opponent 1NT", "choice", ("Natural", "DONT", "Cappelletti", "Meckwell", "Landy", "Other fixed defense")),
            ("Defense versus strong club/artificial openings", "choice", ("Natural", "Suction", "CRASH", "Other fixed defense", "None special")),
            ("Response to takeout double", "choice", ("Standard", "Lebensohl", "Jordan", "Mixed methods")),
            ("Negative doubles", "choice", ("Yes", "No")),
            ("Support doubles/redoubles", "choice", ("Support doubles only", "Support doubles and redoubles", "None")),
            ("Advanced doubles", "choice", ("Responsive", "Maximal", "Snapdragon", "Several", "None")),
            ("Keycard method", "choice", ("Standard Blackwood", "RKCB 1430", "RKCB 0314", "Other fixed method", "None")),
            ("Control-bid style for slam", "choice", ("First-round only", "First and second-round", "Italian style", "Not used")),
            ("Opening lead style vs suit contracts", "choice", ("4th best", "3rd-5th", "Rusinow", "Top of sequence", "Mixed style")),
            ("Opening lead style vs notrump", "choice", ("4th best", "Attitude", "Journalist", "Top of sequence", "Mixed style")),
            ("Attitude signals", "choice", ("Standard", "Upside-down", "Odd-even", "Mixed")),
            ("Count signals", "choice", ("Standard", "Upside-down", "Mixed", "Rarely used")),
            ("Suit-preference signals", "choice", ("Standard high-low", "Upside-down", "Rarely used", "Context only")),
            ("Primary defensive signaling priority", "choice", ("Attitude", "Count", "Suit preference", "Context dependent")),
            ("Discarding method", "choice", ("Standard", "Upside-down", "Odd-even", "Lavinthal style", "Mixed")),
            ("Signal in partner’s led suit", "choice", ("Attitude first", "Count first", "Context dependent")),
            ("Defensive switching style", "choice", ("Conservative", "Normal", "Aggressive")),
            ("Trump management on defense", "choice", ("Draw declarer trumps early", "Preserve trumps", "Context dependent")),
            ("Lead style against slam", "choice", ("Passive", "Normal", "Aggressive", "Looking for ruff")),
            ("Lead style against preemptive contracts", "choice", ("Passive", "Normal", "Aggressive")),
            ("Declarer style in notrump", "choice", ("Safety-first", "Normal percentages", "Aggressive overtricks")),
            ("Declarer style in suit contracts", "choice", ("Safety-first", "Normal percentages", "Aggressive overtricks")),
            ("Table feel / deviation from system", "choice", ("Never", "Rarely", "Sometimes", "Often")),
        ]
    )
    numeric_answers: List[int] = field(default_factory=list)
    loaded_profile_name: Optional[str] = None
    loaded_profile_version: Optional[str] = None

    def Strat_define(self) -> List[int]:
        """Prompt user to define strategy and return numeric answer array."""
        self.numeric_answers = []
        for index, (question, answer_type, options) in enumerate(self.question_bank, start=1):
            print(f"\n{index}. {question}")
            if answer_type == "numeric":
                while True:
                    try:
                        value = int(input("Enter numeric value: ").strip())
                        self.numeric_answers.append(value)
                        break
                    except ValueError:
                        print("Invalid input. Please enter an integer.")
            else:
                for option_index, option in enumerate(options, start=1):
                    print(f"  {option_index}) {option}")
                while True:
                    try:
                        choice = int(input("Select option number: ").strip())
                        if 1 <= choice <= len(options):
                            self.numeric_answers.append(choice)
                            break
                        print(f"Please choose a number between 1 and {len(options)}.")
                    except ValueError:
                        print("Invalid input. Please enter a valid option number.")
        return self.numeric_answers

    def load(self, profile_number: int) -> List[int]:
        """
        Load a predefined strategy profile from MVP/bridge_nine_strategy_profiles.json.

        Notes:
        - Accepts profile numbers 1-9 (inclusive), as requested by the MVP profile set.
        - Converts profile answer values into the same numeric encoding used by Strat_define:
          numeric question -> literal integer, choice question -> 1-based option index.
        """
        if not 1 <= profile_number <= 9:
            raise ValueError("profile_number must be between 1 and 9.")

        profiles_path = Path(__file__).resolve().parent / "bridge_nine_strategy_profiles.json"
        payload = json.loads(profiles_path.read_text(encoding="utf-8"))
        profiles = payload.get("profiles", [])

        if profile_number > len(profiles):
            raise ValueError(
                f"Profile {profile_number} is unavailable. "
                f"Found {len(profiles)} profiles in {profiles_path.name}."
            )

        profile = profiles[profile_number - 1]
        answers = profile.get("answers", {})

        # deterministic key ordering: q1_..., q2_..., ... q75_...
        sorted_items = sorted(
            answers.items(),
            key=lambda item: int(item[0].split("_", 1)[0][1:]),
        )

        if len(sorted_items) != len(self.question_bank):
            raise ValueError(
                "Loaded profile answer count does not match StrategyDeclaration question count."
            )

        loaded_numeric_answers: List[int] = []
        for question_index, (answer_key, raw_answer) in enumerate(sorted_items):
            _, answer_type, options = self.question_bank[question_index]
            if answer_type == "numeric":
                if not isinstance(raw_answer, int):
                    raise ValueError(
                        f"{answer_key} expects numeric answer, received {type(raw_answer).__name__}."
                    )
                loaded_numeric_answers.append(raw_answer)
                continue

            # choice answer: store option number (1-based), matching Strat_define behavior.
            try:
                option_index = options.index(str(raw_answer)) + 1
            except ValueError as exc:
                raise ValueError(
                    f"{answer_key} has unsupported option '{raw_answer}'."
                ) from exc
            loaded_numeric_answers.append(option_index)

        self.numeric_answers = loaded_numeric_answers
        self.loaded_profile_name = profile.get("strategy_name")
        self.loaded_profile_version = str(profile.get("version", f"profile-{profile_number}"))
        return self.numeric_answers


def strategy_answers_hash(strategy_answers: List[int]) -> str:
    """Build a deterministic hash for a full strategy answer declaration."""
    normalized = ",".join(str(int(value)) for value in strategy_answers)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class EpochMetadata:
    """Epoch-level strategy declaration metadata for reproducible training."""

    epoch_id: str
    strategy_profile_name: str
    strategy_profile_version: str
    strategy_answers_hash: str
    strategy_answers_numeric: List[int]


@dataclass
class GameData:
    """Stores all current and historical values used by the MVP game loop."""

    strat_dec: StrategyDeclaration = field(default_factory=StrategyDeclaration)
    curr_card_hold: List[List[str]] = field(default_factory=lambda: [[] for _ in PLAYERS])
    curr_bid_hist: List[List[Optional[str]]] = field(default_factory=list)
    curr_points: Dict[int, int] = field(default_factory=lambda: {player: 0 for player in PLAYERS})
    hist_points: Dict[int, int] = field(default_factory=lambda: {player: 0 for player in PLAYERS})
    board_number: int = 0
    vulnerability: Dict[int, bool] = field(default_factory=lambda: {player: False for player in PLAYERS})
    double_dummy_outcome: Optional[DoubleDummyOutcome] = None
    bid_infractions: List[Dict[str, Any]] = field(default_factory=list)
    penalty_points_by_player: Dict[int, int] = field(default_factory=lambda: {player: 0 for player in PLAYERS})
    penalty_reason_breakdown: Dict[str, int] = field(default_factory=dict)
    round_result_payload: Dict[str, Any] = field(default_factory=dict)
    epoch_metadata: Optional[EpochMetadata] = None

    def reset_round_state(self) -> None:
        """Clear all hand-specific data before a new hand is dealt."""
        self.curr_card_hold = [[] for _ in PLAYERS]
        self.curr_bid_hist = []
        self.curr_points = {player: 0 for player in PLAYERS}
        self.double_dummy_outcome = None
        self.bid_infractions = []
        self.penalty_points_by_player = {player: 0 for player in PLAYERS}
        self.penalty_reason_breakdown = {}
        self.round_result_payload = {}

    def set_board_vulnerability(self) -> None:
        """Apply duplicate-bridge vulnerability pattern based on board number."""
        # Standard 16-board cycle:
        # 1 None, 2 N-S, 3 E-W, 4 All, 5 N-S, 6 E-W, 7 All, 8 None,
        # 9 E-W, 10 All, 11 None, 12 N-S, 13 All, 14 None, 15 N-S, 16 E-W
        cycle = [
            (False, False),
            (True, False),
            (False, True),
            (True, True),
            (True, False),
            (False, True),
            (True, True),
            (False, False),
            (False, True),
            (True, True),
            (False, False),
            (True, False),
            (True, True),
            (False, False),
            (True, False),
            (False, True),
        ]
        ns_vul, ew_vul = cycle[(self.board_number - 1) % 16]
        self.vulnerability = {1: ns_vul, 3: ns_vul, 2: ew_vul, 4: ew_vul}

    def next_board(self) -> None:
        """Advance to the next board and update vulnerability."""
        self.board_number += 1
        self.set_board_vulnerability()

    def randomize_board(self, rng: random.Random | None = None) -> None:
        """Pick a random board number (1-16) and apply its vulnerability."""
        rng = rng or random.Random()
        self.board_number = rng.randint(1, 16)
        self.set_board_vulnerability()

    def record_bid(self, player: int, bid: str) -> None:
        """Append bids in rows of four columns that map to players 1-4."""
        if not self.curr_bid_hist or all(cell is not None for cell in self.curr_bid_hist[-1]):
            self.curr_bid_hist.append([None, None, None, None])
        self.curr_bid_hist[-1][player - 1] = bid

    def set_epoch_metadata(self, epoch_id: str) -> EpochMetadata:
        """Attach reproducible epoch strategy declaration metadata to this board."""
        if not self.strat_dec.numeric_answers:
            raise ValueError("Cannot set epoch metadata without strategy numeric_answers.")

        metadata = EpochMetadata(
            epoch_id=str(epoch_id),
            strategy_profile_name=self.strat_dec.loaded_profile_name or "custom",
            strategy_profile_version=self.strat_dec.loaded_profile_version or "unversioned",
            strategy_answers_hash=strategy_answers_hash(self.strat_dec.numeric_answers),
            strategy_answers_numeric=[int(value) for value in self.strat_dec.numeric_answers],
        )
        self.epoch_metadata = metadata
        return metadata

    def record_infraction(
        self,
        *,
        player: int,
        bid: str,
        rule_type: str,
        message: str,
        auction_index: int,
        penalty_points: int,
    ) -> None:
        """Store a normalized infraction record and accumulate penalties."""
        self.bid_infractions.append(
            {
                "player": player,
                "bid": bid,
                "rule_type": rule_type,
                "message": message,
                "auction_index": auction_index,
                "penalty_points": penalty_points,
            }
        )
        self.penalty_points_by_player[player] += penalty_points
        self.penalty_reason_breakdown[rule_type] = self.penalty_reason_breakdown.get(rule_type, 0) + penalty_points

    def add_round_points(self, round_points: Dict[int, int]) -> None:
        """Save points earned this round and update historical totals."""
        for player in PLAYERS:
            delta = round_points.get(player, 0)
            self.curr_points[player] = delta
            self.hist_points[player] += delta
