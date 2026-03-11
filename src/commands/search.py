#!/usr/bin/env python3
"""Search cached toolcards from the active sync snapshot."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, NoReturn

from src.utils.registry_file_utils import hard_fail
from src.utils.toolcards_utils import load_toolcards


def _project_tool(
    record: dict[str, Any],
    index: int,
    fail: Callable[[str], NoReturn],
) -> dict[str, str]:
    """Extract the required search output fields from a tool record."""
    output: dict[str, str] = {}
    for field in ("id", "name", "description"):
        value = record.get(field)
        if not isinstance(value, str):
            fail(f"malformed toolcards artifact: tool at position {index} missing string field '{field}'")
        output[field] = value
    return output


def _hard_fail(message: str) -> NoReturn:
    hard_fail(f"search failed: {message}")


def run_search(cache_dir: Path) -> int:
    """Print cached tools as strict JSONL records."""
    fail = _hard_fail
    tools = load_toolcards(Path(cache_dir).expanduser(), fail=fail)
    if not tools:
        print("No tools found in cached registry.")
        return 0

    for index, record in enumerate(tools, start=1):
        print(json.dumps(_project_tool(record, index, fail), separators=(",", ":")))
    return 0
