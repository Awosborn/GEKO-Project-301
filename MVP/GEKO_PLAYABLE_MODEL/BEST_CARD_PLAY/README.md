# BEST_CARD_PLAY

This is a streamlined standalone copy of the strongest current GEKO card-play model.

Source model:

`artifacts\mvp_card_self_play_policy_3hr_01_model`

Included runtime files:

- `model\card_feature_checkpoint_best.pt`
- `model\card_feature_config.json`
- `model\label_map.json`
- `best_card_play.py`

The runner only needs Python and `torch`. It does not require the rest of the MVP training code.

## Command Line Example

From the MVP folder:

```bat
python BEST_CARD_PLAY\best_card_play.py --seat 1 --hand "5C 8C 10C JC 2D JD KD 10H KH 5S 6S 9S KS" --trick "2C AC 3C" --contract-level 3 --contract-strain NT --declarer 1 --dummy 3 --visible-dummy "AC 4D 6D 7D 8D 2H 3H 4H 5H 8H QH 2S QS" --top-k 5
```

For exact in-game state, pass the full play prefix as a JSON file containing a list of `{ "player": seat, "card": card }` objects:

```bat
python BEST_CARD_PLAY\best_card_play.py --seat 1 --hand "5C 8C 10C JC 2D JD KD 10H KH 5S 6S 9S KS" --play-prefix-json path\to\play_prefix.json --contract-level 3 --contract-strain NT --declarer 1 --dummy 3 --top-k 5
```

## Python Example

```python
from BEST_CARD_PLAY import BestCardPlayModel

model = BestCardPlayModel()
result = model.predict(
    seat_to_act=1,
    hand_cards=["5C", "8C", "10C", "JC", "2D", "JD", "KD", "10H", "KH", "5S", "6S", "9S", "KS"],
    play_prefix=[
        {"player": 2, "card": "2C"},
        {"player": 3, "card": "AC"},
        {"player": 4, "card": "3C"},
    ],
    derived_contract={"level": 3, "strain": "NT", "declarer": 1, "dummy": 3},
    visible_dummy_hand=["AC", "4D", "6D", "7D", "8D", "2H", "3H", "4H", "5H", "8H", "QH", "2S", "QS"],
    top_k=5,
)
print(result["recommended_card"])
print(result["top_k"])
```
