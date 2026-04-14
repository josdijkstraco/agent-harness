# Trace Logging & Replay for Workflow Pipelines

## Overview

Add structured trace logging to workflow pipeline runs, enabling post-mortem debugging, cost analysis, and step-level replay. Traces are JSON files written to a `traces/` directory.

**Scope**: Workflow pipelines only (`harness.py`). The interactive REPL (`main.py`) is not traced.

**Priority order**: Debugging > Cost analysis > Replay.

## Architecture

### Approach

A `Trace` object is created in `run_pipeline` and threaded into `agent_loop` via a new optional parameter. Both functions call `trace.log()` at key points. No global state or implicit context.

### New module: `trace.py`

Two classes:

```python
@dataclass
class TraceEvent:
    timestamp: float          # time.time()
    step: str | None          # "0:planner", "1:implementer", etc. None for pipeline-level events
    event: str                # event type (see below)
    data: dict                # event-specific payload

class Trace:
    id: str                   # uuid4 hex[:8]
    workflow: str             # workflow name
    command: str              # initial user prompt
    started_at: float
    events: list[TraceEvent]
    status: str               # "running", "completed", "failed", "cancelled"
```

### Event types

| Event | Step | Data |
|---|---|---|
| `pipeline_start` | None | `{workflow, command}` |
| `step_start` | agent name | `{model, tools, prompt_preview}` |
| `api_call` | agent name | `{input_tokens, output_tokens, cost}` |
| `tool_call` | agent name | `{tool, params}` |
| `tool_result` | agent name | `{tool, result_preview, error}` |
| `step_end` | agent name | `{output_preview, loop_triggered}` |
| `loop` | agent name | `{loop_on, loop_to, iteration, max}` |
| `pipeline_end` | None | `{status, total_input, total_output, total_cost, duration}` |

Previews are truncated to ~500 characters.

## Integration points

### `run_pipeline` (harness.py)

- Creates `Trace` at function entry, logs `pipeline_start`
- Logs `step_start` before each `agent_loop` call
- Logs `step_end` after `agent_loop` returns
- Logs `loop` when a loop is triggered
- Logs `pipeline_end` in a `finally` block (fires on success, failure, cancellation)
- Calls `trace.save()` in the `finally` block

### `agent_loop` (agent_openrouter.py)

- Accepts new optional parameter `trace: Trace | None = None`
- Logs `api_call` after each streaming response completes (with token counts)
- Logs `tool_call` before executing each tool
- Logs `tool_result` after each tool returns

### Files not modified

- `main.py` — interactive REPL, out of scope
- `tools.py` — tool handlers don't know about tracing; logging happens around `execute_tool` in `agent_loop`
- `mcp_client.py` — same as above

## Conversation snapshots (for replay)

After each step completes, the full `messages` list is saved to a separate file:

```
traces/
  {id}.json                    # events, metadata, cost summary
  {id}_messages/
    step_0_planner.json        # full messages list after step finished
    step_1_implementer.json
    step_2_reviewer.json
```

The main trace JSON references these files but does not inline them. This keeps the trace file lightweight while preserving full state for replay.

## CLI interface

Three new subcommands on `harness.py`:

### `python harness.py trace list`

Lists recent traces as a summary table:

```
ID        Workflow      Status     Steps  Cost     Duration  Started
a3f1b2c0  pick-and-fix  completed  6      $0.0342  45s       2026-04-13 14:30
9e2c4d11  example       failed     2/3    $0.0128  22s       2026-04-13 14:15
```

### `python harness.py trace show <id>`

Shows a single trace with step-by-step detail:

```
Trace a3f1b2c0 — pick-and-fix (completed)
Command: "Fix the auth bug from card HARNESS-12"

Step 1: linear (2.1s, $0.0031)
  -> tool: search_issues({project: "Agent Harness"})
  -> tool: move_card({id: "HARNESS-12", column: "in progress"})
  -> output: "Card HARNESS-12: Fix login timeout..."

Step 2: planner (3.4s, $0.0058)
  -> output: "1. Read auth.py..."
```

### `python harness.py replay <id> --from-step <N>`

Replays a pipeline from step N:

- Loads the workflow config and agent definitions
- Restores messages from `step_{N-1}_*.json` snapshot
- Re-runs from step N onward
- Creates a new trace for the replayed run

## Storage

Traces are stored in `traces/` at the project root. Message snapshots can be several MB for long pipelines. No automatic cleanup — these are dev/debug artifacts. A `--no-snapshots` flag could be added later if storage becomes a concern.

`traces/` should be added to `.gitignore`.
