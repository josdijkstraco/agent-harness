# Structured Outputs via `submit_result` Tool

Replace fragile substring matching on agent free-text with schema-validated structured outputs using an injected `submit_result` tool.

## Problem

Control flow decisions (`STOP`, `REJECTED`, `APPROVED`) and artifact extraction rely on substring matching and regex against raw agent text output. This is fragile -- false positives occur if the agent incidentally uses these keywords in reasoning (e.g. "I did not STOP the process").

## Approach

Steps that need structured decisions declare a `response_schema` in the workflow YAML. At runtime, the pipeline generates a `submit_result` tool from the schema and injects it into the agent's tool list. The agent streams text as usual for reasoning, then calls `submit_result` with typed fields. The pipeline reads structured fields for control flow instead of substring matching.

## Design

### 1. Workflow YAML Schema Changes

Steps gain an optional `response_schema` field and a new `stop_on` field. When `response_schema` is present, `loop_on` and `when` use `field == value` expressions instead of substring patterns.

**Before:**
```yaml
- name: reviewer
  prompt: Review the fix...
  loop_on: REJECTED
  loop_to: implementer
  max_loops: 3
```

**After:**
```yaml
- name: reviewer
  prompt: Review the fix...
  response_schema:
    decision:
      type: string
      enum: [APPROVED, REJECTED]
    feedback:
      type: string
  loop_on: decision == REJECTED
  loop_to: implementer
  max_loops: 3
```

`stop_on` is a new field for early pipeline exit:
```yaml
- name: linear
  id: card
  prompt: Pick a card...
  response_schema:
    status:
      type: string
      enum: [FOUND, STOP]
    context:
      type: string
  stop_on: status == STOP
```

**Backward compatibility:** Steps without `response_schema` work exactly as today -- substring matching on `loop_on`/`when`, regex for `outputs`.

### 2. `submit_result` Tool Generation

A new function `build_submit_result_schema(response_schema: dict) -> dict` generates an OpenAI-format tool definition from the YAML schema.

Given this `response_schema`:
```yaml
response_schema:
  decision:
    type: string
    enum: [APPROVED, REJECTED]
  feedback:
    type: string
```

The generated tool:
```python
{
    "type": "function",
    "function": {
        "name": "submit_result",
        "description": "Submit your final structured result for this step. You MUST call this tool when you have reached your conclusion.",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["APPROVED", "REJECTED"]},
                "feedback": {"type": "string"}
            },
            "required": ["decision", "feedback"]
        }
    }
}
```

Key details:
- All fields in `response_schema` are required by default.
- The tool description instructs the agent it must call it.
- The tool is injected at pipeline runtime per step, not baked into agent configs. The same agent definition (e.g. `reviewer`) works in workflows with or without `response_schema`.

### 3. Agent Loop Changes

`agent_loop` gains an optional `submit_result_schema` parameter.

**Signature change:**
```python
def agent_loop(
    user_message: str,
    messages: list,
    ...
    submit_result_schema: dict | None = None,
) -> dict:
```

When `submit_result_schema` is passed:
1. The generated `submit_result` tool is added to `active_tools`.
2. When a tool call with `name == "submit_result"` is encountered, its parsed arguments are stored in the return dict under `"result"`. A tool result message "Result accepted." is appended to keep the conversation valid. The agent loop breaks.
3. Other tool calls in the same response are executed normally before `submit_result` is processed.

**Return value:**
```python
# Without structured result:
{"input_tokens": 100, "output_tokens": 50, "cost": 0.01}

# With structured result:
{"input_tokens": 100, "output_tokens": 50, "cost": 0.01,
 "result": {"decision": "REJECTED", "feedback": "Missing error handling..."}}
```

**Fallback:** If the agent finishes (`finish_reason == "stop"`) without calling `submit_result`, the return dict has no `"result"` key. The pipeline falls back to substring matching on text output and logs a warning.

### 4. Pipeline Changes in `run_pipeline`

**Schema passing:**
```python
schema = step.get("response_schema")
submit_schema = build_submit_result_schema(schema) if schema else None
usage = agent_loop(..., submit_result_schema=submit_schema)
```

**Control flow evaluation:** After `agent_loop` returns, if `"result"` is in usage:
- `stop_on`: Evaluate against `usage["result"]` -- exit pipeline if true.
- `loop_on`: Evaluate against `usage["result"]` -- jump to `loop_to` if true.
- `when`: Evaluate against stored structured results from referenced steps.
- `outputs`/artifacts: Structured result fields can be stored directly into `step_outputs`.

If `"result"` is NOT in usage, fall back to today's substring matching. Log a warning.

**Expression evaluator:**
```python
def eval_condition(expr: str, result: dict) -> bool:
    field, value = expr.split(" == ", 1)
    return result.get(field.strip()) == value.strip()
```

**`StepConfig` TypedDict additions:** `response_schema: NotRequired[dict | None]` and `stop_on: NotRequired[str | None]`.

### 5. Workflow Validation Changes

New validations in `load_workflow`:

1. **`response_schema` structure** -- Each field must have at least a `type`. If `enum` is present, it must be a list. Supported types: `string`, `number`, `boolean`.
2. **`stop_on` requires `response_schema`** -- Error if `stop_on` is present without `response_schema`.
3. **`loop_on` with `response_schema`** -- If both are present, validate `loop_on` is in `field == value` format. Validate the field exists in the schema. If the field has an `enum`, validate the value is in it.
4. **`when` with structured references** -- When a `when` clause references a step that has `response_schema`, the `when` expression uses `field == value in step_id` format (e.g. `status == FOUND in card`). Validate the field name exists in the referenced step's schema. When the referenced step has no `response_schema`, the existing `PATTERN in step_id` substring behavior applies.
5. **`stop_on` and `loop_on` are mutually exclusive.**

### 6. Updated `pick-and-fix.yaml`

```yaml
name: pick-and-fix
description: Pick a card and fix it.
steps:
  - name: linear
    id: card
    prompt: |
      Pick a card from the 'Agent Harness' project that is in the 'todo' column
      and move it to the 'in progress' column. Your final response needs to include
      the context of the card. If you don't find any cards, call submit_result with status STOP.
    response_schema:
      status:
        type: string
        enum: [FOUND, STOP]
      context:
        type: string
    stop_on: status == STOP

  - name: planner
    prompt: |
      Plan the fix for the request.

  - name: implementer
    id: implementer
    prompt: |
      Implement the fix.

  - name: reviewer
    prompt: |
      Review the fix. Call submit_result with your verdict.
    response_schema:
      decision:
        type: string
        enum: [APPROVED, REJECTED]
      feedback:
        type: string
    loop_on: decision == REJECTED
    loop_to: implementer
    max_loops: 3

  - name: github
    prompt: |
      Create a pull request for the fix. Create a summary of the changes for this pull request.
    inputs: [implementer]

  - name: linear
    prompt: |
      Move the card to the 'done' column.
    inputs: [card]
```

## Files Changed

- `harness.py` -- `StepConfig`, `load_workflow` validation, `build_submit_result_schema`, `run_pipeline` control flow, `eval_condition`
- `agent_openrouter.py` -- `agent_loop` gains `submit_result_schema` parameter, intercepts `submit_result` tool calls
- `workflows/pick-and-fix.yaml` -- Updated to use `response_schema`

## Not In Scope

- Changing the `outputs`/artifact system (regex-based extraction of fenced code blocks) -- that continues to work as-is for steps that use it.
- Changing agent YAML definitions -- `response_schema` lives in the workflow, not the agent.
- Removing backward compatibility for substring-based `loop_on`/`when` -- both old and new styles work.
