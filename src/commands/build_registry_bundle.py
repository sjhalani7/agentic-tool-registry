#!/usr/bin/env python3
"""Build a versioned stable-channel registry snapshot under dist/."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.utils.common_utils import iter_tool_dirs, load_json, sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = ROOT / "tools"
CHANNELS_ROOT = ROOT / "channels"
DIST_ROOT = ROOT / "dist"
REQUIRED_TOOL_FILES = ("toolcard.json", "toolspec.json", "verification.json")
CHANNEL_FILES = ("stable.json", "community.json", "experimental.json")


def run_validator() -> None:
    """Run the registry validator and abort bundling on failure."""
    cmd = [sys.executable, "-m", "src.commands.validate_toolcards"]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit("Bundling aborted: validate_toolcards.py failed.")


def git_short_sha() -> str:
    """Return the current git short SHA or a fallback when unavailable."""
    cmd = ["git", "rev-parse", "--short=12", "HEAD"]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return "nogit"


def collect_tool_records() -> dict[str, dict[str, Any]]:
    """Load and validate required per-tool files into an in-memory map."""
    records: dict[str, dict[str, Any]] = {}
    for tool_dir in iter_tool_dirs(TOOLS_ROOT):
        missing = [name for name in REQUIRED_TOOL_FILES if not (tool_dir / name).exists()]
        if missing:
            raise SystemExit(f"Bundling aborted: {tool_dir} missing {', '.join(missing)}")

        card = load_json(tool_dir / "toolcard.json")
        spec = load_json(tool_dir / "toolspec.json")
        verification = load_json(tool_dir / "verification.json")

        if not isinstance(card, dict) or not isinstance(spec, dict) or not isinstance(verification, dict):
            raise SystemExit(f"Bundling aborted: invalid JSON object in {tool_dir}")

        tool_id = card.get("id")
        if not isinstance(tool_id, str) or not tool_id:
            raise SystemExit(f"Bundling aborted: invalid toolcard id in {tool_dir / 'toolcard.json'}")

        records[tool_id] = {
            "toolcard": card,
            "toolspec": spec,
            "verification": verification,
        }

    if not records:
        raise SystemExit("Bundling aborted: no tools found.")
    return records


def load_channels() -> dict[str, list[str]]:
    """Load channel manifests and return channel-to-tool-id mappings."""
    channels: dict[str, list[str]] = {}
    for file_name in CHANNEL_FILES:
        channel_name = file_name.replace(".json", "")
        data = load_json(CHANNELS_ROOT / file_name)
        tools = data.get("tools") if isinstance(data, dict) else None
        if not isinstance(tools, list):
            raise SystemExit(f"Bundling aborted: channels/{file_name} has invalid tools list")
        if len(tools) != len(set(tools)):
            raise SystemExit(f"Bundling aborted: channels/{file_name} contains duplicate tool IDs")
        channels[channel_name] = tools
    return channels


def enforce_channel_consistency(all_tool_ids: set[str], channels: dict[str, list[str]]) -> None:
    """Ensure channel tool IDs are known and every tool appears in at least one channel."""
    referenced_ids = set().union(*[set(ids) for ids in channels.values()]) if channels else set()
    unknown = sorted(referenced_ids - all_tool_ids)
    if unknown:
        raise SystemExit(f"Bundling aborted: channel manifests reference unknown tool IDs: {unknown}")

    missing = sorted(all_tool_ids - referenced_ids)
    if missing:
        raise SystemExit(
            "Bundling aborted: every tool must appear in at least one channel; missing: "
            + ", ".join(missing)
        )


def ensure_stable_verified(stable_ids: list[str], records: dict[str, dict[str, Any]]) -> None:
    """Enforce verified publisher/status requirements for stable tools."""
    for tool_id in stable_ids:
        if tool_id not in records:
            raise SystemExit(f"Bundling aborted: stable channel references missing tool '{tool_id}'")
        record = records[tool_id]
        card = record["toolcard"]
        verification = record["verification"]
        publisher = card.get("publisher", {}) if isinstance(card, dict) else {}
        publisher_verified = isinstance(publisher, dict) and publisher.get("verified") is True
        verification_verified = verification.get("status") == "verified"
        if not publisher_verified or not verification_verified:
            raise SystemExit(
                f"Bundling aborted: stable tool '{tool_id}' is not verified (publisher.verified/status mismatch)"
            )


def bundle_version(created_at: datetime) -> str:
    """Generate a unique version string for a new bundle directory."""
    base = f"{created_at.strftime('%Y%m%dT%H%M%SZ')}-{git_short_sha()}"
    version = base
    suffix = 1
    while (DIST_ROOT / version).exists():
        version = f"{base}-{suffix:02d}"
        suffix += 1
    return version


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write JSONL records as one compact JSON object per line."""
    with path.open("w") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def build_bundle() -> Path:
    """Build a stable-channel snapshot bundle and return the output directory."""
    run_validator()
    records = collect_tool_records()
    channels = load_channels()
    all_tool_ids = set(records.keys())

    enforce_channel_consistency(all_tool_ids, channels)
    stable_ids = channels.get("stable", [])
    ensure_stable_verified(stable_ids, records)

    created_at = datetime.now(timezone.utc)
    version = bundle_version(created_at)
    out_dir = DIST_ROOT / version
    out_dir.mkdir(parents=True, exist_ok=False)

    toolcards = [records[tool_id]["toolcard"] for tool_id in stable_ids]
    toolspecs = [records[tool_id]["toolspec"] for tool_id in stable_ids]
    verifications = [records[tool_id]["verification"] for tool_id in stable_ids]

    toolcards_path = out_dir / "toolcards.bundle.jsonl"
    toolspecs_path = out_dir / "toolspecs.bundle.jsonl"
    verifications_path = out_dir / "verifications.bundle.jsonl"

    write_jsonl(toolcards_path, toolcards)
    write_jsonl(toolspecs_path, toolspecs)
    write_jsonl(verifications_path, verifications)

    artifact_paths = [toolcards_path, toolspecs_path, verifications_path]
    artifacts: dict[str, dict[str, Any]] = {}
    for artifact in artifact_paths:
        artifacts[artifact.name] = {
            "sha256": sha256_file(artifact),
            "bytes": artifact.stat().st_size,
        }

    manifest = {
        "bundle_version": version,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "source_commit": git_short_sha(),
        "channel": "stable",
        "tool_count": len(stable_ids),
        "tool_ids": stable_ids,
        "artifacts": artifacts,
    }
    write_json(out_dir / "manifest.json", manifest)

    return out_dir


def main() -> int:
    """Build the bundle and return a process exit code."""
    out_dir = build_bundle()
    print(f"Built registry bundle at: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
