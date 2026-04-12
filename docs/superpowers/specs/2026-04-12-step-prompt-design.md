# Step Prompt Design

**Date:** 2026-04-12

## Context

Workflows chain agents sequentially, passing each agent's output as the next agent's input. Currently, workflow steps carry only an agent name — there is no way to add per-step guidance in the workflow definition. This makes it hard to steer individual steps (e.g., "focus on sub-tasks" for the planner, "check tests pass" for the reviewer) without baking that guidance into the agent's system prompt.

## Feature

Add an optional `prompt` field to workflow steps. When present, it is appended to the input that step receives (which is either the initial job/command prompt or the previous step's output). This applies to every step, including the first.

## YAML Schema

Steps may be a plain string (backwards-compatible) or a dict:

```yaml
name: pick-and-fix
steps:
  - name: planner
    prompt: "Break this into clear sub-tasks with file paths."
  - name: implementer          # no prompt — works as before
  - name: reviewer
    prompt: "Check that tests pass and nothing is left TODO."
```

## Data Flow

```
initial_input = job/command prompt

for each step:
    if step.prompt:
        input = previous_output + "\n\n" + step.prompt
    else:
        input = previous_output
    output = agent_loop(input, ...)
    previous_output = output
```

## Code Changes

**`harness.py` — `load_workflow()`**

Parse each step as either a string or dict; always return a list of dicts:

```python
return [
    {"name": s} if isinstance(s, str) else {"name": s["name"], "prompt": s.get("prompt")}
    for s in data["steps"]
]
```

**`harness.py` — `run_pipeline()`**

Rename parameter `step_names` → `steps`. Unpack name and prompt per step:

```python
for step in steps:
    step_name = step["name"]
    # ... existing agent loading ...
    if step.get("prompt"):
        current_input = current_input + "\n\n" + step["prompt"]
    usage = agent_loop(current_input, ...)
```

**`load_job()`** — no change needed; it calls `load_workflow()` and forwards its result.

**Tests** — update any assertions that check `load_workflow()` return values or `run_pipeline()` step arguments as plain strings.

## Verification

1. Run existing test suite: `pytest` — all tests pass (backwards compatibility)
2. Add a workflow YAML with a step prompt and run it end-to-end: confirm the appended text appears in the `[prompt]` log line for that step
3. Confirm a workflow with no step prompts behaves identically to before
4. Confirm first-step prompt is appended to the initial job prompt
