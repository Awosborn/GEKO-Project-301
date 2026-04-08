# GEKO Project Overview

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
