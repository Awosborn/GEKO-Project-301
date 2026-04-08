"""Episode-based bidding runner for delayed bridge-auction learning.

This module extends the tokenization in ``BiddingModel.py`` with an episode object
that captures:
- board/hand identity,
- epoch strategy declarations,
- ordered bidder-aware auction actions,
- latent-state trajectory,
- terminal outcome + reward decomposition.

Learning updates are intentionally delayed until auction close.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from BiddingModel import BID_VOCAB, BridgeBiddingModel
from PenaltyConfig import ACBL_BREAK_PENALTY, STRAT_BREAK_PENALTY


TOKEN_STORE_PATH = Path(__file__).resolve().parent / "training_tokens.json"


# Data container: BidStep.
@dataclass
# Class: BidStep.
class BidStep:
    """One chronological auction action with context and latent snapshots."""

    step_index: int
    bidder: int
    bid: str
    bid_token: int
    is_opponent_bid: bool
    is_partner_bid: bool
    strategy_answers_hash: str
    strategy_answers: List[float]
    context_features: Dict[str, float]
    latent_before: List[float]
    latent_after: List[float]


# Data container: AuctionEpisode.
@dataclass
# Class: AuctionEpisode.
class AuctionEpisode:
    """Container used for episode-level delayed learning."""

    epoch_id: str
    board_hand_id: str
    strategy_profile_name: str
    strategy_profile_version: str
    strategy_answers_hash: str
    strategy_answers: List[float]
    strategy_snapshot: Dict[str, float]
    bid_steps: List[BidStep] = field(default_factory=list)
    latent_state: List[float] = field(default_factory=list)
    latent_trajectory: List[List[float]] = field(default_factory=list)
    final_contract: Optional[str] = None
    legality_flags: Dict[str, bool] = field(default_factory=dict)
    score_delta: float = 0.0
    penalties: Dict[str, float] = field(default_factory=dict)
    reward_components: Dict[str, float] = field(default_factory=dict)


# Class: AuctionEpisodeRunner.
class AuctionEpisodeRunner(BridgeBiddingModel):
    """Bridge bidding runner with episode-oriented delayed credit assignment.

    The only place any learning update is applied is
    :meth:`close_auction_and_learn`.
    """

    # Function: __init__.
    def __init__(
        self,
        focus_player: int = 1,
        latent_size: int = 16,
        token_store_path: Path = TOKEN_STORE_PATH,
    ) -> None:
        super().__init__(focus_player=focus_player)
        if latent_size <= 0:
            raise ValueError("latent_size must be > 0")

        self.latent_size = latent_size
        self.token_store_path = token_store_path
        self._persisted_bid_tokens = self._load_persisted_bid_tokens(token_store_path)

        self.current_episode: Optional[AuctionEpisode] = None
        self.training_records: List[Dict[str, object]] = []

    # Function: _load_persisted_bid_tokens.
    def _load_persisted_bid_tokens(self, path: Path) -> Dict[str, int]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

        bids = payload.get("bids", {})
        loaded: Dict[str, int] = {}
        for symbol, spec in bids.items():
            bid = str(symbol).upper()
            if bid in BID_VOCAB and isinstance(spec, dict) and "id" in spec:
                loaded[bid] = int(spec["id"])
        return loaded

    # Function: _zero_latent.
    def _zero_latent(self) -> List[float]:
        return [0.0] * self.latent_size

    # Function: _token_for_bid.
    def _token_for_bid(self, bid: str) -> int:
        clean_bid = self._normalize_bid(bid)
        # Prefer persisted training token IDs when available.
        if clean_bid in self._persisted_bid_tokens:
            return self._persisted_bid_tokens[clean_bid]
        # Fallback to static BID_VOCAB compatibility.
        return self.bid_to_id[clean_bid]

    # Function: _encode_strategy_answers.
    def _encode_strategy_answers(self, strategy_answers: Sequence[float]) -> Dict[str, float]:
        return {f"strategy_q_{idx+1}": float(value) for idx, value in enumerate(strategy_answers)}

    # Function: _strategy_answers_hash.
    def _strategy_answers_hash(self, strategy_answers: Sequence[float]) -> str:
        normalized = ",".join(str(float(value)) for value in strategy_answers)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    # Function: _update_latent.
    def _update_latent(
        self,
        prev_latent: Sequence[float],
        bid_token: int,
        bidder: int,
        is_opponent_bid: bool,
        context_features: Dict[str, float],
    ) -> List[float]:
        """Deterministic light-weight latent update for stepwise tracking.

        This update is stateful but model-agnostic so it can be swapped later by a
        trainable recurrent module.
        """
        next_latent: List[float] = []
        context_energy = sum(float(v) for v in context_features.values()) if context_features else 0.0
        side_sign = -1.0 if is_opponent_bid else 1.0

        for i, prior in enumerate(prev_latent):
            drift = (bid_token + 1) * 0.01
            seat_bias = bidder * 0.005
            ctx = context_energy * 0.001
            value = (prior * 0.85) + side_sign * drift + seat_bias + ctx + (i * 0.0005)
            next_latent.append(round(value, 6))

        return next_latent

    # Function: start_epoch.
    def start_epoch(
        self,
        epoch_id: str,
        strategy_answers: Sequence[float],
        board_hand_id: str,
        strategy_profile_name: str,
        strategy_profile_version: str,
    ) -> AuctionEpisode:
        """Start a new auction episode with epoch strategy declaration snapshot."""
        if self.current_episode is not None:
            raise RuntimeError("Current episode is still active. Close it before starting a new one.")
        if not strategy_answers:
            raise ValueError("strategy_answers must be explicitly provided and non-empty at epoch start.")

        strategy_answer_values = [float(value) for value in strategy_answers]
        snapshot = self._encode_strategy_answers(strategy_answer_values)
        answers_hash = self._strategy_answers_hash(strategy_answer_values)
        episode = AuctionEpisode(
            epoch_id=str(epoch_id),
            board_hand_id=str(board_hand_id),
            strategy_profile_name=str(strategy_profile_name),
            strategy_profile_version=str(strategy_profile_version),
            strategy_answers_hash=answers_hash,
            strategy_answers=strategy_answer_values,
            strategy_snapshot=snapshot,
            latent_state=self._zero_latent(),
        )
        episode.latent_trajectory.append(list(episode.latent_state))
        self.current_episode = episode
        return episode

    # Function: record_bid_step.
    def record_bid_step(
        self,
        player: int,
        bid: str,
        strategy_answers: Sequence[float],
        context_features: Optional[Dict[str, float]] = None,
    ) -> BidStep:
        """Append one bid event and update latent state for the active episode."""
        if self.current_episode is None:
            raise RuntimeError("No active episode. Call start_epoch(...) first.")
        if player not in (1, 2, 3, 4):
            raise ValueError("player must be one of 1, 2, 3, 4")
        if not strategy_answers:
            raise ValueError("strategy_answers must be explicitly provided on every bid step.")

        incoming_answers = [float(value) for value in strategy_answers]
        incoming_hash = self._strategy_answers_hash(incoming_answers)
        if incoming_hash != self.current_episode.strategy_answers_hash:
            raise RuntimeError(
                "Strategy declaration changed mid-epoch. "
                "Split the epoch before recording additional bid steps."
            )

        context = context_features or {}
        clean_bid = self._normalize_bid(bid)
        bid_token = self._token_for_bid(clean_bid)
        is_opponent_bid = self._is_opponent(player)
        is_partner_bid = not is_opponent_bid

        latent_before = list(self.current_episode.latent_state)
        latent_after = self._update_latent(
            prev_latent=latent_before,
            bid_token=bid_token,
            bidder=player,
            is_opponent_bid=is_opponent_bid,
            context_features=context,
        )

        step = BidStep(
            step_index=len(self.current_episode.bid_steps),
            bidder=player,
            bid=clean_bid,
            bid_token=bid_token,
            is_opponent_bid=is_opponent_bid,
            is_partner_bid=is_partner_bid,
            strategy_answers_hash=incoming_hash,
            strategy_answers=incoming_answers,
            context_features={k: float(v) for k, v in context.items()},
            latent_before=latent_before,
            latent_after=latent_after,
        )
        self.current_episode.bid_steps.append(step)
        self.current_episode.latent_state = list(latent_after)
        self.current_episode.latent_trajectory.append(list(latent_after))
        return step

    # Function: _build_training_record.
    def _build_training_record(self, episode: AuctionEpisode) -> Dict[str, object]:
        encoded_sequence = [
            {
                "step": s.step_index,
                "bid_token": s.bid_token,
                "bidder": s.bidder,
                "bidder_token": s.bidder - 1,
                "is_opponent_bid": int(s.is_opponent_bid),
                "is_partner_bid": int(s.is_partner_bid),
                "strategy_answers_hash": s.strategy_answers_hash,
                "strategy_answers": s.strategy_answers,
                "context_features": s.context_features,
            }
            for s in episode.bid_steps
        ]

        return {
            "epoch_id": episode.epoch_id,
            "board_hand_id": episode.board_hand_id,
            "epoch_strategy_metadata": {
                "strategy_profile_name": episode.strategy_profile_name,
                "strategy_profile_version": episode.strategy_profile_version,
                "strategy_profile_identifier": (
                    f"{episode.strategy_profile_name}@{episode.strategy_profile_version}"
                ),
                "strategy_answers_hash": episode.strategy_answers_hash,
                "strategy_answers": episode.strategy_answers,
            },
            "strategy_declaration_features": episode.strategy_snapshot,
            "encoded_sequence": encoded_sequence,
            "latent_trajectory": episode.latent_trajectory,
            "final_latent_summary": episode.latent_state,
            "terminal": {
                "final_contract": episode.final_contract,
                "legality_flags": episode.legality_flags,
                "score_delta": episode.score_delta,
                "penalties": episode.penalties,
                "reward_components": episode.reward_components,
            },
        }

    # Function: close_auction_and_learn.
    def close_auction_and_learn(
        self,
        final_contract: str,
        reward_components: Dict[str, float],
        double_dummy_target: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, object]:
        """Finalize auction and apply delayed episode-level learning update.

        This is intentionally the *only* method where learning updates occur.
        """
        if self.current_episode is None:
            raise RuntimeError("No active episode to close.")

        episode = self.current_episode
        episode.final_contract = final_contract.strip().upper()
        episode.reward_components = {k: float(v) for k, v in reward_components.items()}
        episode.legality_flags = {
            "valid_contract": bool(reward_components.get("valid_contract", True)),
            "legal_auction": bool(reward_components.get("legal_auction", True)),
        }
        episode.score_delta = float(reward_components.get("score_delta", 0.0))
        episode.penalties = {
            k: float(v)
            for k, v in reward_components.items()
            if "penalty" in k.lower() or k.lower().startswith("illegal")
        }

        strategy_breaks = float(reward_components.get("strategy_break_count", 0.0))
        acbl_breaks = float(reward_components.get("acbl_break_count", 0.0))
        explicit_total_penalty = float(reward_components.get("total_infraction_penalty", 0.0))

        terminal_violation_component = 0.0
        if explicit_total_penalty > 0:
            terminal_violation_component = -explicit_total_penalty
        else:
            terminal_violation_component = -((strategy_breaks * STRAT_BREAK_PENALTY) + (acbl_breaks * ACBL_BREAK_PENALTY))

        episode.reward_components["terminal_violation_component"] = float(terminal_violation_component)
        if double_dummy_target:
            solver_mode = str(double_dummy_target.get("solver_mode", "unknown"))
            is_heuristic = bool(double_dummy_target.get("is_heuristic", False))
            alternatives = double_dummy_target.get("contract_alternatives", [])
            dd_score_for_contract = float(double_dummy_target.get("projected_score", 0.0))
            contract_upper = episode.final_contract
            for alt in alternatives:
                if str(alt.get("contract", "")).upper() == contract_upper:
                    dd_score_for_contract = float(alt.get("projected_score", dd_score_for_contract))
                    break

            observed_score = float(reward_components.get("observed_score", 0.0))
            episode.reward_components["score_delta_vs_true_solver_contract"] = observed_score - dd_score_for_contract
            episode.reward_components["true_solver_signal_available"] = 0.0 if is_heuristic else 1.0
            episode.reward_components["heuristic_mode_penalty"] = -0.25 if is_heuristic else 0.0
            episode.reward_components["solver_mode_flag"] = 1.0 if solver_mode == "solver" else 0.0

        # Delayed credit-assignment target (single scalar), computed only at close.
        total_reward = sum(episode.reward_components.values())

        record = self._build_training_record(episode)
        record["terminal"]["total_reward"] = total_reward

        self.training_records.append(record)
        self.current_episode = None
        return record


# Backward-friendly alias in case callers import the old module as a runner object.
RunnerBiddingModel = AuctionEpisodeRunner
