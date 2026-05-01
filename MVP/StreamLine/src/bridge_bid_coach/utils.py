"""Shared utilities for configuration, logging, tokenizer loading, and encoding."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional


WORD_RE = re.compile(r"\S+")


def setup_logging(level: str = "INFO") -> None:
    """Configure logging, preferring Rich if it is installed."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    try:
        from rich.logging import RichHandler

        logging.basicConfig(
            level=numeric_level,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(rich_tracebacks=True)],
        )
    except Exception:
        logging.basicConfig(
            level=numeric_level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )


def load_yaml(path: str | Path) -> Dict[str, Any]:
    """Load a YAML config file."""
    import yaml

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def count_words(text: str) -> int:
    """Count whitespace-delimited words in a string."""
    return len(WORD_RE.findall(text))


def choose_device(requested: str = "auto") -> str:
    """Resolve the training/inference device."""
    if requested != "auto":
        return requested
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def load_tokenizer(tokenizer_path: str | Path):
    """Load an existing Hugging Face tokenizers JSON file."""
    path = Path(tokenizer_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Tokenizer not found: {path}. Put your existing tokenizer at this path "
            "or pass --tokenizer /path/to/tokenizer.json."
        )
    try:
        from tokenizers import Tokenizer
    except ImportError as exc:
        raise ImportError("Install tokenizers first: pip install tokenizers") from exc
    return Tokenizer.from_file(str(path))


def encode_corpus_to_npy(
    corpus_path: str | Path,
    tokenizer_path: str | Path,
    save_tokens_path: str | Path,
    *,
    add_special_tokens: bool = False,
) -> Dict[str, float]:
    """
    Encode a corpus with an existing tokenizer and save token IDs to a .npy file.

    The corpus is read line by line so large text files do not need to be held in
    memory. Token IDs are saved as int32 for broad tokenizer compatibility.
    """
    import numpy as np

    corpus = Path(corpus_path)
    output = Path(save_tokens_path)
    if not corpus.exists():
        raise FileNotFoundError(f"Corpus file not found: {corpus}")

    tokenizer = load_tokenizer(tokenizer_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    token_ids: list[int] = []
    word_count = 0
    with corpus.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            word_count += count_words(stripped)
            token_ids.extend(tokenizer.encode(stripped, add_special_tokens=add_special_tokens).ids)

    array = np.asarray(token_ids, dtype=np.int32)
    np.save(output, array)

    token_count = int(array.size)
    vocab_size = int(tokenizer.get_vocab_size())
    avg_tokens_per_word = float(token_count / word_count) if word_count else 0.0
    return {
        "words": int(word_count),
        "tokens": token_count,
        "vocab_size": vocab_size,
        "avg_tokens_per_word": avg_tokens_per_word,
    }


def pydantic_model_dump(model: Any) -> Dict[str, Any]:
    """Return a dict from either Pydantic v1 or v2 models."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def pydantic_model_validate(model_cls: Any, data: Dict[str, Any]) -> Any:
    """Validate a dict with either Pydantic v1 or v2."""
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(data)
    return model_cls.parse_obj(data)


def read_text_if_exists(path: Optional[str | Path]) -> Optional[str]:
    """Read a UTF-8 text file if a path is provided and exists."""
    if path is None:
        return None
    text_path = Path(path)
    if not text_path.exists():
        return None
    return text_path.read_text(encoding="utf-8")
