"""Plain-language coaching layer for bid and card decision deltas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


# Class: Coach.
class Coach:
    """Converts user-vs-model deltas into structured coaching feedback."""

    # Function: __init__.
    def __init__(self, strategy_profile: Optional[Sequence[int]] = None) -> None:
        self.strategy_profile = [int(value) for value in (strategy_profile or [])]

    # Function: explain_bid_decision.
    def explain_bid_decision(
        self,
        user_bid: str,
        recommended_bids: Sequence[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        chosen = user_bid.strip().upper()
        dd = context.get("double_dummy") or {}
        infractions = context.get("bid_infractions") or []

        matched = next((rec for rec in recommended_bids if str(rec.get("bid", "")).upper() == chosen), None)
        top = recommended_bids[0] if recommended_bids else None

        if matched is not None:
            mistake_type = "aligned_with_recommendation"
            severity = "low"
            suggested = chosen
            learning_tip = "Your call matches model priorities. Keep validating this against auction tempo and vulnerability."
            message = (
                f"Good choice: {chosen} matched model rank #{matched.get('rank', '?')} "
                f"(confidence {float(matched.get('confidence', 0.0)):.2f})."
            )
        else:
            mistake_type = "bid_delta"
            severity = self._severity_from_bid_gap(chosen, top)
            suggested = "" if top is None else str(top.get("bid", ""))
            learning_tip = self._bid_learning_tip(context=context, has_infraction=bool(infractions))
            if top is None:
                message = f"No model bid recommendation was available for {chosen}; review legality and partnership goals."
            else:
                message = (
                    f"Consider {top.get('bid')} next time: it ranked #1 with confidence "
                    f"{float(top.get('confidence', 0.0)):.2f} and better matches the model's auction plan."
                )

        if infractions:
            last_infraction = infractions[-1]
            message += (
                f" Rule note: {last_infraction.get('rule_type')} - "
                f"{last_infraction.get('message', 'Review system/legal constraints.')}"
            )
            if severity == "low":
                severity = "medium"

        dd_hint = ""
        if dd:
            dd_hint = (
                f" Double-dummy reference: {dd.get('contract', 'N/A')} by Player {dd.get('declarer', '?')} "
                f"for {dd.get('expected_tricks', '?')} tricks."
            )

        return {
            "decision": "bid",
            "player": context.get("player"),
            "user_action": chosen,
            "mistake_type": mistake_type,
            "severity": severity,
            "suggested_alternative": suggested,
            "learning_tip": learning_tip,
            "message": f"{message}{dd_hint}".strip(),
            "context_snapshot": {
                "auction_index": context.get("auction_index"),
                "strategy_profile_len": len(self.strategy_profile),
                "auction_history": context.get("auction_history", []),
            },
        }

    # Function: explain_card_play.
    def explain_card_play(
        self,
        user_card: str,
        recommended_cards: Sequence[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        chosen = user_card.strip().upper()
        dd = context.get("double_dummy") or {}

        matched = next((rec for rec in recommended_cards if str(rec.get("card", "")).upper() == chosen), None)
        top = recommended_cards[0] if recommended_cards else None

        if matched is not None:
            mistake_type = "aligned_with_recommendation"
            severity = "low"
            suggested = chosen
            learning_tip = "You followed a strong technical line. Continue balancing trick gain with honor preservation."
            message = (
                f"Strong technical play: {chosen} matched rank #{matched.get('rank', '?')} "
                f"(confidence {float(matched.get('confidence', 0.0)):.2f})."
            )
        else:
            mistake_type = "card_delta"
            severity = self._severity_from_card_gap(chosen, top)
            suggested = "" if top is None else str(top.get("card", ""))
            learning_tip = "When uncertain, prefer lines that preserve entries and keep future winners flexible."
            if top is None:
                message = f"No model card recommendation was available for {chosen}; focus on suit-following and plan continuity."
            else:
                message = (
                    f"Alternative line: {top.get('card')} was top-ranked at "
                    f"{float(top.get('confidence', 0.0)):.2f} to improve expected trick control."
                )

        dd_hint = ""
        if dd:
            dd_hint = (
                f" Double-dummy target remains {dd.get('expected_tricks', '?')} tricks in "
                f"{dd.get('contract', 'N/A')}."
            )

        return {
            "decision": "card",
            "player": context.get("player"),
            "user_action": chosen,
            "mistake_type": mistake_type,
            "severity": severity,
            "suggested_alternative": suggested,
            "learning_tip": learning_tip,
            "message": f"{message}{dd_hint}".strip(),
            "context_snapshot": {
                "trick_number": context.get("trick_number"),
                "trick_cards": context.get("trick_cards", []),
            },
        }

    # Function: summarize_hand_feedback.
    def summarize_hand_feedback(self, decision_feedback: Sequence[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        total = len(decision_feedback)
        medium_or_higher = [f for f in decision_feedback if f.get("severity") in {"medium", "high"}]
        top_gap = next((f for f in medium_or_higher if f.get("mistake_type") in {"bid_delta", "card_delta"}), None)

        learning_tip = (
            "Prioritize model top choices when they align with legal/system constraints, then adjust only with clear table reasons."
            if top_gap
            else "Good alignment overall; keep cross-checking decisions against contract goals and vulnerability."
        )

        return {
            "decision": "hand_summary",
            "mistake_type": "hand_review",
            "severity": "medium" if medium_or_higher else "low",
            "suggested_alternative": "Review top-ranked alternatives from flagged decisions.",
            "learning_tip": learning_tip,
            "message": (
                f"Hand coaching summary: {total} decisions reviewed, "
                f"{len(medium_or_higher)} medium/high coaching flags."
            ),
            "context_snapshot": {
                "contract": context.get("contract"),
                "double_dummy": context.get("double_dummy"),
                "infractions": context.get("bid_infractions", []),
            },
        }

    # Function: _severity_from_bid_gap.
    def _severity_from_bid_gap(self, chosen: str, top: Optional[Dict[str, Any]]) -> str:
        if top is None:
            return "medium"
        rank = int(top.get("rank", 1))
        confidence = float(top.get("confidence", 0.0))
        if confidence >= 0.7 and chosen != str(top.get("bid", "")).upper() and rank == 1:
            return "high"
        return "medium"

    # Function: _severity_from_card_gap.
    def _severity_from_card_gap(self, chosen: str, top: Optional[Dict[str, Any]]) -> str:
        if top is None:
            return "medium"
        confidence = float(top.get("confidence", 0.0))
        if confidence >= 0.75 and chosen != str(top.get("card", "")).upper():
            return "high"
        return "medium"

    # Function: _bid_learning_tip.
    def _bid_learning_tip(self, context: Dict[str, Any], has_infraction: bool) -> str:
        if has_infraction:
            return "First satisfy legal/system constraints, then optimize for fit and level using model-ranked options."
        if context.get("is_opening_bid"):
            return "Opening calls should balance HCP, shape, and vulnerability before preemptive pressure."
        return "Re-evaluate partnership fit and level safety before competing above model top choices."
