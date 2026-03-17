# Contributing

## Before You Start

- Do not push directly to `main`.
- Keep changes focused. Separate tool metadata changes from unrelated code or docs changes.
- Do not hand-edit `dist/` unless you are intentionally generating a new bundle snapshot.

Recommended local setup:

```bash
python3 -m pip install -e .
```

## Repository Basics

Each tool lives in:

```text
tools/<publisher>/<tool>/
  toolcard.json
  toolspec.json
  verification.json
```

Merged tools must satisfy all of the following:
- `toolcard.id`, `toolspec.tool_id`, and `verification.tool_id` match the directory slug
- `toolcard.publisher.verified = true`
- `verification.status = "verified"`
- referenced channel manifests include only valid verified tool IDs

`verified` and related labels are limited moderation markers only. They are not safety, legality, compliance, accuracy, or endorsement guarantees.

## Adding A New Tool

The easiest path is:

```bash
atr init-tool --interactive
```

That creates:
- `toolcard.json`
- `toolspec.json`
- `verification.json`

Important:
- `init-tool` is for contributor intake, not final moderator approval
- it writes a pending verification record that still needs moderator review before merge
- submitting a tool does not obligate maintainers to merge, publish, support, or continue listing it

After scaffolding:
1. Review the generated metadata carefully.
2. Confirm URLs, auth guidance, and examples are accurate.
3. Make sure the tool belongs in the correct publisher directory and uses the correct slug.
4. Add the tool to the appropriate channel manifest only when it meets that channel's requirements.

## Updating An Existing Tool

When updating a tool:
1. Keep metadata aligned across `toolcard.json`, `toolspec.json`, and `verification.json`.
2. Re-check official docs, auth instructions, pricing text, and evidence URLs.
3. Update channel manifests only if channel membership should change.

## Moderator Review

Before a tool is merge-ready, a moderator must complete the verification record:
- set `toolcard.publisher.verified` to `true`
- set `verification.status` to `"verified"`
- set `verification.reviewed_by`
- set `verification.reviewed_at` to a UTC ISO8601 timestamp
- complete `verification.evidence.*`

For CLI tools, `verification.evidence.official_repo_url` is required.

## Validation

Run these commands before opening a PR:

```bash
python3 -m src.commands.validate_toolcards
python3 -m src.commands.check_links --offline
python3 -m py_compile src/atr_cli.py src/commands/*.py src/utils/*.py
```

If your change affects bundles, channels, or release artifacts, also run:

```bash
python3 -m src.commands.build_registry_bundle
```

## Pull Requests

A good PR should:
- explain what changed and why
- call out any channel changes
- mention any verification updates
- include validation results
- update docs when behavior or workflow changes

By submitting code, metadata, or documentation to this repository, you represent that, to the best of your knowledge, you have the right to submit it and that doing so does not knowingly violate third-party rights or confidentiality obligations.

Avoid language in PRs, tool metadata, or documentation that implies any listed tool is guaranteed safe, secure, compliant, lawful, endorsed, or suitable for a user's specific needs.

If you changed contributor or moderation workflow, update [README.md](README.md) and this file in the same PR.
