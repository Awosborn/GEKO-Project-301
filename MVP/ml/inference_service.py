"""Inference service utilities and API routes for next-bid and next-card prediction."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from .masks import bid_legality_mask, card_legality_mask
from .tokenizer import Tokenizer


@dataclass
class InferenceArtifacts:
    """Loaded model/tokenizer artifacts needed for prediction."""

    tokenizer: Tokenizer
    label_vocab: List[str]
    majority_label_id: int | None
    transformer_state: Mapping[str, Any] | None

    @classmethod
    def from_model_dir(cls, model_dir: str | Path) -> "InferenceArtifacts":
        model_path = Path(model_dir)
        tokenizer_payload = json.loads((model_path / "tokenizer_artifact.json").read_text(encoding="utf-8"))
        tokenizer = Tokenizer(
            token_to_id={str(k): int(v) for k, v in tokenizer_payload["token_to_id"].items()},
            id_to_token={int(k): str(v) for k, v in tokenizer_payload["id_to_token"].items()},
        )

        label_payload = json.loads((model_path / "label_map.json").read_text(encoding="utf-8"))
        id_to_label_raw = label_payload["id_to_label"]
        label_vocab = [str(id_to_label_raw[str(idx)]) for idx in range(len(id_to_label_raw))]

        baseline_path = model_path / "baseline.json"
        majority_label_id: int | None = None
        if baseline_path.exists():
            baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
            majority = baseline_payload.get("majority_label_id")
            majority_label_id = int(majority) if majority is not None else None

        transformer_state: Mapping[str, Any] | None = None
        checkpoint_path = model_path / "checkpoint_best.pt"
        if checkpoint_path.exists():
            try:
                import torch

                checkpoint = torch.load(checkpoint_path, map_location="cpu")
                if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
                    transformer_state = checkpoint
            except Exception:
                transformer_state = None

        return cls(
            tokenizer=tokenizer,
            label_vocab=label_vocab,
            majority_label_id=majority_label_id,
            transformer_state=transformer_state,
        )

    def _transformer_probs(self, token_ids: List[int]) -> List[float]:
        import torch
        from torch import nn

        num_classes = len(self.label_vocab)
        vocab_size = max(self.tokenizer.token_to_id.values()) + 1

        class _TransformerClassifier(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                d_model = 64
                self.embed = nn.Embedding(vocab_size, d_model, padding_idx=0)
                encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=4, batch_first=True)
                self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=2)
                self.head = nn.Linear(d_model, num_classes)

            def forward(self, tokens: torch.Tensor) -> torch.Tensor:
                emb = self.embed(tokens)
                encoded = self.encoder(emb)
                pooled = encoded.mean(dim=1)
                return self.head(pooled)

        if self.transformer_state is None:
            raise RuntimeError("Transformer checkpoint unavailable.")

        model = _TransformerClassifier()
        model.load_state_dict(self.transformer_state["model_state_dict"])
        model.eval()
        x = torch.tensor([token_ids], dtype=torch.long)
        with torch.no_grad():
            logits = model(x)[0]
            probs = torch.softmax(logits, dim=0)
        return [float(v) for v in probs.tolist()]

    def predict_probs(self, token_ids: List[int]) -> List[float]:
        if self.transformer_state is not None:
            try:
                return self._transformer_probs(token_ids)
            except Exception:
                pass

        n_classes = len(self.label_vocab)
        majority_id = int(self.majority_label_id or 0)
        probs = [0.0] * n_classes
        if n_classes:
            probs[majority_id] = 1.0
        return probs


def _top_k(probabilities: Sequence[float], labels: Sequence[str], top_k: int) -> List[Dict[str, float | str]]:
    pairs = sorted(zip(labels, probabilities), key=lambda item: item[1], reverse=True)
    return [
        {"label": str(label), "probability": float(prob)}
        for label, prob in pairs[: max(1, top_k)]
    ]


def _masked_probs(probabilities: Sequence[float], mask: Sequence[float]) -> List[float]:
    legal = [math.isfinite(v) and float(v) >= 0.0 for v in mask]
    masked = [float(p) if is_legal else 0.0 for p, is_legal in zip(probabilities, legal)]
    total = sum(masked)
    if total > 0:
        return [p / total for p in masked]

    legal_count = sum(1 for is_legal in legal if is_legal)
    if legal_count == 0:
        return [0.0 for _ in probabilities]
    fallback = 1.0 / float(legal_count)
    return [fallback if is_legal else 0.0 for is_legal in legal]


def predict_bid(
    artifacts: InferenceArtifacts,
    *,
    seat_to_act: int,
    bid_prefix: Sequence[str],
    hand_cards: Sequence[str],
    top_k: int,
) -> Dict[str, object]:
    from .train_next_bid import _tokens_from_bid_row

    token_ids = artifacts.tokenizer.encode(
        _tokens_from_bid_row({"seat_to_act": seat_to_act, "bid_prefix": bid_prefix, "hand_cards": hand_cards})
    )
    raw_probs = artifacts.predict_probs(token_ids)
    mask = bid_legality_mask(artifacts.label_vocab, seat_to_act=seat_to_act, bid_prefix=bid_prefix)
    constrained_probs = _masked_probs(raw_probs, mask)
    return {
        "top_k_probabilities": _top_k(raw_probs, artifacts.label_vocab, top_k),
        "masked_top_k_probabilities": _top_k(constrained_probs, artifacts.label_vocab, top_k),
        "mask": [float(v) for v in mask],
    }


def predict_card(
    artifacts: InferenceArtifacts,
    *,
    seat_to_act: int,
    auction_bids: Sequence[str],
    play_prefix: Sequence[Mapping[str, object]],
    hand_cards: Sequence[str],
    trick_cards: Sequence[str],
    top_k: int,
) -> Dict[str, object]:
    from .train_next_card import _tokens_from_card_row

    token_ids = artifacts.tokenizer.encode(
        _tokens_from_card_row(
            {
                "seat_to_act": seat_to_act,
                "auction_bids": auction_bids,
                "play_prefix": list(play_prefix),
                "hand_cards": hand_cards,
            }
        )
    )
    raw_probs = artifacts.predict_probs(token_ids)
    mask = card_legality_mask(artifacts.label_vocab, hand_cards=hand_cards, trick_cards=trick_cards)
    constrained_probs = _masked_probs(raw_probs, mask)
    return {
        "top_k_probabilities": _top_k(raw_probs, artifacts.label_vocab, top_k),
        "masked_top_k_probabilities": _top_k(constrained_probs, artifacts.label_vocab, top_k),
        "mask": [float(v) for v in mask],
    }


def create_inference_app(model_bid_dir: str | Path, model_card_dir: str | Path):
    """Create a FastAPI app exposing /predict_bid and /predict_card routes."""
    try:
        from fastapi import FastAPI
        from pydantic import BaseModel, Field
    except ImportError as exc:  # pragma: no cover - exercised only when fastapi missing
        raise RuntimeError("FastAPI is required to serve inference endpoints.") from exc

    bid_artifacts = InferenceArtifacts.from_model_dir(model_bid_dir)
    card_artifacts = InferenceArtifacts.from_model_dir(model_card_dir)

    class PredictBidRequest(BaseModel):
        seat_to_act: int = Field(..., ge=1, le=4)
        bid_prefix: List[str] = Field(default_factory=list)
        hand_cards: List[str] = Field(default_factory=list)
        top_k: int = Field(default=3, ge=1, le=20)

    class PredictCardRequest(BaseModel):
        seat_to_act: int = Field(..., ge=1, le=4)
        auction_bids: List[str] = Field(default_factory=list)
        play_prefix: List[Dict[str, object]] = Field(default_factory=list)
        hand_cards: List[str] = Field(default_factory=list)
        trick_cards: List[str] = Field(default_factory=list)
        top_k: int = Field(default=3, ge=1, le=20)

    app = FastAPI(title="GEKO Inference Service")

    @app.post("/predict_bid")
    def predict_bid_route(payload: PredictBidRequest) -> Dict[str, object]:
        return predict_bid(
            bid_artifacts,
            seat_to_act=payload.seat_to_act,
            bid_prefix=payload.bid_prefix,
            hand_cards=payload.hand_cards,
            top_k=payload.top_k,
        )

    @app.post("/predict_card")
    def predict_card_route(payload: PredictCardRequest) -> Dict[str, object]:
        return predict_card(
            card_artifacts,
            seat_to_act=payload.seat_to_act,
            auction_bids=payload.auction_bids,
            play_prefix=payload.play_prefix,
            hand_cards=payload.hand_cards,
            trick_cards=payload.trick_cards,
            top_k=payload.top_k,
        )

    return app
