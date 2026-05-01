"""SFT model loading and text generation for coach inference.

Replaces the original nanoGPT inference path.  The model directory may point to:
  - A LoRA adapter directory (contains adapter_config.json).
    The base model named in adapter_config.json is loaded first; the adapter is
    merged at load time for efficient inference.
  - A full merged checkpoint directory (no adapter_config.json).

A module-level pipeline cache avoids reloading the model on repeated calls
within the same process.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Module-level cache: model_dir str -> transformers pipeline object
_PIPELINE_CACHE: Dict[str, Any] = {}


def _load_pipeline(model_dir: Path, device: str) -> Any:
    """Load (and cache) a text-generation pipeline from *model_dir*."""
    import torch  # type: ignore[import-untyped]
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline  # type: ignore[import-untyped]

    adapter_config = model_dir / "adapter_config.json"
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    device_map = device if device != "auto" else "auto"

    if adapter_config.exists():
        from peft import PeftModel  # type: ignore[import-untyped]

        with adapter_config.open(encoding="utf-8") as fh:
            acfg = json.load(fh)
        base_name: str = acfg["base_model_name_or_path"]

        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=True)
        base_model = AutoModelForCausalLM.from_pretrained(
            base_name,
            torch_dtype=dtype,
            device_map=device_map,
            trust_remote_code=True,
        )
        model = PeftModel.from_pretrained(base_model, str(model_dir))
        model = model.merge_and_unload()
    else:
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            str(model_dir),
            torch_dtype=dtype,
            device_map=device_map,
            trust_remote_code=True,
        )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    return pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
    )


def load_pipeline(model_dir: str | Path, *, device: str = "auto") -> Any:
    """Return a cached text-generation pipeline for *model_dir*."""
    key = str(Path(model_dir).resolve())
    if key not in _PIPELINE_CACHE:
        _PIPELINE_CACHE[key] = _load_pipeline(Path(model_dir), device)
    return _PIPELINE_CACHE[key]


def generate_text(
    messages: List[Dict[str, str]],
    *,
    model_dir: str | Path,
    device: str = "auto",
    max_new_tokens: int = 512,
    temperature: float = 0.1,
    top_p: float = 0.95,
    repetition_penalty: float = 1.1,
    do_sample: bool = False,
) -> str:
    """Generate text from a chat *messages* list using the SFT model.

    Returns the assistant's raw reply string (before any JSON extraction).
    """
    pipe = load_pipeline(model_dir, device=device)

    output = pipe(
        messages,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_p=top_p,
        repetition_penalty=repetition_penalty,
        do_sample=do_sample,
        return_full_text=False,
        pad_token_id=pipe.tokenizer.eos_token_id,
    )
    # transformers pipeline returns [{"generated_text": ...}] for a single input
    return output[0]["generated_text"]


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Extract and return the first complete JSON object found in *text*.

    Returns None if no valid JSON object is present.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
