#!/usr/bin/env python3
"""Validate registry URLs for syntax and optional live reachability."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.utils.common_utils import iter_tool_dirs, load_json

ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = ROOT / "tools"
USER_AGENT = "oss-mktpl-link-check/1.0"


def add_url(index: dict[str, set[str]], value: Any, source: str) -> None:
    """Add a URL and source label to the deduplicated URL index."""
    if isinstance(value, str) and value:
        index[value].add(source)


def collect_urls() -> dict[str, set[str]]:
    """Collect all registry URLs from toolcards, toolspecs, and verification records."""
    urls: dict[str, set[str]] = defaultdict(set)
    for tool_dir in iter_tool_dirs(TOOLS_ROOT):
        card_path = tool_dir / "toolcard.json"
        spec_path = tool_dir / "toolspec.json"
        verification_path = tool_dir / "verification.json"
        if not card_path.exists() or not spec_path.exists() or not verification_path.exists():
            continue

        slug = f"{tool_dir.parent.name}/{tool_dir.name}"
        card = load_json(card_path)
        spec = load_json(spec_path)
        verification = load_json(verification_path)

        publisher = card.get("publisher", {})
        if isinstance(publisher, dict):
            add_url(urls, publisher.get("url"), f"{slug}: toolcard.publisher.url")

        pricing = card.get("pricing")
        if isinstance(pricing, str) and pricing.startswith("http"):
            add_url(urls, pricing, f"{slug}: toolcard.pricing")

        docs = spec.get("external_docs", [])
        if isinstance(docs, list):
            for idx, doc in enumerate(docs):
                if isinstance(doc, dict):
                    add_url(urls, doc.get("url"), f"{slug}: toolspec.external_docs[{idx}].url")

        if spec.get("type") == "http":
            http = spec.get("http", {})
            if isinstance(http, dict):
                add_url(urls, http.get("base_url"), f"{slug}: toolspec.http.base_url")
        elif spec.get("type") == "mcp":
            mcp = spec.get("mcp", {})
            if isinstance(mcp, dict):
                add_url(urls, mcp.get("server_url"), f"{slug}: toolspec.mcp.server_url")

        evidence = verification.get("evidence", {})
        if isinstance(evidence, dict):
            add_url(urls, evidence.get("official_docs_url"), f"{slug}: verification.evidence.official_docs_url")
            add_url(urls, evidence.get("official_repo_url"), f"{slug}: verification.evidence.official_repo_url")
            refs = evidence.get("external_references", [])
            if isinstance(refs, list):
                for idx, ref in enumerate(refs):
                    add_url(urls, ref, f"{slug}: verification.evidence.external_references[{idx}]")
    return urls


def validate_url_syntax(url: str) -> str | None:
    """Validate basic URL syntax rules required by this checker."""
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return "must use https"
    if not parsed.netloc:
        return "missing host"
    return None


def http_status(url: str, method: str, timeout: float) -> int:
    """Perform an HTTP request and return the response status code."""
    request = Request(url=url, method=method, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return int(response.getcode())


def validate_live(url: str, timeout: float) -> str | None:
    """Run live reachability checks and return an error string on failure."""
    try:
        status = http_status(url, "HEAD", timeout)
        if 200 <= status < 300:
            return None
        return f"HEAD returned {status} (expected 2xx)"
    except HTTPError as exc:
        if int(exc.code) in {405, 501}:
            # Some endpoints reject HEAD even when GET is valid.
            try:
                status = http_status(url, "GET", timeout)
                if 200 <= status < 300:
                    return None
                return f"GET returned {status} after HEAD {exc.code} (expected 2xx)"
            except HTTPError as get_exc:
                return f"GET returned {int(get_exc.code)} after HEAD {exc.code} (expected 2xx)"
            except URLError as get_exc:
                return f"GET failed after HEAD {exc.code}: {get_exc.reason}"
        return f"HEAD returned {int(exc.code)} (expected 2xx)"
    except URLError as exc:
        return f"HEAD failed: {exc.reason}"


def main() -> int:
    """Run URL validation and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Run syntax-only checks.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds.")
    args = parser.parse_args()

    urls = collect_urls()
    if not urls:
        print("No URLs found for validation.")
        return 1

    failures: list[str] = []
    for url in sorted(urls):
        syntax_error = validate_url_syntax(url)
        if syntax_error:
            failures.append(f"{url}: {syntax_error} | sources={sorted(urls[url])}")
            continue
        if args.offline:
            continue
        live_error = validate_live(url, args.timeout)
        if live_error:
            failures.append(f"{url}: {live_error} | sources={sorted(urls[url])}")

    mode = "syntax-only" if args.offline else "live"
    if failures:
        print(f"Link validation failed ({mode}):\n" + "\n".join(failures))
        return 1

    print(f"Validated {len(urls)} unique URLs ({mode}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
