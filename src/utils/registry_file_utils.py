#!/usr/bin/env python3
"""Reusable cache/snapshot loading helpers for registry commands."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, NoReturn

from src.utils.common_utils import load_json


def hard_fail(message: str) -> NoReturn:
    """Raise a cache-related failure with sync recovery guidance."""
    raise SystemExit(f"{message}. Rerun `atr sync`.")


def load_json_object(path: Path, label: str, fail: Callable[[str], NoReturn]) -> dict[str, Any]:
    """Load a required JSON object from disk."""
    if not path.exists():
        fail(f"missing {label}: {path}")
    if not path.is_file():
        fail(f"invalid {label}: {path}")
    try:
        payload = load_json(path)
    except Exception as exc:  # noqa: BLE001
        fail(f"malformed {label}: {path} ({exc})")
    if not isinstance(payload, dict):
        fail(f"malformed {label}: {path} (expected JSON object)")
    return payload


def resolve_snapshot_dir(cache_dir: Path, fail: Callable[[str], NoReturn]) -> Path:
    """Resolve and validate snapshot_dir from cache state."""
    state = load_json_object(cache_dir / "current.json", "cache state file", fail)
    raw_snapshot_dir = state.get("snapshot_dir")
    if not isinstance(raw_snapshot_dir, str) or not raw_snapshot_dir.strip():
        fail("cache state missing snapshot_dir")
    snapshot_dir = Path(raw_snapshot_dir).expanduser()
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        fail(f"missing snapshot directory: {snapshot_dir}")
    return snapshot_dir


def find_single_artifact_path(
    manifest: dict[str, Any],
    snapshot_dir: Path,
    artifact_prefix: str,
    fail: Callable[[str], NoReturn],
) -> Path:
    """Find one artifact path from manifest by name prefix."""
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        fail("manifest missing artifacts map")
    candidates = [name for name in artifacts if isinstance(name, str) and name.startswith(artifact_prefix)]
    if not candidates:
        fail(f"manifest missing artifact with prefix '{artifact_prefix}'")
    if len(candidates) > 1:
        listed = ", ".join(sorted(candidates))
        fail(f"manifest has multiple artifacts with prefix '{artifact_prefix}': {listed}")
    artifact_path = snapshot_dir / candidates[0]
    if not artifact_path.exists() or not artifact_path.is_file():
        fail(f"missing artifact file with prefix '{artifact_prefix}': {artifact_path}")
    return artifact_path


def parse_jsonl_object_records(
    path: Path,
    artifact_name: str,
    fail: Callable[[str], NoReturn],
) -> list[dict[str, Any]]:
    """Parse JSONL object records from a file."""
    records: list[dict[str, Any]] = []
    try:
        with path.open() as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    fail(f"malformed {artifact_name}: blank line at {path}:{line_no}")
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    fail(f"malformed {artifact_name}: invalid JSON at {path}:{line_no} ({exc.msg})")
                if not isinstance(record, dict):
                    fail(f"malformed {artifact_name}: expected object at {path}:{line_no}")
                records.append(record)
    except OSError as exc:
        fail(f"unable to read {artifact_name}: {path} ({exc})")
    return records


def parse_json_array_object_records(
    path: Path,
    artifact_name: str,
    fail: Callable[[str], NoReturn],
) -> list[dict[str, Any]]:
    """Parse JSON array object records from a file."""
    payload: Any
    try:
        payload = load_json(path)
    except Exception as exc:  # noqa: BLE001
        fail(f"malformed {artifact_name}: {path} ({exc})")
    if not isinstance(payload, list):
        fail(f"malformed {artifact_name}: {path} (expected JSON array)")

    records: list[dict[str, Any]] = []
    for index, record in enumerate(payload, start=1):
        if not isinstance(record, dict):
            fail(f"malformed {artifact_name}: expected object at index {index}")
        records.append(record)
    return records


def load_object_records(
    path: Path,
    artifact_name: str,
    fail: Callable[[str], NoReturn],
) -> list[dict[str, Any]]:
    """Load object records from JSONL or JSON array files."""
    if path.suffix == ".jsonl":
        return parse_jsonl_object_records(path, artifact_name, fail)
    return parse_json_array_object_records(path, artifact_name, fail)
