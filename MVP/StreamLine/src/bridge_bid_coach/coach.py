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

# Maximum generation attempts before returning model_failure
_MAX_RETRIES = 3

_REQUIRED_LLM_TEXT_FIELDS = ("explanation", "convention_card_reasoning")
_LLM_TEXT_FIELD_ALIASES = {
    "explanation": ("explanation", "explination"),
    "convention_card_reasoning": (
        "convention_card_reasoning",
        "convention_card_reasioning",
        "convention_card_reasiong",
        "convention card reasoning",
    ),
}
_LLM_TEXT_FIELD_STOPS = (
    "alerts",
    "auction_history",
    "confidence",
    "convention_card",
    "convention_card_reasoning",
    "convention_card_reasioning",
    "convention_card_reasiong",
    "convention card reasoning",
    "current_seat",
    "dealer",
    "explanation",
    "explination",
    "hand",
    "hand_shape",
    "known_cards",
    "legal_bids",
    "partner_likely_inference",
    "raw_model_text",
    "recommended_bid",
    "risk_of_user_bid",
    "top_3_bids",
    "top_3_model_bids",
    "user_bid",
    "verdict",
    "vulnerability",
)
_LLM_PLACEHOLDER_TEXTS = {
    "Suggested improvement based on legal bids and model candidates.",
    "Recommendation recovered from partial model output.",
    "Model output could not be parsed as valid coach JSON. Showing raw model text for debugging.",
    "LLM output schema validation failed.",
}
_RESPONSE_KEYS = {
    "confidence",
    "convention_card_reasoning",
    "explanation",
    "partner_likely_inference",
    "raw_model_text",
    "recommended",
    "recommended_bid",
    "risk_of_user_bid",
    "top_3_bids",
    "user_bid",
    "verdict",
}


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
            "No recommendation is returned in this mode."
        ),
        partner_likely_inference=(
            "Inspect raw_model_text and model prompt/configuration."
        ),
        confidence=0.55,
        raw_model_text=raw_model_text,
    )




def _clean_llm_text(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t\r\n,\"'")


def _usable_llm_text(value: object) -> str:
    text = _clean_llm_text(value)
    return "" if text in _LLM_PLACEHOLDER_TEXTS else text


def _llm_alias_pattern(field: str) -> str:
    return "|".join(re.escape(alias) for alias in _LLM_TEXT_FIELD_ALIASES.get(field, (field,)))


def _llm_field_key_pattern(field: str, separator: str = r"[:=]") -> str:
    return rf'["\']?(?:{_llm_alias_pattern(field)})["\']?\s*{separator}'


def _extract_json_string_field(raw_text: str, field: str) -> Optional[str]:
    decoder = json.JSONDecoder()
    key_re = re.compile(_llm_field_key_pattern(field, ":"), re.IGNORECASE)
    for match in key_re.finditer(raw_text):
        index = match.end()
        while index < len(raw_text) and raw_text[index].isspace():
            index += 1
        if index >= len(raw_text):
            continue
        try:
            parsed, _ = decoder.raw_decode(raw_text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, str):
            return parsed
    return None


def _extract_quoted_text_field(raw_text: str, field: str) -> Optional[str]:
    key_re = re.compile(rf'{_llm_field_key_pattern(field)}\s*(["\'])', re.IGNORECASE)
    for match in key_re.finditer(raw_text):
        quote = match.group(1)
        chars: list[str] = []
        escaped = False
        for ch in raw_text[match.end():]:
            if escaped:
                chars.append(ch)
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                value = _usable_llm_text("".join(chars))
                if value:
                    return value
                break
            else:
                chars.append(ch)
    return None


def _extract_unquoted_text_field(raw_text: str, field: str) -> Optional[str]:
    key_re = re.compile(rf'{_llm_field_key_pattern(field)}\s*', re.IGNORECASE)
    stop_pattern = "|".join(re.escape(key) for key in _LLM_TEXT_FIELD_STOPS)
    stop_re = re.compile(rf',?\s*["\']?(?:{stop_pattern})["\']?\s*[:=]', re.IGNORECASE)

    for match in key_re.finditer(raw_text):
        start = match.end()
        stop = stop_re.search(raw_text, start)
        end = stop.start() if stop else len(raw_text)
        value = _usable_llm_text(raw_text[start:end].strip("{}[] \t\r\n,\"'"))
        if value:
            return value
    return None


def _extract_llm_text_field(raw_text: str, field: str) -> Optional[str]:
    return (
        _extract_json_string_field(raw_text, field)
        or _extract_quoted_text_field(raw_text, field)
        or _extract_unquoted_text_field(raw_text, field)
    )


def _parse_and_validate_response(
    raw_text: str, state: GameState
) -> Optional[CoachResponse]:
    """Try to parse *raw_text* as a CoachResponse; return None on any failure."""
    parsed = extract_json_object(raw_text)
    if parsed is None:
        parsed = {}
    elif not any(key in parsed for key in _RESPONSE_KEYS):
        logger.debug("Ignoring non-response JSON fragment in model output: %s", sorted(parsed))
        parsed = {}

    # Fill in structural fields the model sometimes omits. Do not invent the
    # two UI text fields; those must come from the model text itself.
    parsed.setdefault("user_bid", state.user_bid)
    parsed.setdefault("top_3_bids", top_candidate_bids(state.top_3_model_bids, 3))
    parsed.setdefault("raw_model_text", raw_text)
    parsed.setdefault("verdict", "incorrect")
    parsed.setdefault("recommended_bid", _recover_recommended_bid(raw_text, state))
    parsed.setdefault(
        "risk_of_user_bid",
        "Current user bid appears weaker than the recovered recommendation.",
    )
    parsed.setdefault(
        "partner_likely_inference",
        "Partner likely expects a call aligned with the recovered recommendation.",
    )
    parsed.setdefault("confidence", 0.55)
    # Common alias normalization from loosely formatted outputs.
    if "recommended" in parsed and "recommended_bid" not in parsed:
        parsed["recommended_bid"] = parsed.get("recommended")
    if "reasoning" in parsed and "convention_card_reasoning" not in parsed:
        parsed["convention_card_reasoning"] = parsed.get("reasoning")

    for field in _REQUIRED_LLM_TEXT_FIELDS:
        current = _usable_llm_text(parsed.get(field))
        recovered = _extract_llm_text_field(raw_text, field)
        if recovered:
            parsed[field] = recovered
        elif current:
            parsed[field] = current
        else:
            logger.debug("Model output missing required text field %s; retrying.", field)
            return None

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
_RECOVERY_BID_PATTERN = re.compile(
    r"\b(?:[1-7](?:C|D|H|S|NT)|PASS|DOUBLE|REDOUBLE|X|XX|P)\b", re.IGNORECASE
)
_HCP_TEXT_FIELDS = (
    "explanation",
    "convention_card_reasoning",
    "risk_of_user_bid",
    "partner_likely_inference",
)


def _recover_recommended_bid(raw_text: str, state: GameState) -> Optional[str]:
    """Recover a likely recommended bid when the model omits the schema field."""
    legal = [str(b) for b in state.legal_bids if isinstance(b, str)]
    if legal:
        legal_set = {b.upper(): b for b in legal}
        for token in _RECOVERY_BID_PATTERN.findall(raw_text.upper()):
            norm = {"P": "PASS", "X": "DOUBLE", "XX": "REDOUBLE"}.get(token, token)
            if norm in legal_set:
                return legal_set[norm]

    top_3 = top_candidate_bids(state.top_3_model_bids, 3)
    for bid in top_3:
        if not legal or bid in legal:
            return bid
    return legal[0] if legal else None


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
    max_new_tokens: int = 220,
    use_llm: bool = True,
) -> CoachResponse:
    """Coach one game state with the SFT model.

    The model is only called when the user's bid is NOT in the top three.
    Up to _MAX_RETRIES generation attempts are made; each failed attempt appends
    a stronger JSON-only reminder to the user message. If all attempts fail,
    a model_failure response is returned.
    """
    if user_bid_in_top_n(state.user_bid, state.top_3_model_bids, 3):
        return reasonable_bid_response(state)

    if not use_llm:
        raise RuntimeError("Deterministic fallback is disabled; set use_llm=True.")

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
