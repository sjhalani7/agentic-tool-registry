#!/usr/bin/env python3
"""CLI entrypoint for command execution"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.commands.search import run_search
from src.commands.show import run_show
from src.commands.sync import DEFAULT_CACHE_DIR, DEFAULT_SOURCE_DIR, SUPPORTED_CHANNELS, run_sync


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="agentic-tool-registry",
        description="CLI for syncing local registry bundles into cache.",
    )
    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser("sync", help="Sync a local bundle snapshot into cache.")
    sync_parser.add_argument(
        "--source-dir",
        default=str(DEFAULT_SOURCE_DIR),
        help=f"Local bundle source directory (default: {DEFAULT_SOURCE_DIR}).",
    )
    sync_parser.add_argument(
        "--version",
        default=None,
        help="Explicit bundle version directory name (default: latest).",
    )
    sync_parser.add_argument(
        "--channel",
        default="stable",
        choices=sorted(SUPPORTED_CHANNELS),
        help="Channel to sync from the selected bundle (default: stable).",
    )
    sync_parser.add_argument(
        "--allow-risky-channel",
        action="store_true",
        help="Acknowledge risk when syncing non-stable channels.",
    )
    sync_parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help=f"Cache directory path (default: {DEFAULT_CACHE_DIR}).",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Search cached ToolCards and return JSONL records.",
    )
    search_parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help=f"Cache directory path (default: {DEFAULT_CACHE_DIR}).",
    )

    show_parser = subparsers.add_parser(
        "show",
        help="Show one cached ToolCard by tool ID slug.",
    )
    show_parser.add_argument(
        "tool_id",
        help="Tool ID slug to show (case-insensitive match).",
    )
    show_parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help=f"Cache directory path (default: {DEFAULT_CACHE_DIR}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and dispatch command handlers."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "sync":
        return run_sync(args)
    if args.command == "search":
        return run_search(Path(args.cache_dir))
    if args.command == "show":
        return run_show(Path(args.cache_dir), args.tool_id)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
