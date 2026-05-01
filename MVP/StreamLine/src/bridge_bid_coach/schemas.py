"""Pydantic schemas for bridge game states and coach responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class AuctionCall(BaseModel):
    """One call in an auction."""

    seat: Optional[str] = None
    call: str
    alert: bool = False
    explanation: Optional[str] = None


class CandidateBid(BaseModel):
    """A model candidate bid with an optional score."""

    bid: str
    score: Optional[float] = None
    explanation: Optional[str] = None


class ConventionCard(BaseModel):
    """Simplified convention-card fields used by the coach."""

    system_name: Optional[str] = None
    nt_range: Optional[str] = None
    one_nt_shape: Optional[str] = None
    five_card_majors: Optional[bool] = None
    two_over_one: Optional[bool] = None
    strong_2c: Optional[bool] = None
    stayman: Optional[bool] = None
    transfers: Optional[bool] = None
    weak_twos: Optional[bool] = None
    special_agreements: List[str] = Field(default_factory=list)


class GameState(BaseModel):
    """Complete bridge bidding context passed to the coach."""

    dealer: str
    vulnerability: str
    current_seat: str
    scoring: Optional[str] = None
    auction_history: List[AuctionCall] = Field(default_factory=list)
    legal_bids: List[str] = Field(default_factory=list)
    user_bid: str
    top_3_model_bids: List[Union[str, CandidateBid]] = Field(default_factory=list)
    hand: Optional[str] = None
    known_cards: Dict[str, Any] = Field(default_factory=dict)
    convention_card: ConventionCard = Field(default_factory=ConventionCard)
    alerts: List[Any] = Field(default_factory=list)
    explanations: List[Any] = Field(default_factory=list)


class CoachResponse(BaseModel):
    """JSON response suitable for a UI."""

    user_bid: str
    verdict: str
    recommended_bid: Optional[str] = None
    top_3_bids: List[str] = Field(default_factory=list)
    explanation: str
    convention_card_reasoning: Optional[str] = None
    risk_of_user_bid: Optional[str] = None
    partner_likely_inference: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_model_text: Optional[str] = None
