#!/usr/bin/env python3
"""CLI for local registry sync and cache management."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common_utils import load_json, sha256_file, write_json

DEFAULT_SOURCE_DIR = Path("./dist")
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "agentic-tool-registry"
SUPPORTED_CHANNELS = {"stable", "community", "experimental"}


def discover_versions(source_dir: Path) -> list[str]:
    """Return available bundle versions from a local source directory."""
    if not source_dir.exists():
        raise SystemExit(f"sync failed: source directory not found: {source_dir}")
    if not source_dir.is_dir():
        raise SystemExit(f"sync failed: source path is not a directory: {source_dir}")

    versions = [
        path.name
        for path in source_dir.iterdir()
        if path.is_dir() and (path / "manifest.json").exists()
    ]
    versions.sort()
    if not versions:
        raise SystemExit(f"sync failed: no bundle versions with manifest.json found in {source_dir}")
    return versions


def resolve_version(source_dir: Path, requested_version: str | None) -> str:
    """Resolve an explicit or latest bundle version from source_dir."""
    versions = discover_versions(source_dir)
    if requested_version:
        if requested_version not in versions:
            raise SystemExit(
                f"sync failed: requested version '{requested_version}' not found in {source_dir}"
            )
        return requested_version
    return versions[-1]


def enforce_channel_risk(channel: str, allow_risky_channel: bool) -> None:
    """Enforce explicit acknowledgement for non-stable channel sync."""
    if channel not in SUPPORTED_CHANNELS:
        raise SystemExit(f"sync failed: unsupported channel '{channel}'")
    if channel != "stable" and not allow_risky_channel:
        raise SystemExit(
            "sync failed: non-stable channel requested; rerun with --allow-risky-channel to acknowledge risk"
        )


def verify_bundle(bundle_dir: Path, expected_channel: str) -> tuple[dict[str, Any], list[str]]:
    """Verify bundle manifest + checksums and return manifest with required artifact names."""
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"sync failed: missing manifest: {manifest_path}")

    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise SystemExit("sync failed: manifest.json must be a JSON object")

    manifest_channel = manifest.get("channel")
    if manifest_channel != expected_channel:
        raise SystemExit(
            f"sync failed: bundle channel '{manifest_channel}' does not match requested channel '{expected_channel}'"
        )

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise SystemExit("sync failed: manifest.artifacts must be a non-empty object")

    required_files: list[str] = []
    for artifact_name, metadata in sorted(artifacts.items()):
        artifact_path = bundle_dir / artifact_name
        if not artifact_path.exists():
            raise SystemExit(f"sync failed: missing artifact file: {artifact_path}")
        if not isinstance(metadata, dict):
            raise SystemExit(f"sync failed: manifest artifact metadata must be object for '{artifact_name}'")

        expected_sha = metadata.get("sha256")
        if not isinstance(expected_sha, str) or len(expected_sha) != 64: #SHA produced 256 bits=32 bytes, which is 2 hex ch 
            raise SystemExit(
                f"sync failed: manifest artifact '{artifact_name}' missing valid sha256 checksum"
            )
        actual_sha = sha256_file(artifact_path)
        if actual_sha != expected_sha:
            raise SystemExit(
                f"sync failed: checksum mismatch for '{artifact_name}' "
                f"(expected {expected_sha}, got {actual_sha})"
            )
        required_files.append(artifact_name)

    required_files.append("manifest.json")
    return manifest, required_files


def copy_files(src_dir: Path, dest_dir: Path, names: list[str]) -> None:
    """Copy selected files from src_dir to dest_dir."""
    for name in names:
        source = src_dir / name
        target = dest_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def cache_snapshot(
    source_dir: Path,
    version: str,
    artifact_names: list[str],
    cache_dir: Path,
) -> tuple[Path, bool]:
    """Copy artifacts into cache snapshot storage and return snapshot path + created flag."""
    snapshots_dir = cache_dir / "snapshots"
    snapshot_dir = snapshots_dir / version
    if snapshot_dir.exists():
        return snapshot_dir, False

    temp_dir = cache_dir / "tmp" / f"{version}-{os.getpid()}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    copy_files(source_dir / version, temp_dir, artifact_names)

    snapshots_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.rename(snapshot_dir)
    return snapshot_dir, True


def update_sync_state(
    cache_dir: Path,
    version: str,
    channel: str,
    source_dir: Path,
    snapshot_dir: Path,
    manifest: dict[str, Any],
) -> Path:
    """Write current sync metadata to the cache directory."""
    state = {
        "active_version": version,
        "channel": channel,
        "source_dir": str(source_dir),
        "snapshot_dir": str(snapshot_dir),
        "synced_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "manifest_created_at": manifest.get("created_at"),
        "manifest_source_commit": manifest.get("source_commit"),
    }
    state_path = cache_dir / "current.json"
    write_json(state_path, state)
    return state_path


def run_sync(args: argparse.Namespace) -> int:
    """Execute local bundle sync into cache."""
    source_dir = Path(args.source_dir).expanduser().resolve()
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    channel = args.channel

    enforce_channel_risk(channel, args.allow_risky_channel)
    version = resolve_version(source_dir, args.version)
    manifest, artifact_names = verify_bundle(source_dir / version, channel)
    snapshot_dir, created = cache_snapshot(source_dir, version, artifact_names, cache_dir)
    state_path = update_sync_state(cache_dir, version, channel, source_dir, snapshot_dir, manifest)

    if channel != "stable":
        print("WARNING: synced non-stable channel; use-at-your-own-risk.")

    status = "created" if created else "reused"
    print(f"sync complete: version={version} channel={channel} cache_snapshot={snapshot_dir} ({status})")
    print(f"sync state written: {state_path}")
    return 0


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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and dispatch command handlers."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "sync":
        parser.print_help()
        return 1
    return run_sync(args)


if __name__ == "__main__":
    sys.exit(main())
