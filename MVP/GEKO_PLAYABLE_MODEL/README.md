# GEKO Playable Bridge AI

This folder is a streamlined playable package for the current GEKO Bridge AI.
It includes:

- `BEST_CARD_PLAY`: standalone card-play model copied from the best tested card model.
- `BEST_BIDDING`: standalone multi-strategy bidding model trained from card-play outcomes.
- `strategy_profiles_numeric.json`: 30 bundled strategy declarations converted to numeric model input.
- `playable_bridge_ai.py`: command-line runner for bidding, card play, or an AI-only board.

The package is intended for playing with the model, not for training it.

## Install

From this folder:

```bat
pip install -r requirements.txt
```

## List Strategy Profiles

```bat
python playable_bridge_ai.py --list-profiles
```

## AI-Only Board

```bat
python playable_bridge_ai.py --mode ai-only --boards 1 --strategy-profile 1 --show-hands --top-k 5 --seed 31
```

Change `--strategy-profile` to test another declaration.

## Recommend A Bid

```bat
python playable_bridge_ai.py --mode bid --strategy-profile 1 --seat 1 --dealer 1 --hand "AS KS QS JS 2H 3H 4D 5D 6C 7C 8C 9C 10C" --top-k 5
```

## Recommend A Card

```bat
python playable_bridge_ai.py --mode card --seat 1 --hand "5C 8C 10C JC 2D JD KD 10H KH 5S 6S 9S KS" --trick "2C AC 3C" --contract-level 3 --contract-strain NT --declarer 1 --dummy 3 --visible-dummy "AC 4D 6D 7D 8D 2H 3H 4H 5H 8H QH 2S QS" --top-k 5
```

## Included Models

Card-play source:

`artifacts\mvp_card_self_play_policy_3hr_01_model`

Bidding source:

`artifacts\mvp_bid_cardplay_outcome_all_strategies_model`
