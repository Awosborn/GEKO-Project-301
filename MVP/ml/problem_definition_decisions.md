# Locked Problem-Definition Decisions (Step 1)

This document locks the unresolved decisions that shape data schema, features, and model targets.

## 1) Seat/dealer mapping for auction order

- Internal seat ids remain `1..4`.
- Canonical compass mapping is:
  - `1 -> N`
  - `2 -> E`
  - `3 -> S`
  - `4 -> W`
- Auction order is clockwise from dealer and computed by modulo rotation.

## 2) Model visibility at inference/training

- **Inference visibility:** acting hand + public information only.
  - Public info includes auction history, play history, vulnerability, dealer, and any contract fields that are legally inferable.
- **Training visibility for supervised policy:** same as inference (acting hand + public only) to avoid leakage.
- Full-deal information can still be used in an offline oracle pipeline to generate labels, but never as policy input features.

## 3) Label source ("best move")

- Label source is locked to **solver-generated labels**.
- Human/expert examples may be stored as auxiliary metadata, but target labels for this MVP pipeline are solver outputs.

## 4) Declarer/dummy derivation timing

- Declarer and dummy are derived at dataset-build time (**derive now**), not deferred to training/inference.
- Rationale: this keeps downstream feature extraction deterministic and avoids repeated re-derivation logic in multiple stages.

## Scope

These choices are implemented in `MVP/ml/problem_definition.py` as immutable constants/helpers.
Any future changes should be treated as a schema/version bump.
