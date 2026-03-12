#!/usr/bin/env python3
"""Interactively scaffold a new tool directory and required manifests."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*/[a-z0-9]+(?:-[a-z0-9]+)*$")
CAPABILITY_RE = re.compile(r"^[a-z0-9-]{1,32}$")
CURRENCY_RE = re.compile(r"^[A-Z0-9]{3,5}$")
AUTH_TYPES = ("none", "api_key", "oauth", "cli_login", "signing_key", "x402")
INTERFACE_TYPES = ("http", "cli", "mcp")
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write human-editable JSON with deterministic key order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _prompt_text(
    label: str,
    *,
    required: bool = True,
    default: str | None = None,
    max_length: int | None = None,
) -> str:
    """Prompt for one text value with optional validation constraints."""
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{label}{suffix}: ").strip()
        value = raw if raw else (default or "")
        if required and not value:
            print("Value is required.")
            continue
        if max_length is not None and len(value) > max_length:
            print(f"Value exceeds max length {max_length}.")
            continue
        return value


def _prompt_bool(label: str, *, default: bool = False) -> bool:
    """Prompt for a yes/no decision."""
    default_label = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} [{default_label}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please enter y or n.")


def _prompt_choice(label: str, options: tuple[str, ...], *, default: str | None = None) -> str:
    """Prompt for one value from a fixed set."""
    options_label = "/".join(options)
    normalized_options = {option.casefold(): option for option in options}
    while True:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{label} ({options_label}){suffix}: ").strip()
        value = raw or (default or "")
        normalized_value = value.casefold()
        if normalized_value in normalized_options:
            return normalized_options[normalized_value]
        print(f"Choose one of: {options_label}")


def _prompt_slug_id() -> str:
    """Prompt for a normalized publisher/tool slug ID."""
    while True:
        raw = input("Tool ID slug (publisher/tool): ").strip().casefold()
        if not raw:
            print("Tool ID is required.")
            continue
        if not SLUG_RE.match(raw):
            print("Tool ID must match publisher/tool slug format.")
            continue
        return raw


def _prompt_capabilities() -> list[str]:
    """Prompt for one or more capability slugs."""
    while True:
        raw = input("Capabilities (comma-separated lowercase slugs): ").strip()
        items = [item.strip().casefold() for item in raw.split(",") if item.strip()]
        if not items:
            print("At least one capability is required.")
            continue
        deduped: list[str] = []
        seen: set[str] = set()
        valid = True
        for item in items:
            if not CAPABILITY_RE.match(item):
                print(f"Invalid capability '{item}'. Use lowercase letters/numbers/hyphen only.")
                valid = False
                break
            if item in seen:
                continue
            deduped.append(item)
            seen.add(item)
        if valid and deduped:
            if len(deduped) > 12:
                print("Capabilities cannot exceed 12 entries.")
                continue
            return deduped


def _prompt_url(label: str, *, default: str | None = None) -> str:
    """Prompt for an HTTPS URL."""
    while True:
        value = _prompt_text(label, default=default)
        if not value.startswith("https://"):
            print("URL must start with https://")
            continue
        return value


def _normalize_host(host: str | None) -> str:
    """Normalize hostname for first-party comparison."""
    if not host:
        return ""
    return host.lower().rstrip(".")


def _get_registrable_domain(host: str) -> str:
    """Approximate registrable domain using the final two labels."""
    parts = host.split(".")
    if len(parts) < 2:
        return host
    return ".".join(parts[-2:])


def _is_first_party_url(url: str, publisher_url: str) -> bool:
    """Return True when a URL appears first-party for the publisher domain."""
    url_host = _normalize_host(urlparse(url).hostname)
    publisher_host = _normalize_host(urlparse(publisher_url).hostname)
    if not url_host or not publisher_host:
        return False
    if url_host == publisher_host or url_host.endswith("." + publisher_host):
        return True
    return _get_registrable_domain(url_host) == _get_registrable_domain(publisher_host)


def _prompt_external_docs(publisher_url: str) -> list[dict[str, str]]:
    """Prompt for one or more external documentation entries."""
    docs: list[dict[str, str]] = []
    while True:
        url = _prompt_url("Primary official docs URL (first-party)")
        if not _is_first_party_url(url, publisher_url):
            print("Primary docs URL must be first-party for publisher domain.")
            continue
        description = _prompt_text("Primary doc description", default="Official docs", max_length=128)
        docs.append({"description": description, "url": url})
        break

    while True:
        if not _prompt_bool("Add another external doc?", default=False):
            return docs
        url = _prompt_url("Additional external doc URL")
        description = _prompt_text("Additional doc description", default="Reference docs", max_length=128)
        docs.append({"description": description, "url": url})


def _prompt_currency() -> str:
    """Prompt for currency code matching ToolCard schema."""
    while True:
        value = _prompt_text("Currency code (USD, USDC, etc.)").upper()
        if CURRENCY_RE.match(value):
            return value
        print("Currency must be 3-5 uppercase alphanumeric characters.")


def _prompt_http_spec() -> dict[str, Any]:
    """Prompt for HTTP interface details."""
    base_url = _prompt_url("HTTP base_url")
    endpoints: list[dict[str, Any]] = []
    while True:
        name = _prompt_text("Endpoint name", max_length=64)
        method = _prompt_choice("HTTP method", HTTP_METHODS, default="GET")
        path = _prompt_text("Endpoint path (for example /v1/items)", max_length=256)
        description = _prompt_text("Endpoint description", max_length=512)
        query_raw = _prompt_text("Query params (comma-separated, optional)", required=False)
        query_params = [item.strip() for item in query_raw.split(",") if item.strip()]
        endpoint: dict[str, Any] = {
            "name": name,
            "method": method,
            "path": path,
            "description": description,
        }
        if query_params:
            endpoint["query_params"] = query_params
        endpoints.append(endpoint)
        if not _prompt_bool("Add another HTTP endpoint?", default=False):
            break
    return {"base_url": base_url, "endpoints": endpoints}


def _prompt_cli_spec() -> tuple[dict[str, Any], str]:
    """Prompt for CLI interface details and official repository URL."""
    binary = _prompt_text("CLI binary (for example mytool)")
    official_repo_url = _prompt_url("Official CLI repository URL")
    install = _prompt_text("CLI install instructions", required=False)
    commands: list[dict[str, str]] = []
    while True:
        name = _prompt_text("CLI command name", max_length=64)
        usage = _prompt_text("CLI command usage", max_length=256)
        description = _prompt_text("CLI command description", max_length=512)
        example = _prompt_text("CLI command example (optional)", required=False, max_length=512)
        command: dict[str, str] = {"name": name, "usage": usage, "description": description}
        if example:
            command["example"] = example
        commands.append(command)
        if not _prompt_bool("Add another CLI command?", default=False):
            break
    result: dict[str, Any] = {"binary": binary, "commands": commands}
    if install:
        result["install"] = install
    return result, official_repo_url


def _prompt_mcp_spec() -> dict[str, Any]:
    """Prompt for MCP interface details."""
    server_url = _prompt_url("MCP server_url")
    capabilities = _prompt_capabilities()
    return {"server_url": server_url, "capabilities": capabilities}


def _build_toolcard(tool_id: str, publisher_slug: str, tool_slug: str) -> dict[str, Any]:
    """Collect interactive inputs for a ToolCard payload."""
    _ = publisher_slug, tool_slug
    name = _prompt_text("Tool display name", max_length=80)
    publisher_name = _prompt_text("Publisher name")
    publisher_url = _prompt_url("Publisher URL")
    capabilities = _prompt_capabilities()
    description = _prompt_text("Tool description", max_length=256)
    is_paid = _prompt_bool("Is payment required?", default=False)
    if is_paid:
        pricing = _prompt_text(
            "ToolCard pricing (describe pricing; prefer official HTTPS pricing URL when available)",
            max_length=256,
        )
        currency = _prompt_currency()
        purl_supported = _prompt_bool("Supports Stripe purl payment flow?", default=False)
    else:
        pricing = "Free"
        currency = "USD"
        purl_supported = False
    return {
        "id": tool_id,
        "name": name,
        "publisher": {
            "name": publisher_name,
            "url": publisher_url,
            "verified": False,
        },
        "capabilities": capabilities,
        "description": description,
        "pricing": pricing,
        "currency": currency,
        "payment": {
            "is_paid": is_paid,
            "purl_supported": purl_supported,
        },
    }


def _build_toolspec(tool_id: str, publisher_url: str) -> tuple[dict[str, Any], str, str | None]:
    """Collect interactive inputs for a ToolSpec payload."""
    spec_type = _prompt_choice("Tool interface type", INTERFACE_TYPES)
    summary = _prompt_text("Tool summary", max_length=512)
    auth_type = _prompt_choice("Auth type", AUTH_TYPES, default="none")
    auth_instructions = _prompt_text("Auth instructions", max_length=512)
    auth: dict[str, Any] = {"type": auth_type, "instructions": auth_instructions}
    if auth_type == "x402":
        auth["payment_client"] = _prompt_choice("x402 payment client", ("purl", "custom"), default="purl")

    spec: dict[str, Any] = {
        "tool_id": tool_id,
        "type": spec_type,
        "summary": summary,
        "auth": auth,
        "external_docs": _prompt_external_docs(publisher_url),
    }

    if spec_type == "http":
        spec["http"] = _prompt_http_spec()
        return spec, spec_type, None
    elif spec_type == "cli":
        cli_spec, official_repo_url = _prompt_cli_spec()
        spec["cli"] = cli_spec
        return spec, spec_type, official_repo_url
    else:
        spec["mcp"] = _prompt_mcp_spec()
        return spec, spec_type, None


def _build_verification(
    tool_id: str,
    spec_type: str,
    toolspec: dict[str, Any],
    publisher_url: str,
    cli_repo_url: str | None,
) -> dict[str, Any]:
    """Build pending-moderation verification payload without contributor prompts."""
    external_docs = toolspec.get("external_docs", [])
    official_docs_url = external_docs[0]["url"]

    external_references: list[str] = []
    for entry in external_docs:
        url = entry.get("url")
        if isinstance(url, str) and url and url not in external_references:
            external_references.append(url)
    if publisher_url not in external_references:
        external_references.append(publisher_url)

    evidence: dict[str, Any] = {
        "official_docs_url": official_docs_url,
        "external_references": external_references[:8],
        "notes": "Pending manual moderator review.",
    }
    if spec_type == "cli":
        if not cli_repo_url:
            raise SystemExit("init-tool failed: official CLI repository URL is required for cli tools")
        evidence["official_repo_url"] = cli_repo_url

    reviewed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "tool_id": tool_id,
        "status": "revoked",
        "reviewed_by": "pending-moderator",
        "reviewed_at": reviewed_at,
        "evidence": evidence,
    }


def _ensure_paths_available(tool_dir: Path) -> None:
    """Fail when scaffold target already exists."""
    if tool_dir.exists():
        raise SystemExit(f"init-tool failed: target directory already exists: {tool_dir}")


def _assert_unique_tool_name(tools_root: Path, proposed_name: str) -> None:
    """Fail when proposed display name matches an existing toolcard name."""
    proposed = proposed_name.strip().casefold()
    for card_path in sorted(tools_root.glob("*/*/toolcard.json")):
        try:
            payload = json.loads(card_path.read_text())
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        existing_name = payload.get("name")
        if isinstance(existing_name, str) and existing_name.strip().casefold() == proposed:
            raise SystemExit(
                f"init-tool failed: tool name '{proposed_name}' already exists in {card_path}"
            )


def run_init_tool(args: argparse.Namespace) -> int:
    """Interactively scaffold a new tool folder and required JSON manifests."""
    if not args.interactive:
        raise SystemExit("init-tool failed: use --interactive for MVP scaffolding mode")

    tools_root = Path("./tools").resolve()
    tool_id = _prompt_slug_id()
    publisher_slug, tool_slug = tool_id.split("/", 1)
    tool_dir = tools_root / publisher_slug / tool_slug
    _ensure_paths_available(tool_dir)

    print(f"Scaffolding {tool_id} in {tool_dir}")
    toolcard = _build_toolcard(tool_id, publisher_slug, tool_slug)
    _assert_unique_tool_name(tools_root, toolcard["name"])
    toolspec, spec_type, cli_repo_url = _build_toolspec(tool_id, toolcard["publisher"]["url"])
    verification = _build_verification(
        tool_id,
        spec_type,
        toolspec,
        toolcard["publisher"]["url"],
        cli_repo_url,
    )

    _write_json(tool_dir / "toolcard.json", toolcard)
    _write_json(tool_dir / "toolspec.json", toolspec)
    _write_json(tool_dir / "verification.json", verification)

    print(f"Created tool scaffold at: {tool_dir}")
    print("Review generated manifests and open a PR when ready.")
    return 0
