#!/usr/bin/env python3
"""Resolve one cached toolspec from the active sync snapshot."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, NoReturn

from src.utils.registry_file_utils import hard_fail, order_record_fields
from src.utils.toolspecs_utils import load_toolspecs
from src.utils.toolcards_utils import normalize_tool_id


def _hard_fail(message: str) -> NoReturn:
    """Raise a command-scoped resolve failure."""
    hard_fail(f"resolve failed: {message}")


def _validate_record(
    record: dict[str, Any],
    index: int,
    fail: Callable[[str], NoReturn],
) -> str:
    """Validate required resolve fields and return normalized tool ID."""
    raw_tool_id = record.get("tool_id")
    if not isinstance(raw_tool_id, str) or not raw_tool_id.strip():
        fail(f"malformed toolspecs artifact: spec at position {index} missing string field 'tool_id'")

    raw_type = record.get("type")
    if not isinstance(raw_type, str) or not raw_type.strip():
        fail(f"malformed toolspecs artifact: spec at position {index} missing string field 'type'")

    raw_summary = record.get("summary")
    if not isinstance(raw_summary, str):
        fail(f"malformed toolspecs artifact: spec at position {index} missing string field 'summary'")

    raw_auth = record.get("auth")
    if not isinstance(raw_auth, dict):
        fail(f"malformed toolspecs artifact: spec at position {index} missing object field 'auth'")

    raw_external_docs = record.get("external_docs")
    if not isinstance(raw_external_docs, list):
        fail(f"malformed toolspecs artifact: spec at position {index} missing array field 'external_docs'")

    return normalize_tool_id(raw_tool_id)


def run_resolve(cache_dir: Path, tool_id: str) -> int:
    """Print one cached toolspec as minified JSON."""
    fail = _hard_fail
    normalized_query_id = normalize_tool_id(tool_id)
    if not normalized_query_id:
        fail("tool ID is required")

    toolspecs = load_toolspecs(Path(cache_dir).expanduser(), fail=fail)
    if not toolspecs:
        fail("no toolspecs found in cached registry")

    for index, record in enumerate(toolspecs, start=1):
        normalized_id = _validate_record(record, index, fail)
        if normalized_id == normalized_query_id:
            ordered = order_record_fields(record, ("tool_id", "type", "summary", "auth", "external_docs"))
            print(json.dumps(ordered, separators=(",", ":")))
            return 0

    fail(f"tool '{tool_id}' not found")
