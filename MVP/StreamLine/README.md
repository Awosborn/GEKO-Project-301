# StreamLine — Bridge Bid Coach Inference Package

Self-contained inference deployment for the fine-tuned bridge bidding coach.
No training code, no datasets, no nanoGPT. Everything needed to run the model
is in this folder.

---

## Folder Structure

```
StreamLine/
├── quick_test.py              Interactive command-line tester
├── requirements.txt           Python dependencies
├── model/                     Trained LoRA adapter (~35 MB)
│   ├── adapter_model.safetensors
│   ├── adapter_config.json
│   ├── tokenizer.json
│   ├── tokenizer_config.json
│   ├── chat_template.jinja
│   └── training_meta.json
├── src/
│   └── bridge_bid_coach/      Inference-only Python package
│       ├── coach.py           Main entry point + HCP correction
│       ├── inference.py       Model loading and text generation
│       ├── prompt_builder.py  Chat message construction
│       ├── schemas.py         GameState and CoachResponse types
│       ├── bid_ranker.py      Bid ranking utilities
│       ├── bridge_rules.py    Bid normalisation + HCP calculation
│       └── utils.py           Helpers
└── examples/
    ├── game_state.json                    Sample hand (South, after 1NT transfer)
    └── wrong_1nt_should_be_1h_input.json  Sample error hand
```

---

## Quick Start

```powershell
cd c:\LLMdev\StreamLine
python quick_test.py
```

You will be prompted step by step:

```
Your hand            : S AKQ H J94 D T862 C K73
Your seat (N/S/E/W)  : S
Dealer (N/S/E/W)     : N
Vulnerability        : none
Bid you made         : 2NT
Legal bids           : Pass 2NT 3C 3D 3H 3S 3NT Double
Auction so far       : 1NT Pass
Model's top-3 bids   :          <- press Enter to skip
```

All fields except hand, seat, dealer, vulnerability, and your bid are optional.

---

## Dependencies

Uses the shared `.venv` at `c:\LLMdev\.venv`. No reinstall needed if it is
already active. To install from scratch:

```powershell
pip install torch transformers peft pydantic
```

The base model (`HuggingFaceTB/SmolLM2-360M-Instruct`) is downloaded from
HuggingFace automatically on first run and cached at
`C:\Users\<you>\.cache\huggingface\`. Subsequent runs load from cache — no
internet required after the first run.

---

## The Model

| Property | Value |
|---|---|
| Base model | HuggingFaceTB/SmolLM2-360M-Instruct |
| Fine-tuning | LoRA (r=16, alpha=32), 7 attention/MLP modules |
| Training data | 1900 SAYC bridge bidding examples |
| Epochs | 3 |
| Final eval loss | 0.0494 |
| Token accuracy | ~98% |

The adapter weights in `model/adapter_model.safetensors` are merged into the
base model at load time (`PeftModel.merge_and_unload()`).

---

## Input Format

The model accepts a `GameState` object with these fields:

| Field | Required | Example |
|---|---|---|
| `dealer` | yes | `"north"` |
| `vulnerability` | yes | `"none"` / `"NS"` / `"EW"` / `"both"` |
| `current_seat` | yes | `"south"` |
| `user_bid` | yes | `"3NT"` |
| `hand` | recommended | `"S KQ984 H 72 D A83 C Q94"` |
| `auction_history` | optional | list of `{seat, call}` objects |
| `legal_bids` | optional | `["Pass","2S","2NT",...]` |
| `top_3_model_bids` | optional | `["2S","Pass","2NT"]` |
| `convention_card` | optional | system name, NT range, flags |

---

## Output Format

```json
{
  "user_bid": "3NT",
  "verdict": "improve",
  "recommended_bid": "2S",
  "top_3_bids": ["2S", "Pass", "2NT"],
  "explanation": "...",
  "convention_card_reasoning": "...",
  "risk_of_user_bid": "...",
  "partner_likely_inference": "...",
  "confidence": 0.85
}
```

`verdict` is `"reasonable"` when the user's bid is already in the top 3,
or `"improve"` when the model recommends a different call.

---

## HCP Correction (Hard-Coded Override)

The 360M model sometimes writes the wrong High Card Point count in its
free-text fields. StreamLine detects and corrects this automatically
**before returning the response to the caller**.

### How it works

**`bridge_rules.calculate_hcp(hand)`** — calculates the exact HCP from the
hand string using standard honours values:

| Card | Points |
|---|---|
| Ace | 4 |
| King | 3 |
| Queen | 2 |
| Jack | 1 |
| All others | 0 |

Example: `"S AKQ H J94 D T862 C K73"` = A(4) + K(3) + Q(2) + J(1) + K(3) = **13 HCP**

**`coach._correct_hcp(response, hand)`** — after the model returns valid JSON,
scans four free-text fields for any `N HCP` or `NHCP` pattern (case-insensitive):

- `explanation`
- `convention_card_reasoning`
- `risk_of_user_bid`
- `partner_likely_inference`

Any number that does not match the calculated HCP is replaced in-place.

```
Model wrote:  "Hand: S AK H AKT93 D T9762 C 7 (18 HCP, 2-5-5-1 shape)"
True HCP:     14
After fix:    "Hand: S AK H AKT93 D T9762 C 7 (14 HCP, 2-5-5-1 shape)"
```

The correction is silent — the response object is returned with the correct
value as if the model had written it correctly. If the model's HCP was already
right, the response is returned unchanged with no overhead.

### Where the code lives

| File | What it does |
|---|---|
| `src/bridge_bid_coach/bridge_rules.py` | `calculate_hcp()` — parses hand string, returns int |
| `src/bridge_bid_coach/coach.py` | `_correct_hcp()` — regex scan + replace across text fields |
| `src/bridge_bid_coach/coach.py` | `coach_game_state()` — calls `_correct_hcp` before returning |

---

## Using from Python

```python
import sys
sys.path.insert(0, "src")

from bridge_bid_coach.coach import coach_game_state
from bridge_bid_coach.schemas import GameState

state = GameState(
    dealer="north",
    vulnerability="none",
    current_seat="south",
    user_bid="3NT",
    hand="S KQ984 H 72 D A83 C Q94",
    top_3_model_bids=["2S", "Pass", "2NT"],
)

response = coach_game_state(state, model_dir="model")
print(response.verdict)           # "improve"
print(response.recommended_bid)   # "2S"
print(response.explanation)
```

---

## Known Limitations

| Issue | Detail |
|---|---|
| Weak free-text | 360M model is too small for fluent explanation generation |
| HCP corrected automatically | See HCP Correction section above |
| `risk_of_user_bid` sometimes echoes `verdict` | Training artefact — upgrade to 1.5B model to fix |
| Slow on CPU | ~30–60s per query; GPU reduces this to ~2s |

To improve the model, retrain with `Qwen2.5-1.5B` using
`c:\LLMdev\bridge_bid_coach_nano\sft\config_sft.yaml` on a GPU.
