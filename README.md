# Agentic Tool Registry

Registry of production-reviewed tool metadata for agent discovery and invocation.

This repo stores:
- `ToolCard` (compact discovery metadata)
- `ToolSpec` (how to call the tool)
- `verification` record (moderator legitimacy decision)
- channel manifests and versioned bundle artifacts

## Critical Rules

1. No direct pushes to `main`.
2. Every tool directory must contain all three files:
   - `toolcard.json`
   - `toolspec.json`
   - `verification.json`
3. Merged/published tools must satisfy verification policy:
   - `toolcard.publisher.verified = true`
   - `verification.status = "verified"`
4. Channel manifests can reference only valid, verified tool IDs.
5. CI pass is required, but moderator review is still required.

## Repository Layout

```text
schemas/
  toolcard.schema.json
  toolspec.schema.json
  tool-verification.schema.json

tools/<publisher>/<tool>/
  toolcard.json
  toolspec.json
  verification.json

channels/
  index.json
  stable.json
  community.json
  experimental.json

dist/<bundle-version>/
  manifest.json
  toolcards.bundle.jsonl
  toolspecs.bundle.jsonl
  verifications.bundle.jsonl
```

## Submission Workflow

### Contributor Flow (requesting/adding a new tool)

1. Scaffold files:

```bash
./bin/atr init-tool --interactive
```

2. Fill prompts for tool metadata and call details.

3. Review generated files under:
- `tools/<publisher>/<tool>/toolcard.json`
- `tools/<publisher>/<tool>/toolspec.json`
- `tools/<publisher>/<tool>/verification.json`

4. Open a PR.

Notes:
- `init-tool` intentionally does **not** ask moderator-only verification questions.
- It generates a pending verification record for PR intake.

### Moderator Flow (approval and merge)

Before merge, moderator must complete legitimacy review and update submission state:
- `toolcard.publisher.verified` -> `true`
- `verification.status` -> `"verified"`
- `verification.reviewed_by` -> moderator identity
- `verification.reviewed_at` -> UTC ISO8601 timestamp
- `verification.evidence.*` -> complete evidence links/notes

Then ensure CI passes and approve merge.

## Local Validation (before PR)

```bash
python3 -m src.commands.validate_toolcards
python3 -m src.commands.check_links --offline
python3 -m py_compile src/atr_cli.py src/commands/*.py src/utils/*.py
```

## CI Validation

Workflow: `.github/workflows/validate-registry.yml`

Runs on PR updates and pushes to `main`.

CI gates:
- `python3 -m src.commands.validate_toolcards`
- `python3 -m src.commands.check_links --timeout 12`
- `python3 -m py_compile src/atr_cli.py src/commands/*.py src/utils/*.py`

## Build Registry Bundle

Build a versioned stable snapshot:

```bash
python3 -m src.commands.build_registry_bundle
```

Bundler behavior:
- hard-fails if validator fails
- bundles `stable` channel only
- includes verified tools only
- writes versioned artifacts to `dist/<timestamp>-<gitsha>/`

## CLI Commands

Supported binary names:
- `atr`
- `agentic-tool-registry`

### `sync`

```bash
./bin/atr sync
./bin/atr sync --version <bundle-version>
./bin/atr sync --channel community --allow-risky-channel
./bin/atr sync --source-dir ./dist --cache-dir ~/.cache/agentic-tool-registry
```

Behavior:
- reads local bundle from `dist/`
- defaults to latest bundle version
- verifies artifact checksums from `manifest.json`
- caches snapshot under `~/.cache/agentic-tool-registry/snapshots/<version>/`
- writes active state to `~/.cache/agentic-tool-registry/current.json`

### `search`

```bash
./bin/atr search
```

Outputs JSONL records with exactly:
- `id`
- `name`
- `description`

### `show`

```bash
./bin/atr show <tool-id>
```

Behavior:
- case-insensitive tool ID match
- prints full ToolCard as minified JSON
- key order starts with `id`, `name`, `description`

### `resolve`

```bash
./bin/atr resolve <tool-id>
```

Behavior:
- case-insensitive tool ID match
- resolves against cached `toolspecs` artifact
- prints full ToolSpec as minified JSON
- key order starts with `tool_id`, `type`, `summary`, `auth`, `external_docs`

### `init-tool`

```bash
./bin/atr init-tool --interactive
```

Behavior:
- creates required manifest files in `tools/<publisher>/<tool>/`
- enforces slug/URL/basic schema-shape constraints during prompting
- asks payment requirement first; for unpaid tools it auto-fills `pricing=\"Free\"`, `currency=\"USD\"`, and `payment.purl_supported=false`
- does not expose moderator verification workflow in prompts

## Legal / Risk Notice

This repository is provided **as is**. Listed tools may be inaccurate, unsafe, or malicious. Use at your own risk. Maintainers and contributors are not liable for losses or incidents resulting from tool usage.
