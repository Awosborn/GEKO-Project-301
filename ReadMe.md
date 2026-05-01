# GEKO Project Overview

## Quick Commands (Verified against files in this snapshot)
- **Run tests:** `python -m pytest -q`
- **Build supervised datasets from snapshot JSONL:** `python -m MVP.ml.build_dataset_cli <path/to/snapshots.jsonl> --output-dir <artifacts/datasets> --formats jsonl parquet`
- **Train next-bid model:** `python -m MVP.ml.train_next_bid <artifacts/datasets/bidding_examples.jsonl> --output-dir <artifacts/models/bid> --apply-legality-mask-training`
- **Train next-card model:** `python -m MVP.ml.train_next_card <artifacts/datasets/cardplay_examples.jsonl> --output-dir <artifacts/models/card> --apply-legality-mask-training`
- **Play random deals vs trained bidding AI (AI = players 1-3, you = player 4):** `python -m MVP.ml.play_vs_ai --model-dir <artifacts/models/bid> --boards 3 --seed 7`
- **Inspect generated eval report (produced during training):** `python -c "import json, pathlib; p=pathlib.Path('<artifacts/models/bid/evaluation_report.json>'); print(json.dumps(json.loads(p.read_text()), indent=2)[:4000])"`

> Note: legacy commands that reference `MVP/cli.py` are currently stale in this repository snapshot because `MVP/cli.py` is not present.

### ML quickstart (dataset build → train → eval → serve)
1. **Build datasets** from raw snapshot rows:
   - `python -m MVP.ml.build_dataset_cli data/snapshots.jsonl --output-dir artifacts/datasets --formats jsonl parquet`
2. **Train bidding model** (writes baseline + transformer artifacts + eval report):
   - `python -m MVP.ml.train_next_bid artifacts/datasets/bidding_examples.jsonl --output-dir artifacts/models/bid --epochs 3 --batch-size 16 --apply-legality-mask-training`
3. **Train card-play model**:
   - `python -m MVP.ml.train_next_card artifacts/datasets/cardplay_examples.jsonl --output-dir artifacts/models/card --epochs 3 --batch-size 16 --apply-legality-mask-training`
4. **Evaluate** by reading generated reports:
   - `python -c "import json, pathlib; print(json.dumps(json.loads(pathlib.Path('artifacts/models/bid/evaluation_report.json').read_text()), indent=2))"`
   - `python -c "import json, pathlib; print(json.dumps(json.loads(pathlib.Path('artifacts/models/card/evaluation_report.json').read_text()), indent=2))"`
5. **Serve predictions** via FastAPI:
   - `python -c "import uvicorn; from MVP.ml.inference_service import create_inference_app; uvicorn.run(create_inference_app('artifacts/models/bid','artifacts/models/card'), host='0.0.0.0', port=8000)"`

### Artifact locations
- Dataset export outputs (`build_dataset_cli`):
  - `artifacts/datasets/bidding_examples.jsonl`
  - `artifacts/datasets/cardplay_examples.jsonl`
  - `artifacts/datasets/bidding_examples.parquet` (if parquet requested)
  - `artifacts/datasets/cardplay_examples.parquet` (if parquet requested)
- Training outputs (each model output dir):
  - `baseline.json`
  - `tokenizer_artifact.json`
  - `label_map.json`
  - `checkpoint_epoch_<N>.pt`
  - `checkpoint_best.pt`
  - `transformer_metrics.json`
  - `evaluation_report.json`
  - `inference_guardrails.json`

### Troubleshooting
- **`ModuleNotFoundError: No module named 'MVP'`**
  - Run commands from the repo root (`GEKO-Project-301/`) so `python -m MVP...` resolves packages correctly.
- **Parquet write errors** (e.g., missing engine)
  - Re-run with JSONL only: `--formats jsonl`.
- **`Dataset is empty; cannot train.`**
  - Confirm `build_dataset_cli` produced non-empty `bidding_examples.jsonl` / `cardplay_examples.jsonl`.
- **FastAPI serve import/runtime errors**
  - Install runtime deps (`fastapi`, `uvicorn`) in your environment before running the serve command.
- **No GPU detected**
  - Training auto-falls back to CPU; expect slower epochs.

## Purpose of the Codebase
This repository contains the MVP implementation for the **GEKO bridge coaching and play engine**. The code focuses on simulating and evaluating Contract Bridge gameplay with separate logic for bidding, card play, rules validation, and penalties.

At a high level, the project aims to:
- Model realistic bridge game flow (deal, bidding, play, scoring).
- Evaluate bridge decisions using strategy/rules checks.
- Support AI-assisted or model-driven bidding and card-play experimentation.
- Provide a foundation for coaching feedback by comparing player actions to stronger projected outcomes.

## Pull Request Update Instructions
This file **must be updated in every pull request**.

For each PR, append a short section at the bottom using this template:

```md
## PR Update - <YYYY-MM-DD> - <PR or Branch Name>
- Summary: <1-2 sentence summary of what changed>
- Files touched: <comma-separated list>
- Validation: <tests/checks run and results>
- Follow-ups: <optional next steps>
```

### Update Rules
- Keep updates in reverse chronological order (newest at the bottom).
- Be specific and concise.
- Include at least one validation/check item, even if manual.
- Do not delete historical PR update sections.

## PR Update - 2026-04-08 - training-cli-self-play-cycle
- Summary: Added a unified CLI command for training both models and playing against stable models, plus a training cycle that pits new candidate policies against the prior stable champion before promotion.
- Files touched: read.md, MVP/cli.py, MVP/train_cycle.py, MVP/model_registry.py, MVP/train_bidding.py, MVP/train_cardplay.py
- Validation: Ran `python3 MVP/cli.py train-cycle`, `python3 MVP/cli.py train-all`, and `python3 MVP/cli.py --help`.
- Follow-ups: Consider extending arena evaluation from context-match scoring to full hand-level simulated matches.

## PR Update - 2026-04-08 - docs-windows-cli-path-fix
- Summary: Clarified CLI usage for both repo-root and `MVP/` working directories, and added Windows-specific guidance for Python executable/path confusion.
- Files touched: read.md
- Validation: Ran `python --version` and `python MVP/cli.py --help`.
- Follow-ups: Consider adding a tiny PowerShell helper script that auto-detects a working Python interpreter and runs `cli.py`.

## PR Update - 2026-04-08 - add-run_this-numbered-launcher
- Summary: Added a repo-root `run_this` launcher script that prompts for a numbered choice and executes the matching GEKO CLI command.
- Files touched: run_this, read.md
- Validation: Ran `python3 run_this` (with selections `4` and invalid `9`).
- Follow-ups: Consider adding a fifth option to let users enter custom CLI subcommands directly.

## PR Update - 2026-04-08 - self-play-generated-training-data
- Summary: Updated CLI training commands to generate runner training/validation datasets from self-play before training, removing reliance on pre-existing external training data files.
- Files touched: read.md, MVP/cli.py, MVP/self_play_data.py
- Validation: Static inspection only (no command execution per task constraints).
- Follow-ups: Consider replacing stochastic placeholder action sampling in self-play generation with fully legal game-loop simulation for stronger data quality.


## PR Update - 2026-04-13 - week1-priority-steps-1-4
- Summary: Implemented a Week-1 preprocessing module covering deal-id derivation, bid normalization, full-hand reconstruction from snapshot play history, and corruption checks, with pytest coverage for these flows.
- Files touched: read.md, MVP/ml/preprocess.py, MVP/ml/__init__.py, MVP/__init__.py, MVP/tests/test_preprocess.py
- Validation: Ran `python -m pytest -q` (5 tests passed).
- Follow-ups: Wire these preprocessing helpers into a dataset-export CLI once source snapshot JSONL files are added to this repository.

## PR Update - 2026-04-13 - week2-priority-steps-5-8
- Summary: Implemented Week-2 supervised dataset-export helpers to group snapshot rows by deal, select the representative bidding snapshot, flatten/normalize auctions into temporal events, and emit prefix→next examples for both bidding and card-play (post-action inversion).
- Files touched: read.md, MVP/ml/__init__.py, MVP/ml/dataset_export.py, MVP/tests/test_dataset_export.py
- Validation: Ran `python -m pytest -q` (9 tests passed).
- Follow-ups: Add JSONL/parquet writers and split-by-deal utilities so these in-memory examples can be persisted for training loops.

## PR Update - 2026-04-13 - week3-priority-steps-9-12
- Summary: Added Week-3 ML utilities by introducing centralized token normalization, training-token-backed tokenizer helpers, auction contract-meaning derivation for card-play examples, and deal-group split helpers to prevent train/val/test leakage.
- Files touched: read.md, MVP/ml/preprocess.py, MVP/ml/dataset_export.py, MVP/ml/__init__.py, MVP/ml/normalize.py, MVP/ml/tokenizer.py, MVP/ml/derive_contract.py, MVP/ml/splits.py, MVP/tests/test_preprocess.py, MVP/tests/test_dataset_export.py, MVP/tests/test_week3_ml_utils.py
- Validation: Ran `python -m pytest -q` (12 tests passed).
- Follow-ups: Add bid/card legality-mask builders and wire these utilities into model training/evaluation scripts under `MVP/ml/train` and `MVP/ml/eval`.

## PR Update - 2026-04-13 - week4-priority-steps-13-16
- Summary: Implemented Week-4 legality-mask utilities for supervised bidding and card-play workflows, including bid/card mask builders that mirror game legality constraints, with dedicated unit tests.
- Files touched: read.md, MVP/ml/__init__.py, MVP/ml/masks.py, MVP/tests/test_week4_masks.py
- Validation: Ran `python -m pytest -q` (17 tests passed).
- Follow-ups: Wire these masks directly into the training/evaluation loops once `MVP/ml/train` modules are added.

## PR Update - 2026-04-13 - week5-step1-problem-definition-lock
- Summary: Locked unresolved problem-definition decisions for supervised bridge learning (seat/dealer mapping, inference/training visibility, solver-based labels, and deriving declarer/dummy at dataset build time), and encoded them in a reusable ML module with tests.
- Files touched: read.md, MVP/ml/problem_definition.py, MVP/ml/problem_definition_decisions.md, MVP/ml/__init__.py, MVP/tests/test_problem_definition.py
- Validation: Ran `python -m pytest -q` (20 tests passed).
- Follow-ups: Thread `dealer_seat` explicitly into auction flattening/export paths so seat-to-act reconstruction can support partial-auction snapshots sourced from alternate schemas.

## PR Update - 2026-04-13 - week5-step2-dataset-persistence-cli
- Summary: Added end-to-end dataset persistence for bidding/card-play examples with JSONL and Parquet writers, plus a CLI that builds datasets from snapshot JSONL and emits reproducibility stats including corruption counts.
- Files touched: read.md, MVP/ml/dataset_export.py, MVP/ml/build_dataset_cli.py, MVP/ml/__init__.py, MVP/tests/test_dataset_export.py, MVP/tests/test_build_dataset_cli.py
- Validation: Ran `python -m pytest -q` (23 tests passed).
- Follow-ups: Consider adding schema-version metadata files and deterministic split manifests alongside dataset outputs.

## PR Update - 2026-04-13 - week5-step3-training-entrypoints
- Summary: Added supervised next-bid and next-card training entrypoints with a baseline majority classifier and a transformer training loop, including epoch/best checkpoint artifacts and tokenizer/label-map persistence.
- Files touched: read.md, MVP/ml/train_common.py, MVP/ml/train_next_bid.py, MVP/ml/train_next_card.py, MVP/ml/__init__.py, MVP/tests/test_train_entrypoints.py
- Validation: Ran `python -m pytest -q` (25 tests passed).
- Follow-ups: Add train/val split support, evaluation metrics (top-k/legality-aware), and stable model registry integration for promotion workflows.

## PR Update - 2026-04-13 - week5-step4-legality-masks-integration
- Summary: Integrated bid/card legality masks into supervised train/eval/inference paths by adding legality-constrained inference helpers, optional legality-masked transformer training flags, and guardrail artifact generation to prevent illegal recommendations.
- Files touched: read.md, MVP/ml/inference.py, MVP/ml/train_next_bid.py, MVP/ml/train_next_card.py, MVP/ml/__init__.py, MVP/tests/test_train_entrypoints.py, MVP/tests/test_week6_legality_inference.py
- Validation: Ran `python -m pytest -q` (27 tests passed).
- Follow-ups: Replace placeholder score sources in guardrail report generation with saved model logits once standalone eval/inference entrypoints are added.

## PR Update - 2026-04-13 - week6-step6-inference-service-endpoints
- Summary: Added inference-service utilities plus FastAPI endpoint wiring for `/predict_bid` and `/predict_card`, loading saved tokenizer/model artifacts and returning both raw top-k and legality-masked top-k probabilities.
- Files touched: read.md, MVP/ml/inference_service.py, MVP/ml/__init__.py, MVP/tests/test_inference_service.py
- Validation: Ran `python -m pytest -q MVP/tests/test_inference_service.py` and `python -m pytest -q`.
- Follow-ups: Add deployment/runtime config docs (env vars and uvicorn command) once serving infrastructure is finalized.

## PR Update - 2026-04-13 - week6-step7-docs-command-wiring
- Summary: Replaced stale top-level quick commands with verified module-based commands, and added an end-to-end ML quickstart covering dataset build, training, evaluation report inspection, serving, artifact paths, and troubleshooting guidance.
- Files touched: read.md
- Validation: Ran `python -m MVP.ml.build_dataset_cli --help`, `python -m MVP.ml.train_next_bid --help`, `python -m MVP.ml.train_next_card --help`, and `python -m pytest -q MVP/tests/test_build_dataset_cli.py MVP/tests/test_train_entrypoints.py MVP/tests/test_inference_service.py`.
- Follow-ups: Add a dedicated serving CLI entrypoint (for direct `uvicorn module:app`) and a standalone evaluation CLI to avoid inline `python -c` report inspection commands.


## PR Update - 2026-04-14 - play-vs-ai-seat4-random-deals
- Summary: Added an interactive random-deal play mode that loads trained bidding artifacts so AI controls players 1-3 while the user plays as player 4, plus launcher/docs updates for the new workflow.
- Files touched: read.md, run_this.py, MVP/ml/play_vs_ai.py, MVP/tests/test_play_vs_ai.py
- Validation: Ran `python -m pytest -q MVP/tests/test_play_vs_ai.py`.
- Follow-ups: Extend this from bidding-only interaction into full trick-play progression using trained card model artifacts.

## PR Update - 2026-05-01 - standalone-bridge-ui-integration
- Summary: Added a standalone offline web UI that integrates a local predictive top-3 bidding module with an LLM-style coaching layer that auto-corrects bids outside the top-3 and explains why.
- Files touched: MVP/bridge_ui/index.html, MVP/bridge_ui/styles.css, MVP/bridge_ui/app.js, ReadMe.md
- Validation: Ran `node --check MVP/bridge_ui/app.js` and `git status --short`.
- Follow-ups: Replace heuristic predictive logic with direct bindings to packaged StreamLine + GEKO model runners once a shared local execution interface is finalized.
