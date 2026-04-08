"""Model artifact registry and stable-version lookup for MVP policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


ARTIFACT_ROOT = Path(__file__).resolve().parent / "model_artifacts"
REGISTRY_PATH = ARTIFACT_ROOT / "registry.json"


@dataclass
class ModelArtifactMetadata:
    model_type: str
    version: str
    task: str
    stable: bool
    metrics: Dict[str, float]
    artifact_path: str
    created_at: str
    notes: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_registry() -> Dict[str, List[Dict[str, Any]]]:
    if not REGISTRY_PATH.exists():
        return {"artifacts": []}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _save_registry(payload: Dict[str, List[Dict[str, Any]]]) -> None:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def register_model_artifact(
    *,
    model_type: str,
    version: str,
    task: str,
    metrics: Dict[str, float],
    artifact_payload: Dict[str, Any],
    stable: bool = True,
    notes: str = "",
) -> ModelArtifactMetadata:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    artifact_name = f"{model_type}_{task}_{version}.json"
    artifact_path = ARTIFACT_ROOT / artifact_name
    artifact_path.write_text(json.dumps(artifact_payload, indent=2), encoding="utf-8")

    registry = _load_registry()
    if stable:
        for entry in registry["artifacts"]:
            if entry.get("model_type") == model_type and entry.get("task") == task:
                entry["stable"] = False

    metadata = ModelArtifactMetadata(
        model_type=model_type,
        version=version,
        task=task,
        stable=stable,
        metrics={k: float(v) for k, v in metrics.items()},
        artifact_path=str(artifact_path.relative_to(Path(__file__).resolve().parent)),
        created_at=_now_iso(),
        notes=notes,
    )
    registry["artifacts"].append(metadata.__dict__)
    _save_registry(registry)
    return metadata


def load_latest_stable_model(model_type: str, task: str) -> Optional[Dict[str, Any]]:
    registry = _load_registry()
    candidates = [
        item
        for item in registry.get("artifacts", [])
        if item.get("model_type") == model_type and item.get("task") == task and item.get("stable")
    ]
    if not candidates:
        return None

    latest = sorted(candidates, key=lambda item: item.get("created_at", ""))[-1]
    base = Path(__file__).resolve().parent
    path = base / str(latest["artifact_path"])
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["_metadata"] = latest
    return payload


def list_model_artifacts(model_type: str, task: str) -> List[Dict[str, Any]]:
    registry = _load_registry()
    artifacts = [
        item
        for item in registry.get("artifacts", [])
        if item.get("model_type") == model_type and item.get("task") == task
    ]
    return sorted(artifacts, key=lambda item: item.get("created_at", ""))


def load_model_artifact(model_type: str, task: str, version: str) -> Optional[Dict[str, Any]]:
    for entry in list_model_artifacts(model_type=model_type, task=task):
        if str(entry.get("version")) != str(version):
            continue
        path = Path(__file__).resolve().parent / str(entry.get("artifact_path", ""))
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["_metadata"] = entry
        return payload
    return None


def promote_model_artifact(model_type: str, task: str, version: str) -> bool:
    registry = _load_registry()
    target_found = False
    for entry in registry.get("artifacts", []):
        if entry.get("model_type") != model_type or entry.get("task") != task:
            continue
        is_target = str(entry.get("version")) == str(version)
        entry["stable"] = is_target
        if is_target:
            target_found = True
    if target_found:
        _save_registry(registry)
    return target_found
