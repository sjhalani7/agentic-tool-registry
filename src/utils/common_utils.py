#!/usr/bin/env python3
"""Shared helpers used across registry scripts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def iter_tool_dirs(tools_root: Path) -> list[Path]:
    """Return sorted tool directories under tools/<publisher>/<tool>."""
    if not tools_root.exists():
        return []
    return sorted(path for path in tools_root.glob("*/*") if path.is_dir())


def load_json(path: Path) -> Any:
    """Load a JSON file from disk."""
    with path.open() as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    """Write pretty, sorted JSON output to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    """Compute a SHA256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
