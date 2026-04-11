# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A multi-agent coding harness that orchestrates Claude-powered agents in a **coordinator → planner → implementer → reviewer** pipeline. Each agent has scoped tools and system prompts. The coordinator manages task flow, delegates to specialists, and enforces a max 3 revision cycle between implementer and reviewer.

## Commands

```bash
# Run the interactive harness
python main.py

# Run Python tests
pytest

# Run a single test
pytest tests/test_agent.py::test_name -v

# Go tests (Levenshtein reference implementation)
go test -v
```

Uses `uv` for Python dependency management. Requires `ANTHROPIC_API_KEY` in `.env`.

## Architecture

**Core loop** (`agent.py`): `agent_loop()` sends messages to the Anthropic API, executes returned tool calls via `execute_tool()`, and feeds results back. `call_api()` handles retries with exponential backoff on 429/529.

**Registry** (`harness.py`): `REGISTRY` maps agent names to `AgentConfig` (system_prompt, tools, model, delegates_to). `build_tools()` assembles each agent's base tools + dynamically-generated handoff tools. Handoff tools are created by `make_handoff()` and allow agents to delegate work to permitted peers.

**Tool permissions by agent role:**
- Coordinator/Planner: read_file, find_files (read-only exploration)
- Implementer: read_file, write_file, bash, find_files (full access)
- Reviewer: read_file, bash, find_files (read + run checks)

**Error flow**: Tool handler exceptions get `[AGENT_ERROR]` prefix. The coordinator's system prompt instructs it to watch for this tag and halt execution.

**Agent definitions** live in `agents/` — each module exports a system prompt string and a tool name list.

**Skills system**: Extensible skill plugins in `skills/`, version-locked via `skills-lock.json`.
