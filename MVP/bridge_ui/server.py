#!/usr/bin/env python3
"""Serve bridge UI and expose /api/coach (StreamLine), /api/bid and /api/card (GEKO)."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
STREAMLINE_SRC = ROOT.parent / "StreamLine" / "src"
STREAMLINE_MODEL = ROOT.parent / "StreamLine" / "model"
GEKO_ROOT = ROOT.parent / "GEKO_PLAYABLE_MODEL"

for _p in (str(STREAMLINE_SRC), str(GEKO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bridge_bid_coach.bridge_rules import normalize_call  # noqa: E402
from bridge_bid_coach.coach import coach_game_state  # noqa: E402
from bridge_bid_coach.inference import extract_json_object  # noqa: E402
from bridge_bid_coach.schemas import AuctionCall, GameState  # noqa: E402

# ── Translation helpers ───────────────────────────────────────────────────────

_SEAT_TO_INT: Dict[str, int] = {"north": 1, "east": 2, "south": 3, "west": 4}
_CONTRACT_RE = re.compile(r"^([1-7])(C|D|H|S|NT)$", re.IGNORECASE)


def _vuln_dict(vuln: str) -> Dict[str, bool]:
    if vuln == "NS":
        return {"1": True, "2": False, "3": True, "4": False}
    if vuln == "EW":
        return {"1": False, "2": True, "3": False, "4": True}
    if vuln == "both":
        return {"1": True, "2": True, "3": True, "4": True}
    return {"1": False, "2": False, "3": False, "4": False}


def _ui_bid_to_geko(bid: str) -> str:
    """Convert StreamLine-normalised bid to GEKO model format ('Pass'→'P', 'Double'→'X')."""
    upper = bid.upper()
    if upper in {"PASS", "P"}:
        return "P"
    if upper in {"DOUBLE", "X", "DBL"}:
        return "X"
    if upper in {"REDOUBLE", "XX", "RDBL"}:
        return "XX"
    return upper


def _parse_hand_text(hand_text: str) -> List[str]:
    """Parse 'S AKQ H 94 D T82 C K73' into GEKO card list like ['AS','KS','9H','10D',...]."""
    cards: List[str] = []
    suit: Optional[str] = None
    for token in hand_text.split():
        if token in ("S", "H", "D", "C"):
            suit = token
        elif suit is not None:
            for ch in token:
                rank = "10" if ch == "T" else ch
                cards.append(f"{rank}{suit}")
    return cards


def _normalize_card_geko(card: object) -> str:
    """Normalise a UI card string to GEKO format ('TS' → '10S')."""
    token = str(card or "").strip().upper()
    if not token:
        return "UNK"
    if len(token) == 2 and token[0] == "T":
        return f"10{token[1]}"
    return token


def _geko_card_to_ui(card: str) -> str:
    """Convert GEKO card format back to UI format ('10S' → 'TS')."""
    if isinstance(card, str) and card.startswith("10") and len(card) == 3:
        return "T" + card[2]
    return str(card or "")


_REVIEW_FIELD_LABELS = {
    "explanation": "Explanation",
    "convention_card_reasoning": "Convention card reasoning",
}
_REVIEW_FIELD_ALIASES = {
    "explanation": ("explanation", "explination"),
    "convention_card_reasoning": (
        "convention_card_reasoning",
        "convention_card_reasioning",
        "convention_card_reasiong",
        "convention card reasoning",
    ),
}
_RAW_FIELD_STOPS = (
    "alerts",
    "auction_history",
    "convention_card",
    "user_bid",
    "verdict",
    "recommended_bid",
    "top_3_bids",
    "top_3_model_bids",
    "explanation",
    "explination",
    "convention_card_reasoning",
    "convention_card_reasioning",
    "convention_card_reasiong",
    "convention card reasoning",
    "dealer",
    "hand",
    "hand_shape",
    "known_cards",
    "legal_bids",
    "risk_of_user_bid",
    "partner_likely_inference",
    "confidence",
    "current_seat",
    "raw_model_text",
    "vulnerability",
)


def _clean_review_text(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t\r\n,")


def _alias_pattern(field: str) -> str:
    return "|".join(re.escape(alias) for alias in _REVIEW_FIELD_ALIASES.get(field, (field,)))


def _field_key_pattern(field: str, separator: str = r"[:=]") -> str:
    return rf'["\']?(?:{_alias_pattern(field)})["\']?\s*{separator}'


def _extract_json_string_field(raw_text: str, field: str) -> Optional[str]:
    """Extract one string field from loose JSON-ish model text."""
    decoder = json.JSONDecoder()
    key_re = re.compile(_field_key_pattern(field, ":"), re.IGNORECASE)
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
    """Extract a quoted field value without requiring valid JSON."""
    key_re = re.compile(rf'{_field_key_pattern(field)}\s*(["\'])', re.IGNORECASE)
    for match in key_re.finditer(raw_text):
        quote = match.group(1)
        chars: List[str] = []
        escaped = False
        for ch in raw_text[match.end():]:
            if escaped:
                chars.append(ch)
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                value = _clean_review_text("".join(chars))
                if value:
                    return value
                break
            else:
                chars.append(ch)
    return None


def _extract_unquoted_text_field(raw_text: str, field: str) -> Optional[str]:
    """Extract a field up to the next known JSON-ish key."""
    key_re = re.compile(rf'{_field_key_pattern(field)}\s*', re.IGNORECASE)
    stop_pattern = "|".join(re.escape(key) for key in _RAW_FIELD_STOPS)
    stop_re = re.compile(rf',?\s*["\']?(?:{stop_pattern})["\']?\s*[:=]', re.IGNORECASE)

    for match in key_re.finditer(raw_text):
        start = match.end()
        stop = stop_re.search(raw_text, start)
        end = stop.start() if stop else len(raw_text)
        value = raw_text[start:end].strip().strip("{}[] \t\r\n,\"'")
        value = _clean_review_text(value)
        if value:
            return value
    return None


def _extract_text_field(raw_text: str, field: str) -> Optional[str]:
    return (
        _extract_json_string_field(raw_text, field)
        or _extract_quoted_text_field(raw_text, field)
        or _extract_unquoted_text_field(raw_text, field)
    )


def _extract_review_fields(raw_text: Optional[str]) -> Dict[str, str]:
    """Pull only the user-facing review fields from raw model output."""
    if not raw_text:
        return {}

    fields: Dict[str, str] = {}
    parsed = extract_json_object(raw_text)
    if isinstance(parsed, dict):
        for field in _REVIEW_FIELD_LABELS:
            value = _clean_review_text(parsed.get(field))
            if value:
                fields[field] = value

    for field in _REVIEW_FIELD_LABELS:
        if field not in fields:
            value = _clean_review_text(_extract_text_field(raw_text, field))
            if value:
                fields[field] = value

    return fields


def _build_review_text(
    explanation: object,
    convention_card_reasoning: object,
    raw_model_text: Optional[str],
    verdict: str,
) -> Dict[str, str]:
    """Return cleaned explanation fields and a display string for the UI."""
    fields = {
        "explanation": _clean_review_text(explanation),
        "convention_card_reasoning": _clean_review_text(convention_card_reasoning),
    }
    raw_fields = _extract_review_fields(raw_model_text)

    for field, value in raw_fields.items():
        fields[field] = value

    review_parts = [
        f"{label}: {fields[field]}"
        for field, label in _REVIEW_FIELD_LABELS.items()
        if fields.get(field)
    ]
    fields["review_text"] = "\n\n".join(review_parts) or "Not available"
    return fields


def _select_geko_recommended_bid(
    payload_recommended: object,
    top3: List[str],
    legal_bids: List[str],
) -> Optional[str]:
    """Use GEKO's bid, not the LLM's, as the displayed proper bid."""
    legal_set = {bid.upper() for bid in legal_bids}
    candidates = [payload_recommended, *(top3 or [])]
    for candidate in candidates:
        bid = normalize_call(str(candidate or "").strip())
        if bid and (not legal_set or bid.upper() in legal_set):
            return bid
    return None


# ── GEKO model globals ────────────────────────────────────────────────────────

_geko_lock = threading.Lock()
_geko_loaded = False
_geko_bidding_model: Any = None
_geko_card_model: Any = None
_geko_strategy_answers: List[int] = []


def _ensure_geko_models() -> bool:
    global _geko_loaded, _geko_bidding_model, _geko_card_model, _geko_strategy_answers
    with _geko_lock:
        if _geko_loaded:
            return _geko_bidding_model is not None
        _geko_loaded = True
        try:
            from playable_bridge_ai import BiddingModel, strategy_answers_for_profile  # type: ignore
            from BEST_CARD_PLAY.best_card_play import BestCardPlayModel  # type: ignore
            _geko_bidding_model = BiddingModel()
            _geko_card_model = BestCardPlayModel(GEKO_ROOT / "BEST_CARD_PLAY" / "model")
            _geko_strategy_answers = strategy_answers_for_profile(1)
            logger.info("GEKO bidding and card-play models loaded.")
            return True
        except Exception as exc:
            logger.warning("GEKO models unavailable: %s", exc)
            return False


# ── HTTP handler ──────────────────────────────────────────────────────────────

class BridgeUIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_POST(self):
        routes: Dict[str, Any] = {
            "/api/coach": self._handle_coach,
            "/api/bid": self._handle_bid,
            "/api/card": self._handle_card,
        }
        handler = routes.get(self.path)
        if handler is None:
            self.send_error(404, "Not found")
            return
        try:
            payload = self._read_body()
            handler(payload)
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": str(exc)})

    # ── /api/coach ────────────────────────────────────────────────────────────

    def _handle_coach(self, payload: dict) -> None:
        top3 = payload.get("top3", [])
        if isinstance(top3, list):
            top3 = [normalize_call(str(b)) for b in top3 if str(b).strip()]
        else:
            top3 = []
        legal_bids = payload.get("legalBids") or []
        if not isinstance(legal_bids, list):
            legal_bids = []
        legal_bids = [normalize_call(str(b)) for b in legal_bids if str(b).strip()]
        if not legal_bids:
            legal_bids = [b for b in top3 if isinstance(b, str) and b]
        auction_history_payload = payload.get("auctionHistory")
        auction_history: List[AuctionCall] = []
        if isinstance(auction_history_payload, list) and auction_history_payload:
            for entry in auction_history_payload:
                if isinstance(entry, dict):
                    call = normalize_call(str(entry.get("call", "")).strip())
                    if not call:
                        continue
                    seat = str(entry.get("seat", "")).strip().lower() or None
                    auction_history.append(AuctionCall(seat=seat, call=call))
        else:
            auction_text = (payload.get("auction") or "").strip()
            auction_history = [AuctionCall(call=normalize_call(c)) for c in auction_text.split() if c]

        state = GameState(
            dealer=payload.get("dealer", "north"),
            vulnerability=payload.get("vulnerability", "none"),
            current_seat=payload.get("seat", "south"),
            user_bid=normalize_call(payload.get("userBid", "Pass")),
            top_3_model_bids=top3,
            hand=payload.get("hand", ""),
            auction_history=auction_history,
            legal_bids=legal_bids,
        )
        llm_response = coach_game_state(state, model_dir=STREAMLINE_MODEL)
        geko_recommended_bid = _select_geko_recommended_bid(
            payload.get("recommendedBid"),
            top3,
            legal_bids,
        )
        review = _build_review_text(
            llm_response.explanation,
            llm_response.convention_card_reasoning,
            llm_response.raw_model_text,
            llm_response.verdict,
        )
        self._send_json(200, {
            "verdict": llm_response.verdict,
            "recommendedBid": geko_recommended_bid,
            "explanation": review["explanation"],
            "conventionCardReasoning": review["convention_card_reasoning"],
            "reviewText": review["review_text"],
        })

    # ── /api/bid ──────────────────────────────────────────────────────────────

    def _handle_bid(self, payload: dict) -> None:
        if not _ensure_geko_models():
            self._send_json(503, {"error": "GEKO bidding model unavailable"})
            return

        seat_int = _SEAT_TO_INT.get(str(payload.get("seat", "south")).lower(), 3)
        dealer_int = _SEAT_TO_INT.get(str(payload.get("dealer", "north")).lower(), 1)
        hand_cards = _parse_hand_text(str(payload.get("hand", "")))
        vuln_dict = _vuln_dict(str(payload.get("vulnerability", "none")))

        auction_raw = payload.get("auction", [])
        if isinstance(auction_raw, str):
            auction_raw = auction_raw.split()
        auction_geko = [_ui_bid_to_geko(normalize_call(c)) for c in auction_raw if str(c).strip()]

        result = _geko_bidding_model.predict(
            seat_to_act=seat_int,
            hand_cards=hand_cards,
            bid_prefix=auction_geko,
            dealer=dealer_int,
            vulnerability=vuln_dict,
            strategy_answers=_geko_strategy_answers,
            top_k=3,
        )

        recommended = normalize_call(str(result.get("recommended_bid", "P")))
        top3 = [normalize_call(str(row["bid"])) for row in result.get("top_k", [])[:3]]
        if not top3:
            top3 = [recommended]

        self._send_json(200, {"recommendedBid": recommended, "top3": top3})

    # ── /api/card ─────────────────────────────────────────────────────────────

    def _handle_card(self, payload: dict) -> None:
        if not _ensure_geko_models():
            self._send_json(503, {"error": "GEKO card-play model unavailable"})
            return

        seat_int = _SEAT_TO_INT.get(str(payload.get("seat", "south")).lower(), 3)

        hand_raw = payload.get("hand", [])
        if isinstance(hand_raw, str):
            hand_raw = hand_raw.split()
        hand_cards = [_normalize_card_geko(c) for c in hand_raw if _normalize_card_geko(c) != "UNK"]

        # Build play_prefix from completed tricks + current trick in progress
        play_prefix: List[Dict[str, Any]] = []
        for event in payload.get("playHistory", []):
            if isinstance(event, dict):
                player_int = _SEAT_TO_INT.get(str(event.get("seat", "")).lower())
                card = _normalize_card_geko(event.get("card", ""))
                if player_int and card != "UNK":
                    play_prefix.append({"player": player_int, "card": card})
        for event in payload.get("trick", []):
            if isinstance(event, dict):
                player_int = _SEAT_TO_INT.get(str(event.get("seat", "")).lower())
                card = _normalize_card_geko(event.get("card", ""))
                if player_int and card != "UNK":
                    play_prefix.append({"player": player_int, "card": card})

        auction_raw = payload.get("auction", [])
        if isinstance(auction_raw, str):
            auction_raw = auction_raw.split()
        auction_geko = [_ui_bid_to_geko(normalize_call(c)) for c in auction_raw if str(c).strip()]

        declarer_int = _SEAT_TO_INT.get(str(payload.get("declarer", "south")).lower(), 3)
        dummy_int = _SEAT_TO_INT.get(str(payload.get("dummy", "north")).lower(), 1)

        derived_contract: Dict[str, Any] = {}
        m = _CONTRACT_RE.match(str(payload.get("contract", "")).strip())
        if m:
            derived_contract = {
                "level": int(m.group(1)),
                "strain": m.group(2).upper(),
                "declarer": declarer_int,
                "dummy": dummy_int,
            }

        dummy_raw = payload.get("dummyHand", [])
        if isinstance(dummy_raw, str):
            dummy_raw = dummy_raw.split()
        visible_dummy = [_normalize_card_geko(c) for c in dummy_raw if _normalize_card_geko(c) != "UNK"]

        vuln_dict = _vuln_dict(str(payload.get("vulnerability", "none")))

        result = _geko_card_model.predict(
            seat_to_act=seat_int,
            hand_cards=hand_cards,
            play_prefix=play_prefix,
            auction_bids=auction_geko,
            derived_contract=derived_contract,
            visible_dummy_hand=visible_dummy,
            vulnerability=vuln_dict,
            top_k=3,
        )

        recommended = str(result.get("recommended_card") or "")
        self._send_json(200, {"recommendedCard": _geko_card_to_ui(recommended)})

    # ── helpers ───────────────────────────────────────────────────────────────

    def _send_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _ensure_geko_models()  # pre-load at startup so first request is not slow
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), BridgeUIHandler)
    print(f"Bridge UI server running on http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
