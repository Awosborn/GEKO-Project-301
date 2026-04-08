"""Episode-based card-play runner for delayed bridge play learning.

This module mirrors ``RunnerBiddingModel.py`` for card play:
- epoch-level strategy declaration snapshot,
- optional bidding-model encoded auction context,
- ordered card-play events with latent-state trajectory,
- terminal reward formed by comparing observed result vs double-dummy target.

Learning updates are intentionally delayed until hand close.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from BiddingModel import BridgeBiddingModel
from CardPlayModel import BridgeCardPlayModel


TOKEN_STORE_PATH = Path(__file__).resolve().parent / "training_tokens.json"


# Data container: CardStep.
@dataclass
# Class: CardStep.
class CardStep:
    """One chronological card-play event with context and latent snapshots."""

    step_index: int
    trick_index: int
    player: int
    card: str
    card_token: int
    is_opponent_play: bool
    strategy_answers_hash: str
    strategy_answers: List[float]
    context_features: Dict[str, float]
    legal_card_tokens: List[int]
    latent_before: List[float]
    latent_after: List[float]


# Data container: CardPlayEpisode.
@dataclass
# Class: CardPlayEpisode.
class CardPlayEpisode:
    """Container used for episode-level delayed learning in card play."""

    epoch_id: str
    board_hand_id: str
    strategy_profile_name: str
    strategy_profile_version: str
    strategy_answers_hash: str
    strategy_answers: List[float]
    strategy_snapshot: Dict[str, float]
    bid_history_context: List[Dict[str, int]] = field(default_factory=list)
    card_steps: List[CardStep] = field(default_factory=list)
    latent_state: List[float] = field(default_factory=list)
    latent_trajectory: List[List[float]] = field(default_factory=list)
    observed_declarer_tricks: int = 0
    observed_score: float = 0.0
    double_dummy_target: Dict[str, float] = field(default_factory=dict)
    reward_components: Dict[str, float] = field(default_factory=dict)


# Class: CardPlayEpisodeRunner.
class CardPlayEpisodeRunner(BridgeCardPlayModel):
    """Bridge card-play runner with delayed credit assignment at hand close."""

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
        self._persisted_card_tokens = self._load_persisted_card_tokens(token_store_path)

        self.current_episode: Optional[CardPlayEpisode] = None
        self.training_records: List[Dict[str, object]] = []
        self.bidding_encoder = BridgeBiddingModel(focus_player=focus_player)

    # Function: _load_persisted_card_tokens.
    def _load_persisted_card_tokens(self, path: Path) -> Dict[str, int]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

        cards = payload.get("cards", {})
        loaded: Dict[str, int] = {}
        for symbol, spec in cards.items():
            card = str(symbol).upper()
            if card in self.card_to_id and isinstance(spec, dict) and "id" in spec:
                loaded[card] = int(spec["id"])
        return loaded

    # Function: _zero_latent.
    def _zero_latent(self) -> List[float]:
        return [0.0] * self.latent_size

    # Function: _token_for_card.
    def _token_for_card(self, card: str) -> int:
        clean_card = self._normalize_card(card)
        if clean_card in self._persisted_card_tokens:
            return self._persisted_card_tokens[clean_card]
        return self.card_to_id[clean_card]

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
        card_token: int,
        player: int,
        is_opponent_play: bool,
        context_features: Dict[str, float],
    ) -> List[float]:
        next_latent: List[float] = []
        context_energy = sum(float(v) for v in context_features.values()) if context_features else 0.0
        side_sign = -1.0 if is_opponent_play else 1.0

        for i, prior in enumerate(prev_latent):
            drift = (card_token + 1) * 0.0005
            seat_bias = player * 0.004
            ctx = context_energy * 0.001
            value = (prior * 0.9) + side_sign * drift + seat_bias + ctx + (i * 0.0005)
            next_latent.append(round(value, 6))
        return next_latent

    # Function: _build_bid_history_context.
    def _build_bid_history_context(
        self,
        raw_bid_history: Optional[Sequence[Sequence[Optional[str]]]],
        encoded_bid_history: Optional[Sequence[Dict[str, int]]],
    ) -> List[Dict[str, int]]:
        if encoded_bid_history is not None:
            return [dict(item) for item in encoded_bid_history]
        if raw_bid_history is None:
            return []
        return self.bidding_encoder.encode_bid_history(raw_bid_history)

    # Function: start_epoch.
    def start_epoch(
        self,
        epoch_id: str,
        strategy_answers: Sequence[float],
        board_hand_id: str,
        strategy_profile_name: str,
        strategy_profile_version: str,
        raw_bid_history: Optional[Sequence[Sequence[Optional[str]]]] = None,
        encoded_bid_history: Optional[Sequence[Dict[str, int]]] = None,
    ) -> CardPlayEpisode:
        """Start a new card-play episode with strategy + bidding context."""
        if self.current_episode is not None:
            raise RuntimeError("Current episode is still active. Close it before starting a new one.")
        if not strategy_answers:
            raise ValueError("strategy_answers must be explicitly provided and non-empty at epoch start.")

        strategy_answer_values = [float(value) for value in strategy_answers]
        snapshot = self._encode_strategy_answers(strategy_answer_values)
        answers_hash = self._strategy_answers_hash(strategy_answer_values)

        episode = CardPlayEpisode(
            epoch_id=str(epoch_id),
            board_hand_id=str(board_hand_id),
            strategy_profile_name=str(strategy_profile_name),
            strategy_profile_version=str(strategy_profile_version),
            strategy_answers_hash=answers_hash,
            strategy_answers=strategy_answer_values,
            strategy_snapshot=snapshot,
            bid_history_context=self._build_bid_history_context(raw_bid_history, encoded_bid_history),
            latent_state=self._zero_latent(),
        )
        episode.latent_trajectory.append(list(episode.latent_state))
        self.current_episode = episode
        return episode

    # Function: record_card_step.
    def record_card_step(
        self,
        player: int,
        card: str,
        strategy_answers: Sequence[float],
        trick_index: int,
        legal_cards: Optional[Sequence[str]] = None,
        context_features: Optional[Dict[str, float]] = None,
    ) -> CardStep:
        """Append one play event and update latent state for the active episode."""
        if self.current_episode is None:
            raise RuntimeError("No active episode. Call start_epoch(...) first.")
        if player not in (1, 2, 3, 4):
            raise ValueError("player must be one of 1, 2, 3, 4")
        if trick_index < 0:
            raise ValueError("trick_index must be >= 0")
        if not strategy_answers:
            raise ValueError("strategy_answers must be explicitly provided on every card step.")

        incoming_answers = [float(value) for value in strategy_answers]
        incoming_hash = self._strategy_answers_hash(incoming_answers)
        if incoming_hash != self.current_episode.strategy_answers_hash:
            raise RuntimeError(
                "Strategy declaration changed mid-epoch. "
                "Split the epoch before recording additional card-play steps."
            )

        context = context_features or {}
        clean_card = self._normalize_card(card)
        card_token = self._token_for_card(clean_card)
        is_opponent_play = self._is_opponent(player)
        legal_card_tokens = [self._token_for_card(c) for c in (legal_cards or [])]

        latent_before = list(self.current_episode.latent_state)
        latent_after = self._update_latent(
            prev_latent=latent_before,
            card_token=card_token,
            player=player,
            is_opponent_play=is_opponent_play,
            context_features=context,
        )

        step = CardStep(
            step_index=len(self.current_episode.card_steps),
            trick_index=trick_index,
            player=player,
            card=clean_card,
            card_token=card_token,
            is_opponent_play=is_opponent_play,
            strategy_answers_hash=incoming_hash,
            strategy_answers=incoming_answers,
            context_features={k: float(v) for k, v in context.items()},
            legal_card_tokens=legal_card_tokens,
            latent_before=latent_before,
            latent_after=latent_after,
        )
        self.current_episode.card_steps.append(step)
        self.current_episode.latent_state = list(latent_after)
        self.current_episode.latent_trajectory.append(list(latent_after))
        return step

    # Function: _build_training_record.
    def _build_training_record(self, episode: CardPlayEpisode) -> Dict[str, object]:
        encoded_sequence = [
            {
                "step": s.step_index,
                "trick_index": s.trick_index,
                "card_token": s.card_token,
                "player": s.player,
                "player_token": s.player - 1,
                "is_opponent_play": int(s.is_opponent_play),
                "strategy_answers_hash": s.strategy_answers_hash,
                "strategy_answers": s.strategy_answers,
                "context_features": s.context_features,
                "legal_card_tokens": s.legal_card_tokens,
            }
            for s in episode.card_steps
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
            "bid_history_context": episode.bid_history_context,
            "encoded_sequence": encoded_sequence,
            "latent_trajectory": episode.latent_trajectory,
            "final_latent_summary": episode.latent_state,
            "terminal": {
                "observed_declarer_tricks": episode.observed_declarer_tricks,
                "observed_score": episode.observed_score,
                "double_dummy_target": episode.double_dummy_target,
                "reward_components": episode.reward_components,
            },
        }

    # Function: close_hand_and_learn.
    def close_hand_and_learn(
        self,
        observed_declarer_tricks: int,
        observed_score: float,
        double_dummy_target: Dict[str, float],
        reward_components: Optional[Dict[str, float]] = None,
    ) -> Dict[str, object]:
        """Finalize card-play episode and apply delayed learning update.

        Expected ``double_dummy_target`` keys include:
        - ``expected_tricks``
        - ``projected_score``

        Reward defaults are generated from deltas against those targets.
        """
        if self.current_episode is None:
            raise RuntimeError("No active episode to close.")

        episode = self.current_episode
        episode.observed_declarer_tricks = int(observed_declarer_tricks)
        episode.observed_score = float(observed_score)
        episode.double_dummy_target = {k: float(v) for k, v in double_dummy_target.items()}

        dd_tricks = float(episode.double_dummy_target.get("expected_tricks", 0.0))
        dd_score = float(episode.double_dummy_target.get("projected_score", 0.0))
        trick_delta_vs_dd = float(observed_declarer_tricks) - dd_tricks
        score_delta_vs_dd = float(observed_score) - dd_score

        computed_reward_components: Dict[str, float] = {
            "trick_delta_vs_double_dummy": trick_delta_vs_dd,
            "score_delta_vs_double_dummy": score_delta_vs_dd,
            "within_one_trick_of_dd": 1.0 if trick_delta_vs_dd >= -1.0 else 0.0,
        }
        if reward_components:
            computed_reward_components.update({k: float(v) for k, v in reward_components.items()})

        episode.reward_components = computed_reward_components
        total_reward = sum(episode.reward_components.values())

        record = self._build_training_record(episode)
        record["terminal"]["total_reward"] = total_reward

        self.training_records.append(record)
        self.current_episode = None
        return record


# Backward-friendly alias.
RunnerCardPlayModel = CardPlayEpisodeRunner
