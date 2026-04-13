# GEKO Project Overview

## Quick Commands (Run these first)
- **From repository root** (`GEKO-Project-301/`):
  - Train both models: `python MVP/cli.py train-all`
  - Train with self-play cycle against previous best versions: `python MVP/cli.py train-cycle`
  - Play against the currently stable models: `python MVP/cli.py play`
- **From inside the `MVP/` folder**:
  - Train both models: `python cli.py train-all`
  - Train with self-play cycle against previous best versions: `python cli.py train-cycle`
  - Play against the currently stable models: `python cli.py play`

### Windows notes
- If `python3` points to a broken toolchain Python (for example `C:\iverilog\gtkwave\bin\python3.exe`), use `python` or `py -3.13` instead.
- In PowerShell, `MVP/cli.py` is **not** directly executable. Run it through Python (`python MVP/cli.py ...` from repo root, or `python cli.py ...` from `MVP/`).

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
