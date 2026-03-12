#!/usr/bin/env python3
"""Toolspecs cache loading helpers for registry commands."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, NoReturn

from src.utils.registry_file_utils import (
    find_single_artifact_path,
    load_json_object,
    load_object_records,
    resolve_snapshot_dir,
)


def load_toolspecs(
    cache_dir: Path,
    fail: Callable[[str], NoReturn],
) -> list[dict[str, Any]]:
    """Load toolspec records from the active cache snapshot."""
    snapshot_dir = resolve_snapshot_dir(cache_dir, fail)
    manifest = load_json_object(snapshot_dir / "manifest.json", "snapshot manifest", fail)
    artifact_path = find_single_artifact_path(
        manifest=manifest,
        snapshot_dir=snapshot_dir,
        artifact_prefix="toolspecs",
        fail=fail,
    )
    return load_object_records(artifact_path, "toolspecs artifact", fail)
