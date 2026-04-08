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
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from BiddingModel import BID_VOCAB, BridgeBiddingModel


TOKEN_STORE_PATH = Path(__file__).resolve().parent / "training_tokens.json"


@dataclass
class BidStep:
    """One chronological auction action with context and latent snapshots."""

    step_index: int
    bidder: int
    bid: str
    bid_token: int
    is_opponent_bid: bool
    is_partner_bid: bool
    context_features: Dict[str, float]
    latent_before: List[float]
    latent_after: List[float]


@dataclass
class AuctionEpisode:
    """Container used for episode-level delayed learning."""

    epoch_id: str
    board_hand_id: str
    strategy_snapshot: Dict[str, float]
    bid_steps: List[BidStep] = field(default_factory=list)
    latent_state: List[float] = field(default_factory=list)
    latent_trajectory: List[List[float]] = field(default_factory=list)
    final_contract: Optional[str] = None
    legality_flags: Dict[str, bool] = field(default_factory=dict)
    score_delta: float = 0.0
    penalties: Dict[str, float] = field(default_factory=dict)
    reward_components: Dict[str, float] = field(default_factory=dict)


class AuctionEpisodeRunner(BridgeBiddingModel):
    """Bridge bidding runner with episode-oriented delayed credit assignment.

    The only place any learning update is applied is
    :meth:`close_auction_and_learn`.
    """

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

    def _zero_latent(self) -> List[float]:
        return [0.0] * self.latent_size

    def _token_for_bid(self, bid: str) -> int:
        clean_bid = self._normalize_bid(bid)
        # Prefer persisted training token IDs when available.
        if clean_bid in self._persisted_bid_tokens:
            return self._persisted_bid_tokens[clean_bid]
        # Fallback to static BID_VOCAB compatibility.
        return self.bid_to_id[clean_bid]

    def _encode_strategy_answers(self, strategy_answers: Sequence[float]) -> Dict[str, float]:
        return {f"strategy_q_{idx+1}": float(value) for idx, value in enumerate(strategy_answers)}

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

    def start_epoch(
        self,
        epoch_id: str,
        strategy_answers: Sequence[float],
        board_hand_id: str,
    ) -> AuctionEpisode:
        """Start a new auction episode with epoch strategy declaration snapshot."""
        if self.current_episode is not None:
            raise RuntimeError("Current episode is still active. Close it before starting a new one.")

        snapshot = self._encode_strategy_answers(strategy_answers)
        episode = AuctionEpisode(
            epoch_id=str(epoch_id),
            board_hand_id=str(board_hand_id),
            strategy_snapshot=snapshot,
            latent_state=self._zero_latent(),
        )
        episode.latent_trajectory.append(list(episode.latent_state))
        self.current_episode = episode
        return episode

    def record_bid_step(self, player: int, bid: str, context_features: Optional[Dict[str, float]] = None) -> BidStep:
        """Append one bid event and update latent state for the active episode."""
        if self.current_episode is None:
            raise RuntimeError("No active episode. Call start_epoch(...) first.")
        if player not in (1, 2, 3, 4):
            raise ValueError("player must be one of 1, 2, 3, 4")

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
            context_features={k: float(v) for k, v in context.items()},
            latent_before=latent_before,
            latent_after=latent_after,
        )
        self.current_episode.bid_steps.append(step)
        self.current_episode.latent_state = list(latent_after)
        self.current_episode.latent_trajectory.append(list(latent_after))
        return step

    def _build_training_record(self, episode: AuctionEpisode) -> Dict[str, object]:
        encoded_sequence = [
            {
                "step": s.step_index,
                "bid_token": s.bid_token,
                "bidder": s.bidder,
                "bidder_token": s.bidder - 1,
                "is_opponent_bid": int(s.is_opponent_bid),
                "is_partner_bid": int(s.is_partner_bid),
                "context_features": s.context_features,
            }
            for s in episode.bid_steps
        ]

        return {
            "epoch_id": episode.epoch_id,
            "board_hand_id": episode.board_hand_id,
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

    def close_auction_and_learn(
        self,
        final_contract: str,
        reward_components: Dict[str, float],
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

        # Delayed credit-assignment target (single scalar), computed only at close.
        total_reward = sum(episode.reward_components.values())

        record = self._build_training_record(episode)
        record["terminal"]["total_reward"] = total_reward

        self.training_records.append(record)
        self.current_episode = None
        return record


# Backward-friendly alias in case callers import the old module as a runner object.
RunnerBiddingModel = AuctionEpisodeRunner
