#!/usr/bin/env python3
"""Serve bridge UI and expose /api/coach backed by StreamLine model."""
from __future__ import annotations

import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STREAMLINE_SRC = ROOT.parent / "StreamLine" / "src"
STREAMLINE_MODEL = ROOT.parent / "StreamLine" / "model"
if str(STREAMLINE_SRC) not in sys.path:
    sys.path.insert(0, str(STREAMLINE_SRC))

from bridge_bid_coach.coach import coach_game_state  # noqa: E402
from bridge_bid_coach.schemas import AuctionCall, GameState  # noqa: E402


class BridgeUIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path != "/api/coach":
            self.send_error(404, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            top3 = payload.get("top3", [])
            auction_text = (payload.get("auction") or "").strip()
            auction_history = [
                AuctionCall(call=call)
                for call in auction_text.split()
                if call
            ]

            state = GameState(
                dealer=payload.get("dealer", "north"),
                vulnerability=payload.get("vulnerability", "none"),
                current_seat=payload.get("seat", "south"),
                user_bid=payload.get("userBid", "Pass"),
                top_3_model_bids=top3,
                hand=payload.get("hand", ""),
                auction_history=auction_history,
                legal_bids=[],
            )
            llm_response = coach_game_state(state, model_dir=STREAMLINE_MODEL)
            body = {
                "verdict": llm_response.verdict,
                "recommendedBid": llm_response.recommended_bid or (top3[0] if top3 else "Pass"),
                "explanation": llm_response.explanation,
            }
            self._send_json(200, body)
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": str(exc)})

    def _send_json(self, status: int, payload: dict):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), BridgeUIHandler)
    print(f"Bridge UI server running on http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
