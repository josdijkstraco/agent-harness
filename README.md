# coding-harness

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

---

## Workflows

Workflows are defined in the `workflows/` directory as YAML files. A workflow is an ordered list of agent steps. The output of each step becomes the input of the next.

### Workflow YAML Schema

```yaml
name: my-workflow         # Unique identifier passed to harness.py
description: "Optional"  # Human-readable description
steps:
  - name: planner         # Agent name (must exist in agents/)
  - name: implementer
  - name: reviewer
    loop_on: UNAPPROVED   # If this keyword appears in the step's output...
    loop_to: implementer  # ...jump back to this earlier step
    max_loops: 3          # Max times to loop (default: 3)
```

### Running a Workflow

```bash
python harness.py workflow <workflow-name> "<task description>"
```

The `<task description>` is sent to the first agent. Each subsequent agent receives the previous agent's text output as its input.

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
agents/           # Agent YAML definitions
workflows/        # Workflow YAML definitions
skills/           # Skill markdown files
main.py           # Interactive single-agent REPL
harness.py        # Workflow pipeline runner
agent_openrouter.py  # Agent loop + API calls
tools.py          # Built-in tool definitions
mcp_client.py     # MCP subprocess client
skills_loader.py  # Skill loading + prompt injection
.mcp.json         # MCP server registry
```
