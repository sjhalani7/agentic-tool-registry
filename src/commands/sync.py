#!/usr/bin/env python3
"""Sync local or remote registry bundles into cache snapshots."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from src.utils.common_utils import load_json, sha256_file, write_json

DEFAULT_SOURCE_DIR = Path("./dist")
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "agentic-tool-registry"
DEFAULT_REMOTE_BASE_URL = "https://sjhalani7.github.io/agentic-tool-registry"
SUPPORTED_CHANNELS = {"stable", "community", "experimental"}
SUPPORTED_SOURCE_MODES = {"remote", "local"}


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


def resolve_local_version(source_dir: Path, requested_version: str | None) -> str:
    """Resolve an explicit or latest bundle version from a local source directory."""
    versions = discover_versions(source_dir)
    if requested_version:
        if requested_version not in versions:
            raise SystemExit(
                f"sync failed: requested version '{requested_version}' not found in {source_dir}"
            )
        return requested_version
    return versions[-1]


def normalize_remote_base_url(remote_base_url: str) -> str:
    """Validate and normalize remote bundle base URL."""
    value = remote_base_url.strip().rstrip("/")
    if not value:
        raise SystemExit("sync failed: remote base URL is required when source=remote")

    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise SystemExit("sync failed: remote base URL must be a valid http(s) URL")

    if parsed.scheme == "http":
        host = (parsed.hostname or "").lower()
        if host not in {"localhost", "127.0.0.1"}:
            raise SystemExit("sync failed: remote base URL must use https (except localhost testing)")

    return value


def fetch_remote_json(url: str, label: str) -> dict[str, Any]:
    """Download and parse a JSON object from remote URL."""
    try:
        with urlopen(url, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        raise SystemExit(f"sync failed: {label} request failed ({exc.code}) at {url}") from exc
    except URLError as exc:
        raise SystemExit(f"sync failed: {label} request failed at {url} ({exc.reason})") from exc

    try:
        data = json.loads(payload)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"sync failed: malformed {label} JSON at {url} ({exc})") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"sync failed: {label} must be a JSON object at {url}")
    return data


def download_remote_file(url: str, path: Path) -> None:
    """Download one remote file to path."""
    try:
        with urlopen(url, timeout=60) as response:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as handle:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    handle.write(chunk)
    except HTTPError as exc:
        raise SystemExit(f"sync failed: download failed ({exc.code}) at {url}") from exc
    except URLError as exc:
        raise SystemExit(f"sync failed: download failed at {url} ({exc.reason})") from exc


def extract_remote_versions(index: dict[str, Any]) -> list[str]:
    """Extract and normalize bundle versions from a dist index payload."""
    raw_versions = index.get("versions")
    versions: list[str] = []
    if isinstance(raw_versions, list):
        for entry in raw_versions:
            if isinstance(entry, str):
                versions.append(entry)
            elif isinstance(entry, dict):
                version = entry.get("version")
                if isinstance(version, str) and version:
                    versions.append(version)

    return sorted(set(versions))


def resolve_remote_version(remote_base_url: str, requested_version: str | None) -> str:
    """Resolve explicit or latest bundle version from remote index."""
    index = fetch_remote_json(f"{remote_base_url}/index.json", "remote index")
    versions = extract_remote_versions(index)
    if not versions:
        raise SystemExit("sync failed: remote index has no versions")

    if requested_version:
        if requested_version not in versions:
            raise SystemExit(
                f"sync failed: requested version '{requested_version}' not found in remote index"
            )
        return requested_version

    latest = index.get("latest")
    if isinstance(latest, str) and latest in versions:
        return latest
    return versions[-1]


def download_remote_bundle(remote_base_url: str, version: str, temp_dir: Path) -> Path:
    """Download manifest and listed artifacts for a remote bundle version."""
    bundle_dir = temp_dir / version
    manifest_url = f"{remote_base_url}/{version}/manifest.json"
    manifest_path = bundle_dir / "manifest.json"
    download_remote_file(manifest_url, manifest_path)

    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise SystemExit(f"sync failed: manifest.json must be a JSON object ({manifest_url})")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise SystemExit(f"sync failed: manifest.artifacts must be a non-empty object ({manifest_url})")

    for artifact_name in sorted(artifacts.keys()):
        if not isinstance(artifact_name, str) or not artifact_name:
            raise SystemExit(f"sync failed: manifest contains invalid artifact name ({manifest_url})")
        artifact_url = f"{remote_base_url}/{version}/{artifact_name}"
        download_remote_file(artifact_url, bundle_dir / artifact_name)

    return bundle_dir


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
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
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
    bundle_dir: Path,
    version: str,
    artifact_names: list[str],
    cache_dir: Path,
) -> tuple[Path, bool]:
    """Copy bundle files into cache snapshot storage and return snapshot path + created flag."""
    snapshots_dir = cache_dir / "snapshots"
    snapshot_dir = snapshots_dir / version
    if snapshot_dir.exists():
        return snapshot_dir, False

    temp_dir = cache_dir / "tmp" / f"{version}-{os.getpid()}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    copy_files(bundle_dir, temp_dir, artifact_names)

    snapshots_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.rename(snapshot_dir)
    return snapshot_dir, True


def update_sync_state(
    cache_dir: Path,
    version: str,
    channel: str,
    source_mode: str,
    source_ref: str,
    snapshot_dir: Path,
    manifest: dict[str, Any],
) -> Path:
    """Write current sync metadata to the cache directory."""
    state = {
        "active_version": version,
        "channel": channel,
        "source_mode": source_mode,
        "source_ref": source_ref,
        "snapshot_dir": str(snapshot_dir),
        "synced_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "manifest_created_at": manifest.get("created_at"),
        "manifest_source_commit": manifest.get("source_commit"),
    }
    state_path = cache_dir / "current.json"
    write_json(state_path, state)
    return state_path


def run_sync(args: argparse.Namespace) -> int:
    """Execute local or remote bundle sync into cache."""
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    channel = args.channel
    source_mode = args.source

    if source_mode not in SUPPORTED_SOURCE_MODES:
        raise SystemExit(f"sync failed: unsupported source mode '{source_mode}'")

    enforce_channel_risk(channel, args.allow_risky_channel)

    remote_temp_root: Path | None = None
    try:
        if source_mode == "local":
            source_dir = Path(args.source_dir).expanduser().resolve()
            version = resolve_local_version(source_dir, args.version)
            bundle_dir = source_dir / version
            source_ref = str(source_dir)
        else:
            remote_base_url = normalize_remote_base_url(args.remote_base_url)
            version = resolve_remote_version(remote_base_url, args.version)
            remote_temp_root = cache_dir / "tmp" / f"remote-{version}-{os.getpid()}"
            bundle_dir = download_remote_bundle(remote_base_url, version, remote_temp_root)
            source_ref = remote_base_url

        manifest, artifact_names = verify_bundle(bundle_dir, channel)
        snapshot_dir, created = cache_snapshot(bundle_dir, version, artifact_names, cache_dir)
        state_path = update_sync_state(
            cache_dir,
            version,
            channel,
            source_mode,
            source_ref,
            snapshot_dir,
            manifest,
        )
    finally:
        if remote_temp_root is not None and remote_temp_root.exists():
            shutil.rmtree(remote_temp_root, ignore_errors=True)

    if channel != "stable":
        print("WARNING: synced non-stable channel; use-at-your-own-risk.")

    status = "created" if created else "reused"
    print(
        f"sync complete: source={source_mode} version={version} "
        f"channel={channel} cache_snapshot={snapshot_dir} ({status})"
    )
    print(f"sync state written: {state_path}")
    return 0
