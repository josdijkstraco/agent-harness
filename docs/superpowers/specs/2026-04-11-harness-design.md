# harness.py — Workflow Pipeline Executor

**Date:** 2026-04-11

## Overview

A CLI batch executor that loads a named workflow, resolves each step to an agent definition, and runs a user-supplied command through the pipeline. Each agent's final text response becomes the next agent's input. Output streams to stdout in real time.

## CLI

```
python harness.py <workflow_name> "<command>"
```

- `workflow_name` — scans all YAML files in `workflows/` and matches the one whose `name:` field equals `workflow_name`
- `command` — the initial user message sent to the first agent

Exits with a clear error message if the workflow file or any agent file is not found.

## File Formats

### Workflow YAML (`workflows/<name>.yaml`)

```yaml
name: example
description: Example workflow.
steps:
  - name: implementer
  - name: reviewer
```

`steps[].name` must match the `name:` field of an agent file in `agents/`.

### Agent YAML (`agents/<name>.yaml`)

```yaml
name: implementer
model: qwen/qwen3.6-plus   # optional; falls back to DEFAULT_MODEL
prompt: |
  You are an implementer...
tools:
  - name: read_file
  - name: write_file
  - name: bash
  - name: find_files
```

Tool names are resolved against `ALL_TOOLS` from `tools.py`. Unknown tool names produce a startup error.

## Architecture

```
harness.py
  └── load_workflow(name) → list[step_name]   # scans workflows/ by name: field
  └── load_agent(name)    → AgentConfig(prompt, tools, model)  # scans agents/ by name: field
  └── run_pipeline(steps, command)
        for each step:
          agent_loop(input_message, messages, model, tools)  ← agent_openrouter.py
          extract last assistant message → next input
```

**No new abstractions.** `harness.py` is a flat script; `agent_loop()` from `agent_openrouter.py` does the heavy lifting.

## Data Flow

```
command
  → [agent 1] streams output → final_text_1
  → [agent 2] streams output → final_text_2
  → ...
  → [agent N] streams output → final_text_N (printed, program exits)
```

Each agent gets a **fresh messages list** seeded with its own system prompt. The only thing passed between agents is the final text response.

## Output

```
[agent: planner]
<streamed tokens...>

[agent: implementer]
<streamed tokens...>
```

No summary line at the end. The last agent's streamed output is the result.

## Default Model

`DEFAULT_MODEL = "qwen/qwen3.6-plus"` — same as `MODEL` in `agent_openrouter.py`.

## Error Handling

- Missing workflow file → print error, `sys.exit(1)`
- Missing agent file → print error, `sys.exit(1)`
- Unknown tool name in agent YAML → print error, `sys.exit(1)`
- Runtime errors during agent execution → propagate naturally (no silent swallowing)

## Files Modified

| File | Change |
|------|--------|
| `harness.py` | **New file** — ~80 lines |
| `agent_openrouter.py` | No changes |
| `tools.py` | No changes |
| `workflows/example.yaml` | No changes |
| `agents/implementer.yaml` | Add optional `model:` field to spec (backward-compatible) |

## Verification

```bash
# Basic smoke test
python harness.py example "Add a hello world function to main.py"

# Missing workflow error
python harness.py nonexistent "test"  # should print error and exit 1

# Multi-step workflow (create a test workflow first)
python harness.py planner-implementer "Implement feature X"
```
