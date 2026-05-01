"""Build prompts and chat messages for bridge bidding coach inference."""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from .schemas import GameState
from .utils import pydantic_model_dump

# ── SFT system prompt ────────────────────────────────────────────────────────
# Must match the prompt injected during SFT training (sft/train_sft.py).
# Also written to config/system_prompt.md for reference.
SFT_SYSTEM_PROMPT = """You are a bridge bidding coach. Your ONLY output is a single valid JSON object — no text before or after it, no markdown code blocks, no explanation outside the JSON.

Output schema (all keys required):
{
  "user_bid": "<string>",
  "verdict": "improve",
  "recommended_bid": "<string — must be in legal_bids>",
  "top_3_bids": ["<bid1>", "<bid2>", "<bid3>"],
  "explanation": "<string>",
  "convention_card_reasoning": "<string>",
  "risk_of_user_bid": "<string>",
  "partner_likely_inference": "<string>",
  "confidence": <float 0.0-1.0>
}

Rules:
- verdict is always "improve" (this coach is only called when the user bid is outside top-3)
- top_3_bids must contain exactly 3 bid strings
- recommended_bid must be one of the values in the legal_bids array from the input
- confidence must be a number between 0.0 and 1.0
- Output the JSON object and nothing else"""


def build_messages(
    state: GameState,
    system_prompt: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Build the chat messages list for SFT model inference.

    The user message is the raw GameState JSON — exactly the format the model
    was trained on.  Extra runtime-only fields (raw_model_text, etc.) are never
    present because they come from CoachResponse, not GameState.
    """
    system = (system_prompt or SFT_SYSTEM_PROMPT).strip()
    user_content = json.dumps(pydantic_model_dump(state), ensure_ascii=False, separators=(",", ":"))
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]


# ── Legacy text-prompt builder (kept for reference / testing) ────────────────

def _format_auction(state: GameState) -> str:
    if not state.auction_history:
        return "None"
    parts = []
    for call in state.auction_history:
        seat = call.seat or "unknown"
        text = f"{seat}: {call.call}"
        if call.alert:
            text += " (alert)"
        if call.explanation:
            text += f" - {call.explanation}"
        parts.append(text)
    return "; ".join(parts)


def build_prompt(state: GameState, system_prompt: Optional[str] = None) -> str:
    """Legacy text-format prompt (kept for backward compatibility with tests)."""
    from .bid_ranker import top_candidate_bids

    system = (system_prompt or SFT_SYSTEM_PROMPT).strip()
    convention_card = json.dumps(pydantic_model_dump(state.convention_card), ensure_ascii=False)
    alerts = json.dumps(state.alerts, ensure_ascii=False)
    explanations = json.dumps(state.explanations, ensure_ascii=False)
    candidates = top_candidate_bids(state.top_3_model_bids, 3)

    return f"""[SYSTEM]
{system}

[GAME_STATE]
Dealer: {state.dealer}
Vulnerability: {state.vulnerability}
Scoring: {state.scoring or "unspecified"}
Current seat: {state.current_seat}
Hand: {state.hand or "unknown"}
Auction so far: {_format_auction(state)}
Legal calls: {", ".join(state.legal_bids)}
Convention card: {convention_card}
Alerts/explanations: alerts={alerts}; explanations={explanations}

[MODEL_CANDIDATES]
Top 3 bids:
1. {candidates[0] if len(candidates) > 0 else ""}
2. {candidates[1] if len(candidates) > 1 else ""}
3. {candidates[2] if len(candidates) > 2 else ""}

[USER_ACTION]
User selected: {state.user_bid}

[TASK]
The user selected a bid outside the top 3 choices. Return the best improvement as valid JSON.

[OUTPUT_FORMAT]
Return JSON with:
{{
  "verdict": "...",
  "recommended_bid": "...",
  "top_3_bids": [],
  "explanation": "...",
  "convention_card_reasoning": "...",
  "risk_of_user_bid": "...",
  "partner_likely_inference": "...",
  "confidence": 0.0
}}
"""
