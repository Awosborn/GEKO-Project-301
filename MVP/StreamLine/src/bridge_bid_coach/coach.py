"""High-level bridge bidding coach behaviour (SFT model backend)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from .bid_ranker import top_candidate_bids, user_bid_in_top_n
from .bridge_rules import calculate_hcp
from .inference import extract_json_object, generate_text
from .prompt_builder import build_messages
from .schemas import CoachResponse, GameState
from .utils import pydantic_model_dump, pydantic_model_validate

logger = logging.getLogger(__name__)

# Maximum generation attempts before using the deterministic fallback
_MAX_RETRIES = 3


def load_game_state(path: str | Path) -> GameState:
    """Load and validate a game-state JSON file."""
    state_path = Path(path)
    if not state_path.exists():
        raise FileNotFoundError(f"Game-state file not found: {state_path}")
    data = json.loads(state_path.read_text(encoding="utf-8"))
    return pydantic_model_validate(GameState, data)


def reasonable_bid_response(state: GameState) -> CoachResponse:
    """Return a canned response when the user's bid is already in the top three."""
    top_3 = top_candidate_bids(state.top_3_model_bids, 3)
    return CoachResponse(
        user_bid=state.user_bid,
        verdict="reasonable",
        recommended_bid=state.user_bid,
        top_3_bids=top_3,
        explanation="The selected bid is among the model's top three candidates.",
        convention_card_reasoning="No correction is needed from the current top-three ranking.",
        risk_of_user_bid="Normal bidding risk for this auction.",
        partner_likely_inference="Partner can treat the bid as a plausible action in the current context.",
        confidence=0.75,
        raw_model_text=None,
    )


def model_failure_response(
    state: GameState, raw_model_text: Optional[str] = None
) -> CoachResponse:
    """Return an explicit model-failure response with raw model output."""
    top_3 = top_candidate_bids(state.top_3_model_bids, 3)
    return CoachResponse(
        user_bid=state.user_bid,
        verdict="model_error",
        recommended_bid=None,
        top_3_bids=top_3,
        explanation=(
            "Model output could not be parsed as valid coach JSON. Showing raw model text for debugging."
        ),
        convention_card_reasoning=(
            "LLM output schema validation failed."
        ),
        risk_of_user_bid=(
            "No deterministic recommendation is returned in this mode."
        ),
        partner_likely_inference=(
            "Inspect raw_model_text and model prompt/configuration."
        ),
        confidence=0.55,
        raw_model_text=raw_model_text,
    )


def _parse_and_validate_response(
    raw_text: str, state: GameState
) -> Optional[CoachResponse]:
    """Try to parse *raw_text* as a CoachResponse; return None on any failure."""
    parsed = extract_json_object(raw_text)
    if parsed is None:
        return None

    # Fill in fields the model sometimes omits
    parsed.setdefault("user_bid", state.user_bid)
    parsed.setdefault("top_3_bids", top_candidate_bids(state.top_3_model_bids, 3))

    try:
        return pydantic_model_validate(CoachResponse, parsed)
    except Exception as exc:
        logger.debug("CoachResponse validation failed: %s", exc)
        return None


def _retry_message(attempt: int) -> str:
    """Return an escalating reminder appended to the user message on retries."""
    if attempt == 1:
        return (
            "\n\nIMPORTANT: Your previous response was not valid JSON. "
            "Output ONLY the JSON object — no other text."
        )
    return (
        "\n\nCRITICAL: Still not valid JSON. Output the raw JSON object only, "
        "starting with { and ending with }. No markdown, no prose."
    )


_HCP_PATTERN = re.compile(r"(\d+)(\s*HCP)", re.IGNORECASE)
_HCP_TEXT_FIELDS = (
    "explanation",
    "convention_card_reasoning",
    "risk_of_user_bid",
    "partner_likely_inference",
)


def _correct_hcp(response: CoachResponse, hand: str) -> CoachResponse:
    """Override any wrong HCP value the model wrote with the calculated truth.

    Scans all free-text fields for patterns like '14 HCP' or '10HCP'.
    Any number that does not match the actual count is replaced in-place.
    Returns the original response unchanged if the hand is unknown or all
    values are already correct.
    """
    if not hand:
        return response

    true_hcp = calculate_hcp(hand)
    data = pydantic_model_dump(response)
    changed = False

    for field in _HCP_TEXT_FIELDS:
        text = data.get(field)
        if not isinstance(text, str):
            continue
        new_text = _HCP_PATTERN.sub(
            lambda m: (
                f"{true_hcp}{m.group(2)}"
                if int(m.group(1)) != true_hcp
                else m.group(0)
            ),
            text,
        )
        if new_text != text:
            changed = True
            data[field] = new_text

    if changed:
        logger.debug("HCP correction applied: calculated=%d", true_hcp)
        return pydantic_model_validate(CoachResponse, data)
    return response


def coach_game_state(
    state: GameState,
    *,
    model_dir: Optional[str | Path] = None,
    system_prompt: Optional[str] = None,
    device: str = "auto",
    max_new_tokens: int = 40,
) -> CoachResponse:
    """Coach one game state with the SFT model.

    The model is only called when the user's bid is NOT in the top three.
    Up to _MAX_RETRIES generation attempts are made; each failed attempt appends
    a stronger JSON-only reminder to the user message.  If all attempts fail,
    the deterministic fallback is returned.
    """
    if user_bid_in_top_n(state.user_bid, state.top_3_model_bids, 3):
        return reasonable_bid_response(state)

    if model_dir is None:
        raise RuntimeError("model_dir is required for LLM coaching")

    messages = build_messages(state, system_prompt=system_prompt)
    last_raw: Optional[str] = None

    for attempt in range(_MAX_RETRIES):
        # On retries, append a JSON reminder to the user message
        attempt_messages = list(messages)
        if attempt > 0:
            reminder = _retry_message(attempt)
            last_user = dict(attempt_messages[-1])
            last_user["content"] = last_user["content"] + reminder
            attempt_messages = attempt_messages[:-1] + [last_user]

        try:
            raw_text = generate_text(
                attempt_messages,
                model_dir=model_dir,
                device=device,
                max_new_tokens=max_new_tokens,
            )
        except Exception as exc:
            logger.warning("Generation error on attempt %d: %s", attempt + 1, exc)
            last_raw = f"[generation_error] {exc}"
            continue

        last_raw = raw_text
        response = _parse_and_validate_response(raw_text, state)
        if response is not None:
            return _correct_hcp(response, state.hand or "")

        logger.debug(
            "Attempt %d/%d: invalid JSON output — %r", attempt + 1, _MAX_RETRIES, raw_text[:120]
        )

    logger.warning("All %d attempts failed; returning model_failure response.", _MAX_RETRIES)
    return model_failure_response(state, last_raw)
