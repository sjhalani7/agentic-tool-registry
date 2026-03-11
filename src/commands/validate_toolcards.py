#!/usr/bin/env python3
"""Validate ToolCard + ToolSpec + verification files and enforce repo invariants."""
from __future__ import annotations

import ipaddress
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List
from urllib.parse import urlparse

from src.utils.common_utils import iter_tool_dirs

ROOT = Path(__file__).resolve().parents[2]
TOOLCARD_SCHEMA_PATH = ROOT / "schemas" / "toolcard.schema.json"
TOOLSPEC_SCHEMA_PATH = ROOT / "schemas" / "toolspec.schema.json"
VERIFICATION_SCHEMA_PATH = ROOT / "schemas" / "tool-verification.schema.json"
TOOLS_ROOT = ROOT / "tools"
CHANNELS_ROOT = ROOT / "channels"
SIZE_LIMIT = 2048  # bytes for toolcards

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*/[a-z0-9]+(?:-[a-z0-9]+)*$")
CAPABILITY_RE = re.compile(r"^[a-z0-9-]{1,32}$")
CURRENCY_RE = re.compile(r"^[A-Z0-9]{3,5}$")
SHORTENER_HOSTS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
    "ow.ly",
    "is.gd",
    "buff.ly",
    "rebrand.ly",
    "cutt.ly",
    "shorturl.at",
    "lnkd.in",
    "rb.gy",
    "tiny.cc",
}


def load_schema(path: Path) -> dict:
    """Load a JSON schema file from disk."""
    with path.open() as fh:
        return json.load(fh)


def load_json(path: Path, failures: List[str]) -> Any:
    """Load a JSON document and append parse failures to the shared list."""
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        failures.append(f"{path}: invalid JSON ({exc})")
        return None


def normalize_host(host: str | None) -> str:
    """Normalize a hostname for consistent comparisons."""
    if not host:
        return ""
    return host.lower().rstrip(".")


def get_registrable_domain(host: str) -> str:
    """Approximate a registrable domain by taking the last two labels."""
    parts = host.split(".")
    if len(parts) < 2:
        return host
    return ".".join(parts[-2:])


def is_ip_host(host: str) -> bool:
    """Return True when the host is a raw IPv4/IPv6 address."""
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def is_shortener_host(host: str) -> bool:
    """Return True when the host matches a known URL shortener."""
    return any(host == entry or host.endswith("." + entry) for entry in SHORTENER_HOSTS)


def is_first_party_host(host: str, publisher_host: str) -> bool:
    """Check whether host belongs to the same first-party domain as publisher_host."""
    if not host or not publisher_host:
        return False
    if host == publisher_host or host.endswith("." + publisher_host):
        return True
    return get_registrable_domain(host) == get_registrable_domain(publisher_host)


def parse_host(url: str) -> str:
    """Extract and normalize the hostname from a URL string."""
    if not isinstance(url, str) or not url:
        return ""
    return normalize_host(urlparse(url).hostname)


def is_iso8601_utc(value: Any) -> bool:
    """Validate that a value is an ISO8601 UTC timestamp ending in Z."""
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_https_url(url: Any, label: str) -> List[str]:
    """Validate URL scheme, host quality, and shortener/IP restrictions."""
    errors: List[str] = []
    if not isinstance(url, str) or not url:
        return [f"{label} must be a non-empty URL string"]

    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        errors.append(f"{label} must use https")

    host = normalize_host(parsed.hostname)
    if not host:
        errors.append(f"{label} must include a valid host")
        return errors

    if is_ip_host(host):
        errors.append(f"{label} must not use a raw IP host")
    if is_shortener_host(host):
        errors.append(f"{label} must not use URL shortener host '{host}'")

    return errors


def validate_channels(tool_ids: set[str], verified_tool_ids: set[str]) -> List[str]:
    """Validate channel manifest structure and verified-only tool membership."""
    failures: List[str] = []
    expected_files = {
        "index.json",
        "stable.json",
        "community.json",
        "experimental.json",
    }

    if not CHANNELS_ROOT.exists():
        failures.append(f"{CHANNELS_ROOT}: missing channels directory")
        return failures

    channel_files = {p.name for p in CHANNELS_ROOT.glob("*.json")}
    missing = sorted(expected_files - channel_files)
    for name in missing:
        failures.append(f"{CHANNELS_ROOT / name}: missing channel manifest")

    index_path = CHANNELS_ROOT / "index.json"
    if index_path.exists():
        index_data = load_json(index_path, failures)
        if isinstance(index_data, dict):
            channels = index_data.get("channels", [])
            names = [c.get("name") for c in channels if isinstance(c, dict)]
            if sorted(names) != ["community", "experimental", "stable"]:
                failures.append(f"{index_path}: channels index must include stable, community, experimental")

    for name in ["stable", "community", "experimental"]:
        path = CHANNELS_ROOT / f"{name}.json"
        if not path.exists():
            continue

        data = load_json(path, failures)
        if not isinstance(data, dict):
            continue

        if data.get("channel") != name:
            failures.append(f"{path}: channel field must be '{name}'")
        tools = data.get("tools")
        if not isinstance(tools, list):
            failures.append(f"{path}: tools must be an array")
            continue
        if len(tools) != len(set(tools)):
            failures.append(f"{path}: duplicate tool IDs are not allowed")
        if name == "stable" and not tools:
            failures.append(f"{path}: stable channel must contain at least one tool")

        for tool_id in tools:
            if tool_id not in tool_ids:
                failures.append(f"{path}: unknown tool id '{tool_id}'")
            elif tool_id not in verified_tool_ids:
                failures.append(f"{path}: tool id '{tool_id}' is not verified and cannot be published in channels")

    return failures


def manual_validate_card(card: dict) -> List[str]:
    """Perform fallback ToolCard validation when jsonschema is unavailable."""
    errors: List[str] = []

    def expect(condition: bool, msg: str) -> None:
        if not condition:
            errors.append(msg)

    expect(isinstance(card, dict), "Card must be a JSON object")
    if not isinstance(card, dict):
        return errors

    required = [
        "id",
        "name",
        "publisher",
        "capabilities",
        "description",
        "pricing",
        "currency",
        "payment",
    ]
    for field in required:
        expect(field in card, f"Missing field: {field}")

    card_id = card.get("id", "")
    expect(isinstance(card_id, str) and SLUG_RE.match(card_id or ""), "id must be publisher/tool slug")
    expect(isinstance(card.get("name"), str) and 1 <= len(card["name"]) <= 80, "name must be 1-80 chars")

    publisher = card.get("publisher")
    expect(isinstance(publisher, dict), "publisher must be object")
    if isinstance(publisher, dict):
        for key in ["name", "url", "verified"]:
            expect(key in publisher, f"publisher.{key} required")
        expect(isinstance(publisher.get("name"), str) and publisher["name"], "publisher.name must be non-empty string")
        expect(isinstance(publisher.get("url"), str), "publisher.url must be string")
        expect(isinstance(publisher.get("verified"), bool), "publisher.verified must be boolean")

    caps = card.get("capabilities")
    expect(isinstance(caps, list) and caps, "capabilities must be non-empty array")
    if isinstance(caps, list):
        expect(len(caps) <= 12, "capabilities must list <=12 entries")
        seen = set()
        for cap in caps:
            expect(isinstance(cap, str) and CAPABILITY_RE.match(cap or ""), "capabilities must be lowercase slugs")
            expect(cap not in seen, "capabilities entries must be unique")
            seen.add(cap)

    description = card.get("description", "")
    expect(isinstance(description, str) and len(description) <= 256, "description must be <=256 chars")

    payment = card.get("payment")
    expect(isinstance(payment, dict), "payment must be object")
    if isinstance(payment, dict):
        expect("is_paid" in payment, "payment.is_paid required")
        expect(isinstance(payment.get("is_paid"), bool), "payment.is_paid must be boolean")
        if "purl_supported" in payment:
            expect(isinstance(payment.get("purl_supported"), bool), "payment.purl_supported must be boolean when provided")

    pricing = card.get("pricing", "")
    expect(isinstance(pricing, str) and pricing, "pricing must be non-empty string")
    currency = card.get("currency", "")
    expect(isinstance(currency, str) and CURRENCY_RE.match(currency or ""), "currency must be ISO/crypto ticker")

    return errors


def manual_validate_spec(spec: dict, expected_id: str) -> List[str]:
    """Perform fallback ToolSpec validation when jsonschema is unavailable."""
    errors: List[str] = []

    def expect(condition: bool, msg: str) -> None:
        if not condition:
            errors.append(msg)

    expect(isinstance(spec, dict), "Spec must be a JSON object")
    if not isinstance(spec, dict):
        return errors

    required = ["tool_id", "type", "summary", "auth", "external_docs"]
    for field in required:
        expect(field in spec, f"Missing field: {field}")

    tool_id = spec.get("tool_id", "")
    expect(tool_id == expected_id, f"tool_id must match ToolCard id ({expected_id})")
    expect(isinstance(tool_id, str) and SLUG_RE.match(tool_id or ""), "tool_id must be a slug")

    expect(spec.get("type") in {"http", "cli", "mcp"}, "type must be http|cli|mcp")
    summary = spec.get("summary", "")
    expect(isinstance(summary, str) and len(summary) <= 512, "summary must be <=512 chars")

    auth = spec.get("auth")
    expect(isinstance(auth, dict), "auth must be object")
    if isinstance(auth, dict):
        expect(auth.get("type") in {"none", "api_key", "oauth", "cli_login", "signing_key", "x402"}, "auth.type invalid")
        instructions = auth.get("instructions", "")
        expect(isinstance(instructions, str) and instructions, "auth.instructions required")
        if "payment_client" in auth:
            expect(auth.get("payment_client") in {"purl", "custom"}, "auth.payment_client must be purl|custom")
        if auth.get("type") == "x402":
            expect(auth.get("payment_client") in {"purl", "custom"}, "auth.payment_client required for x402")

    docs = spec.get("external_docs")
    expect(isinstance(docs, list) and docs, "external_docs must be non-empty array")
    if isinstance(docs, list):
        for doc in docs:
            expect(isinstance(doc, dict), "external_docs entries must be objects")
            if isinstance(doc, dict):
                expect("description" in doc and isinstance(doc["description"], str), "external_docs.description required")
                expect("url" in doc and isinstance(doc["url"], str), "external_docs.url required")

    spec_type = spec.get("type")
    if spec_type == "http":
        http = spec.get("http")
        expect(isinstance(http, dict), "http object required for type=http")
        if isinstance(http, dict):
            expect("base_url" in http, "http.base_url required")
            endpoints = http.get("endpoints")
            expect(isinstance(endpoints, list) and endpoints, "http.endpoints must be non-empty array")
    elif spec_type == "cli":
        cli = spec.get("cli")
        expect(isinstance(cli, dict), "cli object required for type=cli")
        if isinstance(cli, dict):
            expect("binary" in cli, "cli.binary required")
            cmds = cli.get("commands")
            expect(isinstance(cmds, list) and cmds, "cli.commands must be non-empty array")
    elif spec_type == "mcp":
        mcp = spec.get("mcp")
        expect(isinstance(mcp, dict), "mcp object required for type=mcp")
        if isinstance(mcp, dict):
            expect("server_url" in mcp, "mcp.server_url required")
            expect(isinstance(mcp.get("capabilities"), list) and mcp["capabilities"], "mcp.capabilities required")

    return errors


def manual_validate_verification(verification: dict, expected_id: str, spec_type: str) -> List[str]:
    """Perform fallback verification record checks without jsonschema."""
    errors: List[str] = []

    def expect(condition: bool, msg: str) -> None:
        if not condition:
            errors.append(msg)

    expect(isinstance(verification, dict), "verification must be a JSON object")
    if not isinstance(verification, dict):
        return errors

    required = ["tool_id", "status", "reviewed_by", "reviewed_at", "evidence"]
    for field in required:
        expect(field in verification, f"Missing field: {field}")

    tool_id = verification.get("tool_id", "")
    expect(isinstance(tool_id, str) and SLUG_RE.match(tool_id or ""), "verification.tool_id must be a slug")
    expect(tool_id == expected_id, f"verification.tool_id must match ToolCard id ({expected_id})")
    expect(verification.get("status") in {"verified", "revoked"}, "verification.status must be verified|revoked")
    expect(isinstance(verification.get("reviewed_by"), str) and verification.get("reviewed_by"), "reviewed_by required")
    expect(isinstance(verification.get("reviewed_at"), str) and verification.get("reviewed_at"), "reviewed_at required")

    evidence = verification.get("evidence")
    expect(isinstance(evidence, dict), "verification.evidence must be object")
    if isinstance(evidence, dict):
        expect(
            isinstance(evidence.get("official_docs_url"), str) and evidence.get("official_docs_url"),
            "verification.evidence.official_docs_url required",
        )
        refs = evidence.get("external_references")
        expect(isinstance(refs, list) and refs, "verification.evidence.external_references must be non-empty array")
        expect(isinstance(evidence.get("notes"), str) and evidence.get("notes"), "verification.evidence.notes required")
        if spec_type == "cli":
            expect(
                isinstance(evidence.get("official_repo_url"), str) and evidence.get("official_repo_url"),
                "verification.evidence.official_repo_url required for cli tools",
            )

    return errors


def validate_tool_policies(card: dict, spec: dict, verification: dict, expected_slug: str) -> List[str]:
    """Apply cross-file policy checks not enforced by JSON schema alone."""
    errors: List[str] = []

    def expect(condition: bool, msg: str) -> None:
        if not condition:
            errors.append(msg)

    card_id = card.get("id")
    spec_id = spec.get("tool_id")
    verification_id = verification.get("tool_id")
    spec_type = spec.get("type")

    expect(card_id == expected_slug, f"toolcard.id must match directory slug '{expected_slug}'")
    expect(spec_id == expected_slug, f"toolspec.tool_id must match directory slug '{expected_slug}'")
    expect(verification_id == expected_slug, f"verification.tool_id must match directory slug '{expected_slug}'")
    expect(card_id == spec_id == verification_id, "tool IDs must match across toolcard/toolspec/verification")

    expect(verification.get("status") == "verified", "verification.status must be 'verified' for merged tools")
    expect(is_iso8601_utc(verification.get("reviewed_at")), "verification.reviewed_at must be ISO8601 UTC")

    publisher = card.get("publisher", {})
    if isinstance(publisher, dict):
        expect(
            publisher.get("verified") is True,
            "toolcard.publisher.verified must be true for merged tools",
        )

    evidence = verification.get("evidence", {})
    publisher_url = publisher.get("url", "") if isinstance(publisher, dict) else ""
    publisher_host = parse_host(publisher_url)

    for msg in validate_https_url(publisher_url, "publisher.url"):
        errors.append(msg)

    docs = spec.get("external_docs", [])
    doc_hosts: List[str] = []
    if isinstance(docs, list):
        for idx, doc in enumerate(docs):
            if not isinstance(doc, dict):
                continue
            url = doc.get("url")
            for msg in validate_https_url(url, f"toolspec.external_docs[{idx}].url"):
                errors.append(msg)
            host = parse_host(url if isinstance(url, str) else "")
            if host:
                doc_hosts.append(host)

    if spec_type == "http":
        http_data = spec.get("http", {})
        if isinstance(http_data, dict):
            for msg in validate_https_url(http_data.get("base_url"), "toolspec.http.base_url"):
                errors.append(msg)
    elif spec_type == "mcp":
        mcp_data = spec.get("mcp", {})
        if isinstance(mcp_data, dict):
            for msg in validate_https_url(mcp_data.get("server_url"), "toolspec.mcp.server_url"):
                errors.append(msg)

    if isinstance(evidence, dict):
        official_docs_url = evidence.get("official_docs_url")
        for msg in validate_https_url(official_docs_url, "verification.evidence.official_docs_url"):
            errors.append(msg)

        official_docs_host = parse_host(official_docs_url if isinstance(official_docs_url, str) else "")
        if publisher_host and official_docs_host:
            expect(
                is_first_party_host(official_docs_host, publisher_host),
                "verification.evidence.official_docs_url must be first-party for publisher domain",
            )

        official_repo_url = evidence.get("official_repo_url")
        if official_repo_url is not None:
            for msg in validate_https_url(official_repo_url, "verification.evidence.official_repo_url"):
                errors.append(msg)

        if spec_type == "cli":
            expect(
                isinstance(official_repo_url, str) and official_repo_url,
                "verification.evidence.official_repo_url is required for cli tools",
            )

        refs = evidence.get("external_references", [])
        if isinstance(refs, list):
            for idx, ref in enumerate(refs):
                for msg in validate_https_url(ref, f"verification.evidence.external_references[{idx}]"):
                    errors.append(msg)

    if publisher_host:
        expect(
            any(is_first_party_host(host, publisher_host) for host in doc_hosts),
            "toolspec.external_docs must include at least one first-party URL for the publisher",
        )

    return errors


def main() -> int:
    """Run full registry validation and return an exit code."""
    card_schema = load_schema(TOOLCARD_SCHEMA_PATH)
    spec_schema = load_schema(TOOLSPEC_SCHEMA_PATH)
    verification_schema = load_schema(VERIFICATION_SCHEMA_PATH)

    tool_dirs = iter_tool_dirs(TOOLS_ROOT)
    if not tool_dirs:
        print("No tools found.")
        return 1

    try:
        from jsonschema import Draft7Validator  # type: ignore

        card_validator = Draft7Validator(card_schema)
        spec_validator = Draft7Validator(spec_schema)
        verification_validator = Draft7Validator(verification_schema)
    except Exception:  # pragma: no cover - optional dependency
        card_validator = None
        spec_validator = None
        verification_validator = None

    failures: List[str] = []
    discovered_tool_ids: set[str] = set()
    verified_tool_ids: set[str] = set()
    seen_tool_id_paths: dict[str, Path] = {}
    seen_tool_name_paths: dict[str, Path] = {}

    for tool_dir in tool_dirs:
        card_path = tool_dir / "toolcard.json"
        spec_path = tool_dir / "toolspec.json"
        verification_path = tool_dir / "verification.json"
        expected_slug = f"{tool_dir.parent.name}/{tool_dir.name}"

        if not card_path.exists():
            failures.append(f"{tool_dir}: missing toolcard.json")
            continue
        if not spec_path.exists():
            failures.append(f"{tool_dir}: missing toolspec.json")
            continue
        if not verification_path.exists():
            failures.append(f"{tool_dir}: missing verification.json")
            continue

        card_data = load_json(card_path, failures)
        spec_data = load_json(spec_path, failures)
        verification_data = load_json(verification_path, failures)
        if not isinstance(card_data, dict) or not isinstance(spec_data, dict) or not isinstance(verification_data, dict):
            continue

        card_id = card_data.get("id")
        if isinstance(card_id, str):
            existing_id_path = seen_tool_id_paths.get(card_id)
            if existing_id_path is not None:
                failures.append(
                    f"{card_path}: duplicate toolcard id '{card_id}' already defined in {existing_id_path}"
                )
            else:
                seen_tool_id_paths[card_id] = card_path
                discovered_tool_ids.add(card_id)

        card_name = card_data.get("name")
        if isinstance(card_name, str):
            normalized_name = card_name.strip().casefold()
            if normalized_name:
                existing_name_path = seen_tool_name_paths.get(normalized_name)
                if existing_name_path is not None:
                    failures.append(
                        f"{card_path}: duplicate toolcard name '{card_name}' already defined in {existing_name_path}"
                    )
                else:
                    seen_tool_name_paths[normalized_name] = card_path

        size = card_path.stat().st_size
        if size > SIZE_LIMIT:
            failures.append(f"{card_path}: exceeds {SIZE_LIMIT} bytes ({size} bytes)")

        if card_validator:
            for error in card_validator.iter_errors(card_data):
                failures.append(f"{card_path}: {error.message}")
        else:
            card_errors = manual_validate_card(card_data)
            failures.extend(f"{card_path}: {msg}" for msg in card_errors)

        if spec_validator:
            for error in spec_validator.iter_errors(spec_data):
                failures.append(f"{spec_path}: {error.message}")
        else:
            spec_errors = manual_validate_spec(spec_data, card_data.get("id", ""))
            failures.extend(f"{spec_path}: {msg}" for msg in spec_errors)

        if verification_validator:
            for error in verification_validator.iter_errors(verification_data):
                failures.append(f"{verification_path}: {error.message}")
        else:
            verification_errors = manual_validate_verification(
                verification_data, card_data.get("id", ""), spec_data.get("type", "")
            )
            failures.extend(f"{verification_path}: {msg}" for msg in verification_errors)

        policy_errors = validate_tool_policies(card_data, spec_data, verification_data, expected_slug)
        failures.extend(f"{tool_dir}: {msg}" for msg in policy_errors)

        publisher_data = card_data.get("publisher")
        publisher_verified = isinstance(publisher_data, dict) and publisher_data.get("verified") is True
        if verification_data.get("status") == "verified" and publisher_verified:
            if isinstance(card_id, str):
                verified_tool_ids.add(card_id)

    failures.extend(validate_channels(discovered_tool_ids, verified_tool_ids))

    if failures:
        print("Tool validation failed:\n" + "\n".join(failures))
        return 1

    print(f"Validated {len(tool_dirs)} tools (ToolCard + ToolSpec + verification).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
