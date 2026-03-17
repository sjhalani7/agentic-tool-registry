# Agentic Tool Registry

CLI and metadata registry for agent tool discovery.

## What It Is

Agentic Tool Registry is a local-first CLI plus a curated metadata registry for tools that coding agents may need to discover and use. Instead of making an agent read full product docs up front, the registry gives it a small discovery layer first and then a more detailed invocation layer only when a tool is selected. (Think how agents use skills: they have a header that gives them enough information to invoke a skill, and then they call the relevant information)

In practice, this helps with a few things:
- faster tool discovery
- less context pollution
- repeatable local caching of registry snapshots
- stricter validation around what gets published
- a simple way to inspect how a tool should be called

The registry stores:
- `ToolCard` discovery metadata
- `ToolSpec` invocation details
- per-tool `verification` records
- channel manifests
- versioned bundle artifacts under `dist/`

Why it is needed:
- agents need a compact shortlist before they need a full spec
- maintainers need a reviewable, PR-based source of truth
- users need a simple CLI for syncing, searching, and inspecting tools locally

## Install

Install the CLI with `pipx`:

```bash
pipx install git+https://github.com/sjhalani7/agentic-tool-registry.git
```

For local development from this repo:

```bash
python3 -m pip install -e .
```

Supported binaries:
- `atr`
- `agentic-tool-registry`

## Use With AI Agents

This repo also includes a reusable skill at:

```text
skills/tool-search/
```

If your agent supports local file-based skills, download this repo and copy that folder into the agent's skills directory.

To install it:

1. Download or clone this repo.
2. Copy the entire `skills/tool-search` folder into that agent's local skills directory.
3. Keep the folder name as `tool-search`.
4. Make sure `atr` is installed and available on `PATH`.
5. Start a new agent session so it reloads local skills.

Examples:

```text
~/.codex/skills/tool-search
~/.claude/skills/tool-search
~/.<agent>/skills/tool-search
```

Example copy commands after cloning this repo:

```bash
cp -R ./skills/tool-search ~/.codex/skills/tool-search
cp -R ./skills/tool-search ~/.claude/skills/tool-search
```

The copied folder should contain:

```text
tool-search/
  SKILL.md
```

Once installed, the agent can use the skill to:
- check whether `atr` is available
- run `atr search` first to shortlist tools
- run `atr show <tool-id>` to inspect a ToolCard
- run `atr resolve <tool-id>` only for the selected candidate
- run `atr init-tool --interactive` if no suitable tool exists and a new entry should be scaffolded

## Use The CLI

### 1. Sync a registry snapshot

Fetch the latest published snapshot into your local cache:

```bash
atr sync
```

Useful variants:

```bash
atr sync --version <bundle-version>
atr sync --source remote --remote-base-url <https-registry-url>
atr sync --source local --source-dir ./dist
atr sync --channel community --allow-risky-channel
atr sync --cache-dir ~/.cache/agentic-tool-registry
```

What it does:
- downloads or copies a bundle snapshot
- verifies artifact checksums from `manifest.json`
- stores the snapshot under your cache directory
- updates the active cache state used by `search`, `show`, and `resolve`

Checksum verification confirms artifact integrity relative to the selected manifest. It does not by itself guarantee trustworthiness, safety, legality, suitability, or endorsement.

### 2. List available tools

```bash
atr search
```

Output is JSONL with exactly:
- `id`
- `name`
- `description`

### 3. Inspect one ToolCard

```bash
atr show slack/web-api
```

This prints the full cached `ToolCard` as minified JSON.

### 4. Inspect one ToolSpec

```bash
atr resolve slack/web-api
```

This prints the full cached `ToolSpec` as minified JSON.

## Common Workflows

### Use the published registry

```bash
atr sync
atr search
atr show <tool-id>
atr resolve <tool-id>
```

### Test against a local bundle

Build a bundle from the current repo and sync from `dist/`:

```bash
python3 -m src.commands.build_registry_bundle
atr sync --source local --source-dir ./dist
atr search
```

### Add a new tool

Scaffold a new tool entry:

```bash
atr init-tool --interactive
```

This creates:

```text
tools/<publisher>/<tool>/
  toolcard.json
  toolspec.json
  verification.json
```

`init-tool` creates an intake scaffold only. Moderator review is still required before merge.

## Validate Changes

Run these before opening a PR:

```bash
python3 -m src.commands.validate_toolcards
python3 -m src.commands.check_links --offline
python3 -m py_compile src/atr_cli.py src/commands/*.py src/utils/*.py
```

If your change affects channels or release bundles, also run:

```bash
python3 -m src.commands.build_registry_bundle
```

## Publish Bundles

Build a versioned bundle locally:

```bash
python3 -m src.commands.build_registry_bundle
```

GitHub workflows:
- `.github/workflows/validate-registry.yml`
- `.github/workflows/build-registry-bundle.yml`
- `.github/workflows/publish-registry-pages.yml`

## Future Work

This is still a small sample of tools, and we want to grow the registry substantially over time. If you want to help expand it, please follow the contribution guide, open PRs, file issues, send requests, and star the repo.

Right now, `atr search` returns all tools at once. That works for the current size of the registry, but a better approach is grouping and browsing by category. We plan to add that once the registry has a larger set of ingested tools.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution and moderation workflow.

## Legal / Risk Notice

This repository, the CLI, all bundles, and all listed tools are provided on an `AS IS` and `WITH ALL FAULTS` basis, without warranties or guarantees of any kind, to the maximum extent permitted by applicable law.

`verified`, `stable`, `official`, `reviewed`, and similar labels have a limited repository-specific meaning. They do not mean safe, secure, lawful, accurate, available, endorsed, or fit for any purpose.

You are solely responsible for independently evaluating each tool, bundle, and use case before relying on it, including security, privacy, contract, and legal/compliance review where relevant.

If you do not want to assume those risks, do not use, rely on, sync, redistribute, or build on this repository, the CLI, any bundle, or any listed tool.

See [LEGAL.md](LEGAL.md) for the full notice, including no-liability, no-advice, trademark, and license-status language.
