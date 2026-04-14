# agent-harness

A multi-agent coding harness that orchestrates Claude-powered agents in configurable pipelines. Define agents and workflows in YAML, chain them together, and run tasks through specialist pipelines.

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

Agents are defined in the `agents/` directory as YAML files. Each agent has a system prompt, a set of tools, optional skills, and optional MCP servers.

### Agent YAML Schema

```yaml
name: my-agent            # Unique identifier used in workflow steps
prompt: |                 # System prompt injected before each conversation
  You are a ...
tools:                    # Built-in tools the agent can call
  - name: read_file
  - name: write_file
  - name: bash
  - name: find_files
  - name: ask_user
skills:                   # Skills loaded and appended to the system prompt
  - name: brainstorming
    description: "Optional description for the skill"
  - reverse               # Short form also accepted
mcp:                      # MCP servers the agent can use (must be in .mcp.json)
  - name: linear
model: anthropic/...      # Optional model override; falls back to DEFAULT_MODEL
```

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
tools:
  - name: read_file
  - name: find_files
skills: []
```

### Example: Agent with Skills and MCP

```yaml
name: linear
prompt: |
  You are an expert Linear user. You receive a specific task and context.
  Use the linear tool to complete the task.
tools:
  - name: ask_user
skills: []
mcp:
  - name: linear
```

### Built-in Agents

| Agent | Role | Tools |
|-------|------|-------|
| `coordinator` | Understands the task, delegates to specialists | `read_file`, `find_files` |
| `planner` | Explores codebase and produces implementation plans | `read_file`, `find_files` |
| `implementer` | Writes code, runs commands, reports changes | `read_file`, `write_file`, `bash`, `find_files` |
| `reviewer` | Reads code, runs checks, returns APPROVED or CHANGES REQUESTED | `read_file`, `bash`, `find_files` |
| `brainstormer` | Brainstorms ideas into designs and specs | all tools + `brainstorming` skill |
| `linear` | Creates and updates Linear issues | `ask_user` + `linear` MCP |
| `github` | Creates pull requests via GitHub MCP | `github` MCP |

---

## Workflows

Workflows are defined in the `workflows/` directory as YAML files. A workflow is an ordered list of agent steps. The output of each step becomes the input of the next.

### Workflow YAML Schema

```yaml
name: my-workflow         # Unique identifier passed to harness.py
description: "Optional"  # Human-readable description
steps:
  - name: planner         # Agent name (must exist in agents/)
    id: planner           # Optional: tag this step's output for later reference
    prompt: |             # Optional: step-specific prompt prepended to input
      Plan the fix...
  - name: implementer
    id: implementer
  - name: reviewer
    loop_on: UNAPPROVED   # If this keyword appears in the step's output...
    loop_to: implementer  # ...jump back to this earlier step
    max_loops: 3          # Max times to loop (default: 3)
  - name: github
    inputs: [implementer] # Explicitly pick which step outputs to use as input
```

### Running a Workflow

```bash
python harness.py workflow <workflow-name> "<task description>"
```

The `<task description>` is sent to the first agent. Each subsequent agent receives the previous agent's text output as its input.

### Dry Run

Preview a workflow's resolved config without making API calls:

```bash
python harness.py workflow <workflow-name> --dry-run
```

This loads the workflow and each agent's config, validates that all tools, skills, and MCP servers exist, and prints the resolved pipeline:

```
  Pipeline: example (3 steps)

    1. planner
       model: qwen/qwen3.6-plus
       tools: read_file, find_files, ask_user
       skills: brainstorming
       mcp: none
       inputs: __input__

    2. implementer
       model: qwen/qwen3.6-plus
       tools: read_file, write_file, bash, find_files
       mcp: none
       inputs: previous step output

    3. reviewer
       model: qwen/qwen3.6-plus
       tools: read_file, bash, find_files
       mcp: none
       inputs: previous step output
```

### Step IDs and Explicit Inputs

By default each step receives the previous step's output. For more complex workflows, tag steps with `id` and reference them with `inputs`:

```yaml
steps:
  - name: linear
    id: card               # Tag this step's output as "card"
  - name: implementer
    id: implementer
  - name: reviewer
    loop_on: REJECTED
    loop_to: implementer
  - name: github
    inputs: [implementer]  # Use implementer's output, not reviewer's
  - name: linear
    inputs: [card]         # Use the original card output
```

The special input `__input__` refers to the original prompt passed on the command line. Multiple inputs are concatenated with `---` separators.

### Loop-Back Steps

A step can loop back to an earlier step based on a keyword in its output. This is useful for implement → review cycles where the reviewer signals that more work is needed.

```yaml
steps:
  - name: implementer
  - name: reviewer
    loop_on: UNAPPROVED   # keyword to watch for (substring match, case-sensitive)
    loop_to: implementer  # name of an earlier step to re-run
    max_loops: 3          # optional; defaults to 3
```

When `loop_on` is found in the step's output, execution jumps back to `loop_to` and the reviewer's full output (including its feedback) becomes the input to that step. When `max_loops` is exhausted, the pipeline continues to the next step.

**Rules:**
- `loop_on` and `loop_to` must both be present or both absent
- `loop_to` must name a step that appears earlier in the workflow
- `STOP` takes precedence over `loop_on` if both appear in the output

### Special Output Keywords

| Keyword | Effect |
|---------|--------|
| `STOP` | Exits the pipeline early with "Nothing to do." |
| Any `loop_on` value | Jumps back to `loop_to` step (up to `max_loops` times) |

### Example: Plan → Implement → Review

```yaml
# workflows/example.yaml
name: example
steps:
  - name: planner
  - name: implementer
  - name: reviewer
```

```bash
python harness.py workflow example "Add a /healthz endpoint to the FastAPI app"
```

### Example: Brainstorm Workflow

```yaml
# workflows/brainstorm.yaml
name: brainstorm
description: Brainstorm ideas into designs and specs.
steps:
  - name: brainstormer
```

```bash
python harness.py workflow brainstorm "Design a notification system for missed deadlines"
```

### Example: End-to-End with Linear + GitHub

```yaml
# workflows/pick-and-fix.yaml
name: pick-and-fix
steps:
  - name: linear
    id: card
    prompt: |
      Pick a card from the 'Agent Harness' project that is in the 'todo' column
      and move it to the 'in progress' column.
  - name: planner
    prompt: Plan the fix for the request.
  - name: implementer
    id: implementer
    prompt: Implement the fix.
  - name: reviewer
    prompt: Review the fix. Reply APPROVED or REJECTED.
    loop_on: REJECTED
    loop_to: implementer
    max_loops: 3
  - name: github
    inputs: [implementer]
    prompt: Create a pull request for the fix.
  - name: linear
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
  - name: linear
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
python harness.py agent planner --model anthropic/claude-sonnet-4
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
tools:
  - name: ask_user
mcp:
  - name: github
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
main.py              # Interactive single-agent REPL
harness.py           # Workflow pipeline runner + CLI
agent_openrouter.py  # Agent loop + streaming API calls
tools.py             # Built-in tool definitions
mcp_client.py        # MCP subprocess client
skills_loader.py     # Skill loading + prompt injection
trace.py             # Trace logging, saving, and formatting
repl_utils.py        # REPL utilities (status bar, escape key)
prompts.py           # Base system prompts
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
