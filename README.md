# agent-harness

A multi-agent coding harness that orchestrates LLM agents (via OpenRouter) in configurable pipelines. Define agents and workflows in YAML, chain them together with structured outputs, and run tasks through specialist pipelines.

## Quick Start

```bash
# Install dependencies
uv sync

# Set your API key
echo "OPENROUTER_API_KEY=sk-..." > .env

# Interactive single-agent mode
python main.py

# Run a task through a workflow pipeline
python harness.py workflow <workflow-name> "<your task>"
```

## Agents

Agents are defined in the `agents/` directory as YAML files. Each agent has a system prompt, a set of tools, optional skills, optional MCP servers, an optional model override, and an optional structured output schema.

### Agent YAML Schema

```yaml
name: my-agent            # Unique identifier used in workflow steps
prompt: |                 # System prompt injected before each conversation
  You are a ...
tools:                    # Built-in tools the agent can call
  - read_file
  - write_file
  - bash
  - find_files
  - ask_user
skills:                   # Skills loaded and appended to the system prompt
  - name: brainstorming
    description: "Optional description for the skill"
  - reverse               # Short form also accepted
mcp:                      # MCP servers the agent can use (must be in .mcp.json)
  - linear
model: qwen/qwen3.6-plus  # Optional model override; falls back to DEFAULT_MODEL
output:                   # Optional: agent's canonical structured result schema
  decision: {type: string, enum: [APPROVED, REJECTED]}
  feedback: {type: string}
```

When `output:` is set, the harness generates a `submit_result` tool for the agent and requires it to call that tool to produce its final structured result.

### Available Built-in Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read the contents of a file |
| `write_file` | Write content to a file (creates parent dirs) |
| `bash` | Run a shell command, 30s timeout |
| `find_files` | Find files matching a glob pattern |
| `ask_user` | Prompt the user for input (interactive sessions only) |

### Example: Minimal Agent

```yaml
name: explainer
prompt: |
  You are a code explainer. Read the requested file and explain what it does
  in plain English. Be concise.
tools: [read_file, find_files]
```

### Example: Agent with Structured Output

```yaml
name: reviewer
prompt: |
  You are a code reviewer. Read changed files, run checks with bash, and
  submit your verdict via submit_result.
tools: [read_file, bash, find_files]
model: z-ai/glm-5.1
output:
  decision: {type: string, enum: [APPROVED, REJECTED]}
  feedback: {type: string}
```

### Example: Agent with Skills and MCP

```yaml
name: linear
prompt: |
  You are a Linear assistant. Use the Linear MCP tools to complete the task.
tools: [ask_user]
mcp: [linear]
```

### Built-in Agents

| Agent | Role | Tools | Model |
|-------|------|-------|-------|
| `coordinator` | Understands tasks, explores codebase | `read_file`, `find_files` | default |
| `planner` | Produces step-by-step implementation plans | `read_file`, `find_files`, `ask_user` | default |
| `implementer` | Writes code, runs checks, reports changes | `read_file`, `write_file`, `bash`, `find_files` | `qwen/qwen3.6-plus` |
| `reviewer` | Reads code, runs checks, returns APPROVED/REJECTED (structured) | `read_file`, `bash`, `find_files` | `z-ai/glm-5.1` |
| `brainstormer` | Turns ideas into specs; uses `brainstorming` skill | `read_file`, `write_file`, `bash`, `find_files`, `ask_user` | default |
| `linear` | Creates and updates Linear issues | `ask_user` + `linear` MCP | default |
| `github` | Creates pull requests | `read_file`, `bash` + `github` MCP | default |

---

## Workflows

Workflows are defined in the `workflows/` directory as YAML files. A workflow is an ordered list of agent steps. By default the output of each step becomes the input of the next; explicit `inputs:` and structured `output:` schemas let you build richer graphs.

### Workflow YAML Schema

```yaml
name: my-workflow         # Unique identifier passed to harness.py
description: "Optional"  # Human-readable description
steps:
  - agent: planner        # Agent name (must exist in agents/)
    id: planner           # Optional: tag this step's output for later reference
    prompt: |             # Optional: step-specific prompt prepended to input
      Plan the fix...
  - agent: implementer
    id: implementer
  - agent: reviewer
    output:               # Optional: step-level output schema (merged with agent's)
      decision: {type: string, enum: [APPROVED, REJECTED]}
      feedback: {type: string}
    loop_on: decision == REJECTED  # Loop back when condition holds...
    loop_to: implementer           # ...to this earlier step
    max_loops: 3                   # Max loop iterations (default: 3)
  - agent: github
    inputs: [implementer] # Pick specific earlier step outputs as input
    when: APPROVED in reviewer  # Skip step unless condition holds (optional)
```

### Step Fields

| Field | Type | Description |
|-------|------|-------------|
| `agent` | string | Name of the agent to run (required) |
| `id` | string | Tag this step's output; defaults to `agent`. Required when an agent appears more than once |
| `prompt` | string | Step-specific prompt prepended to the input |
| `inputs` | list | Step ids / artifact names / `__input__` to use as input. Default: previous step's output |
| `output` | dict | Structured result schema, merged with the agent's canonical `output`. Triggers the `submit_result` tool |
| `outputs` | dict | Named artifacts extracted from fenced code blocks in the step's text output |
| `loop_on` | string | Keyword (substring) OR `field == value` when `output` is declared |
| `loop_to` | string | Earlier step id to jump back to |
| `max_loops` | int | Cap for loop iterations (default 3) |
| `stop_on` | string | `field == value` condition evaluated against the structured result; halts the pipeline with "Nothing to do." |
| `when` | string | `PATTERN in step_id` — skip the step if the pattern isn't present in the referenced output |

### Running a Workflow

```bash
python harness.py workflow <workflow-name> "<task description>"
```

The `<task description>` is sent to the first agent. Each subsequent step receives either the previous step's output or whatever `inputs:` selects.

### Dry Run

Preview a workflow's resolved config without making any API calls:

```bash
python harness.py workflow <workflow-name> --dry-run
```

This loads the workflow and each agent's config, validates that all tools, skills, and MCP servers exist, and prints the resolved pipeline:

```
  Pipeline: example (3 steps)

    1. planner  (planner)
       model: qwen/qwen3.6-plus
       tools: read_file, find_files, ask_user
       mcp: none
       inputs: __input__

    2. implementer  (implementer)
       model: qwen/qwen3.6-plus
       tools: read_file, write_file, bash, find_files
       mcp: none
       inputs: previous step output

    3. reviewer  (reviewer)
       model: z-ai/glm-5.1
       tools: read_file, bash, find_files
       mcp: none
       inputs: previous step output
```

### Step IDs and Explicit Inputs

By default each step receives the previous step's output. For more complex workflows, tag steps with `id` and reference them with `inputs`:

```yaml
steps:
  - agent: linear
    id: card               # Tag this step's output as "card"
  - agent: planner
  - agent: implementer
    id: implementer
  - agent: reviewer
    loop_on: decision == REJECTED
    loop_to: implementer
    output:
      decision: {type: string, enum: [APPROVED, REJECTED]}
      feedback: {type: string}
  - agent: github
    inputs: [implementer]  # Use implementer's output, not reviewer's
  - agent: linear
    inputs: [card]         # Use the original card output
```

The special input `__input__` refers to the original prompt passed on the command line. Multiple inputs are concatenated under `## Input: <id>` headers.

### Loop-Back Steps

A step can loop back to an earlier step based on its output. Useful for implement → review cycles.

```yaml
- agent: reviewer
  output:
    decision: {type: string, enum: [APPROVED, REJECTED]}
    feedback: {type: string}
  loop_on: decision == REJECTED   # structured-result form
  loop_to: implementer
  max_loops: 3
```

Or, without a structured schema, fall back to substring matching:

```yaml
- agent: reviewer
  loop_on: UNAPPROVED             # substring match in the step's text output
  loop_to: implementer
```

When the condition holds, execution jumps back to `loop_to` and the full output (including feedback) becomes the input to that step. When `max_loops` is exhausted, the pipeline continues to the next step.

**Rules:**
- `loop_on` and `loop_to` must both be present or both absent
- `loop_to` must name a step that appears earlier in the workflow
- `STOP` in a step's text output halts the pipeline (takes precedence over `loop_on`)
- A step can't use both `loop_on` and `when`, or both `loop_on` and `stop_on`

### Stopping Early

Use `stop_on` with a structured `output` schema to halt the pipeline when a condition is met — for example, when an upstream step reports "nothing to do":

```yaml
- agent: linear
  id: card
  output:
    status: {type: string, enum: [FOUND, STOP]}
    context: {type: string}
  stop_on: status == STOP
```

### Conditional Steps

Use `when:` to skip a step when a pattern isn't present in an earlier step's output:

```yaml
- agent: github
  when: FOUND in card     # only run if "FOUND" appears in the card step's output
```

### Named Artifacts (`outputs:`)

A step can declare named artifacts that the harness will extract from fenced code blocks in the step's text output:

```yaml
- agent: planner
  outputs:
    plan: {type: string}
```

If the agent emits:

    ```plan
    1. Do X
    2. Do Y
    ```

the harness extracts the block into the `plan` artifact, which later steps can reference via `inputs: [plan]`.

### Special Keywords

| Keyword | Effect |
|---------|--------|
| `STOP` (in text output) | Exits the pipeline early with "Nothing to do." |
| `stop_on` condition | Same, but evaluated against the structured result |
| `loop_on` condition | Jumps back to `loop_to` step (up to `max_loops` times) |

### Example: Plan → Implement → Review

```yaml
# workflows/example.yaml
name: example
steps:
  - agent: planner
  - agent: implementer
  - agent: reviewer
```

```bash
python harness.py workflow example "Add a /healthz endpoint to the FastAPI app"
```

### Example: Brainstorm Workflow

```yaml
# workflows/brainstorm.yaml
name: brainstorm
steps:
  - agent: brainstormer
```

```bash
python harness.py workflow brainstorm "Design a notification system for missed deadlines"
```

### Example: End-to-End with Linear + GitHub

```yaml
# workflows/pick-and-fix.yaml
name: pick-and-fix
steps:
  - agent: linear
    id: card
    prompt: |
      Pick a card from the 'Agent Harness' project that is in the 'todo' column
      and move it to 'in progress'. Your final response must include the card's
      context. If no cards are found, call submit_result with status STOP.
    output:
      status: {type: string, enum: [FOUND, STOP]}
      context: {type: string}
    stop_on: status == STOP

  - agent: planner
    prompt: Plan the fix for the request.

  - agent: implementer
    id: implementer

  - agent: reviewer
    output:
      decision: {type: string, enum: [APPROVED, REJECTED]}
      feedback: {type: string}
    loop_on: decision == REJECTED
    loop_to: implementer
    max_loops: 3

  - agent: github
    inputs: [implementer]
    prompt: Create a pull request for the fix.

  - agent: linear
    id: done
    inputs: [card]
    prompt: Move the card to the 'done' column.
```

```bash
python harness.py workflow pick-and-fix "Fix the next bug"
```

### Example: Single-Agent Workflow (Linear)

```yaml
# workflows/linear.yaml
name: linear
steps:
  - agent: linear
```

```bash
python harness.py workflow linear "Create a bug report for the login timeout issue"
```

---

## Single Agent Mode

Run any agent directly without a workflow — either one-shot or as an interactive REPL:

```bash
# One-shot: run once and exit
python harness.py agent planner "Explore the auth module and plan a refactor"

# Interactive REPL
python harness.py agent implementer

# Override the agent's default model
python harness.py agent planner --model z-ai/glm-5.1
```

### REPL Commands

| Command | Effect |
|---------|--------|
| `/model` | Switch to a different model |
| `/clear` | Clear message history and reset token counters |
| `exit` / `quit` | Exit the REPL |
| `Escape` | Cancel the current request |

The REPL shows a status bar with the current model, token usage, turn count, and running cost.

---

## Traces

Every pipeline run is automatically traced and saved to the `traces/` directory. Traces capture each step's inputs, outputs, tool calls, token usage, costs, and timing.

### List Recent Traces

```bash
python harness.py trace list
```

Displays a table of recent traces with ID, workflow name, status, step count, cost, duration, and start time.

### Show Trace Detail

```bash
python harness.py trace show <trace-id>
```

Shows a step-by-step breakdown of the pipeline execution including tool calls, results, and per-step costs.

### Replay from a Step

Resume a previous pipeline run from a specific step. Useful for retrying after a failure or re-running from the review stage:

```bash
python harness.py replay <trace-id> --from-step 2
```

This loads the original trace's workflow and command, then re-executes from step N onward.

---

## MCP Servers

MCP (Model Context Protocol) servers extend agents with external tools. Configure them in `.mcp.json` at the repo root, then reference them by name in an agent's `mcp:` list.

### `.mcp.json` Format

```json
{
  "server-name": {
    "command": "npx",
    "args": ["-y", "some-mcp-package"]
  }
}
```

### Adding an MCP Server to an Agent

1. Add the server to `.mcp.json`:

```json
{
  "github": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"]
  }
}
```

2. Reference it in your agent YAML:

```yaml
name: github-agent
prompt: |
  You are a GitHub assistant. Use the GitHub tools to manage issues and PRs.
tools: [ask_user]
mcp: [github]
```

The harness starts each MCP server as a subprocess and exposes its tools to the agent automatically.

---

## Skills

Skills are markdown documents appended to an agent's system prompt. They live in `skills/<skill-name>/SKILL.md`.

### Adding a Skill to an Agent

```yaml
skills:
  - name: brainstorming
    description: "Use before any creative work"
  - reverse           # short form; description is optional
```

### Creating a New Skill

Create `skills/my-skill/SKILL.md` with the instructions you want appended to the agent's prompt.

---

## Project Structure

```
agents/              # Agent YAML definitions
workflows/           # Workflow YAML definitions
skills/              # Skill markdown files
traces/              # Saved pipeline traces (auto-generated)
main.py              # Interactive single-agent REPL (boot logo + default agent)
harness.py           # Workflow pipeline runner + CLI
agent_openrouter.py  # Agent loop + streaming OpenRouter calls
tools.py             # Built-in tool definitions
mcp_client.py        # MCP subprocess client
skills_loader.py     # Skill loading + prompt injection
trace.py             # Trace logging, saving, and formatting
repl_utils.py        # REPL utilities (status bar, escape key)
prompts.py           # Base system prompts
logo.py              # Startup logo
.mcp.json            # MCP server registry
```

---

## CLI Reference

```bash
# Single agent (one-shot)
python harness.py agent <name> "<prompt>" [--model <model>]

# Single agent (interactive REPL)
python harness.py agent <name> [--model <model>]

# Run a workflow pipeline
python harness.py workflow <name> "<prompt>"

# Preview resolved workflow config (no API calls)
python harness.py workflow <name> --dry-run

# List recent pipeline traces
python harness.py trace list [--traces-dir <dir>]

# Show detailed trace
python harness.py trace show <trace-id> [--traces-dir <dir>]

# Replay pipeline from a specific step
python harness.py replay <trace-id> --from-step <N> [--traces-dir <dir>]

# Interactive single-agent REPL (default model)
python main.py
```
