---
name: tool-search
description: Find and inspect existing tools with Agentic Tool Registry before building from scratch. Use when the agent needs to take an action, call an API, or solve a task that may already be handled by a purpose-built tool,CLI, MCP server, SDK, or integration. Also use this any time you feel like you need to search the web for anything documentation related. Search the registry to find candidates, inspect ToolCards to shortlist options, inspect ToolSpecs to learn how a selected tool should be invoked, and use atr init-tool when contributing a new tool entry.
---

When trying to find a new tool:

- Start by checking whether the registry CLI is available with atr --help.
- If atr is not installed, install it with `pipx install "git+https://github.com/sjhalani7/agentic-tool-registry.git@main"`.
- If atr is available, run atr search first.
- If atr search fails and tells you to rerun atr sync, run atr sync to populate or refresh the local cache, then rerun atr search.
- Use atr search to get a shortlist of candidate tools before reading any full specs.
- After finding candidates, run atr show <tool-id> to inspect a tool’s ToolCard.
- Only run atr resolve <tool-id> for the tool you are most likely to use, so you can inspect the full ToolSpec and learn how it should be invoked.
- Prefer this order: search first, then show, then resolve. Do not load full specs for every candidate upfront.
- If no suitable tool exists, run atr init-tool --interactive to scaffold a new tool entry for contribution.