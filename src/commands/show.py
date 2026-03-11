#!/usr/bin/env python3
"""Show one cached toolcard from the active sync snapshot."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, NoReturn

from src.utils.registry_file_utils import hard_fail, order_record_fields
from src.utils.toolcards_utils import load_toolcards, normalize_tool_id


def _hard_fail(message: str) -> NoReturn:
    """Raise a command-scoped show failure."""
    hard_fail(f"show failed: {message}")


def _validate_record(
    record: dict[str, Any],
    index: int,
    fail: Callable[[str], NoReturn],
) -> str:
    """Validate required show fields and return normalized ID."""
    raw_id = record.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        fail(f"malformed toolcards artifact: tool at position {index} missing string field 'id'")
    for field in ("name", "description"):
        value = record.get(field)
        if not isinstance(value, str):
            fail(f"malformed toolcards artifact: tool at position {index} missing string field '{field}'")
    return normalize_tool_id(raw_id)


def run_show(cache_dir: Path, tool_id: str) -> int:
    """Print one cached toolcard as minified JSON."""
    fail = _hard_fail
    normalized_query_id = normalize_tool_id(tool_id)
    if not normalized_query_id:
        fail("tool ID is required")

    tools = load_toolcards(Path(cache_dir).expanduser(), fail=fail)
    if not tools:
        fail("no tools found in cached registry")

    for index, record in enumerate(tools, start=1):
        normalized_id = _validate_record(record, index, fail)
        if normalized_id == normalized_query_id:
            print(json.dumps(order_record_fields(record, ("id", "name", "description")), separators=(",", ":")))
            return 0

    fail(f"tool '{tool_id}' not found")
