# Structured Outputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace substring-based control flow (STOP, REJECTED) with schema-validated structured outputs via an injected `submit_result` tool.

**Architecture:** Steps with `response_schema` in the workflow YAML get a `submit_result` tool auto-generated and injected at runtime. `agent_loop` intercepts calls to this tool and returns parsed arguments in a `"result"` key. `run_pipeline` evaluates `field == value` expressions against the structured result for `loop_on`, `stop_on`, and `when` conditions. Steps without `response_schema` continue to work with substring matching.

**Tech Stack:** Python 3.12, pytest, YAML workflows

---

## File Structure

- **Modify:** `harness.py` -- Add `response_schema`/`stop_on` to `StepConfig`, add `build_submit_result_tool()` and `eval_condition()` helpers, update `load_workflow` validation, update `run_pipeline` control flow
- **Modify:** `agent_openrouter.py` -- Add `submit_result_schema` parameter to `agent_loop`, intercept `submit_result` tool calls
- **Modify:** `tests/test_harness.py` -- Tests for all new behavior
- **Modify:** `workflows/pick-and-fix.yaml` -- Update to use `response_schema`

---

### Task 1: `build_submit_result_tool` helper

**Files:**
- Modify: `harness.py` (add function after `parse_artifacts`, around line 158)
- Test: `tests/test_harness.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_submit_result_tool_generates_openai_format():
    """build_submit_result_tool generates an OpenAI-compatible tool dict from response_schema."""
    from harness import build_submit_result_tool

    schema = {
        "decision": {"type": "string", "enum": ["APPROVED", "REJECTED"]},
        "feedback": {"type": "string"},
    }
    tool = build_submit_result_tool(schema)

    assert tool["type"] == "function"
    assert tool["function"]["name"] == "submit_result"
    params = tool["function"]["parameters"]
    assert params["type"] == "object"
    assert params["properties"]["decision"] == {"type": "string", "enum": ["APPROVED", "REJECTED"]}
    assert params["properties"]["feedback"] == {"type": "string"}
    assert set(params["required"]) == {"decision", "feedback"}


def test_build_submit_result_tool_number_and_boolean():
    """build_submit_result_tool handles number and boolean types."""
    from harness import build_submit_result_tool

    schema = {
        "confidence": {"type": "number"},
        "approved": {"type": "boolean"},
    }
    tool = build_submit_result_tool(schema)

    params = tool["function"]["parameters"]
    assert params["properties"]["confidence"] == {"type": "number"}
    assert params["properties"]["approved"] == {"type": "boolean"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py::test_build_submit_result_tool_generates_openai_format tests/test_harness.py::test_build_submit_result_tool_number_and_boolean -v`
Expected: FAIL with `ImportError` (function does not exist)

- [ ] **Step 3: Implement `build_submit_result_tool`**

Add to `harness.py` after the `parse_artifacts` function (after line 157):

```python
def build_submit_result_tool(response_schema: dict) -> dict:
    """Generate an OpenAI-format tool definition from a response_schema dict."""
    properties = {}
    for field_name, field_def in response_schema.items():
        prop: dict = {"type": field_def["type"]}
        if "enum" in field_def:
            prop["enum"] = field_def["enum"]
        properties[field_name] = prop
    return {
        "type": "function",
        "function": {
            "name": "submit_result",
            "description": "Submit your final structured result for this step. You MUST call this tool when you have reached your conclusion.",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(response_schema.keys()),
            },
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py::test_build_submit_result_tool_generates_openai_format tests/test_harness.py::test_build_submit_result_tool_number_and_boolean -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add harness.py tests/test_harness.py
git commit -m "feat: add build_submit_result_tool helper"
```

---

### Task 2: `eval_condition` helper

**Files:**
- Modify: `harness.py` (add function after `build_submit_result_tool`)
- Test: `tests/test_harness.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_eval_condition_match():
    """eval_condition returns True when field matches value."""
    from harness import eval_condition
    assert eval_condition("decision == REJECTED", {"decision": "REJECTED", "feedback": "bad"}) is True


def test_eval_condition_no_match():
    """eval_condition returns False when field does not match value."""
    from harness import eval_condition
    assert eval_condition("decision == REJECTED", {"decision": "APPROVED", "feedback": "good"}) is False


def test_eval_condition_missing_field():
    """eval_condition returns False when field is not in result."""
    from harness import eval_condition
    assert eval_condition("decision == REJECTED", {"feedback": "good"}) is False


def test_eval_condition_whitespace_handling():
    """eval_condition handles extra whitespace around field and value."""
    from harness import eval_condition
    assert eval_condition("  decision  ==  REJECTED  ", {"decision": "REJECTED"}) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py::test_eval_condition_match tests/test_harness.py::test_eval_condition_no_match tests/test_harness.py::test_eval_condition_missing_field tests/test_harness.py::test_eval_condition_whitespace_handling -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `eval_condition`**

Add to `harness.py` after `build_submit_result_tool`:

```python
def eval_condition(expr: str, result: dict) -> bool:
    """Evaluate a 'field == value' expression against a structured result dict."""
    parts = expr.split("==", 1)
    if len(parts) != 2:
        return False
    field = parts[0].strip()
    value = parts[1].strip()
    return str(result.get(field, "")) == value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py::test_eval_condition_match tests/test_harness.py::test_eval_condition_no_match tests/test_harness.py::test_eval_condition_missing_field tests/test_harness.py::test_eval_condition_whitespace_handling -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add harness.py tests/test_harness.py
git commit -m "feat: add eval_condition helper for structured field comparison"
```

---

### Task 3: `StepConfig` and `load_workflow` validation

**Files:**
- Modify: `harness.py:35-106` -- Add `response_schema` and `stop_on` to `StepConfig`, add validation in `load_workflow`
- Test: `tests/test_harness.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_load_workflow_step_with_response_schema(tmp_path):
    """response_schema is parsed from YAML and returned in step dict."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: reviewer\n"
        "    response_schema:\n"
        "      decision:\n"
        "        type: string\n"
        "        enum: [APPROVED, REJECTED]\n"
        "      feedback:\n"
        "        type: string\n"
    )
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps[0]["response_schema"] == {
        "decision": {"type": "string", "enum": ["APPROVED", "REJECTED"]},
        "feedback": {"type": "string"},
    }


def test_load_workflow_step_without_response_schema_is_none(tmp_path):
    """Steps without response_schema have response_schema=None."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text("name: mywf\nsteps:\n  - name: agent1\n")
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps[0]["response_schema"] is None
    assert steps[0]["stop_on"] is None


def test_load_workflow_stop_on_without_response_schema_raises(tmp_path):
    """stop_on without response_schema raises ValueError."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: agent1\n"
        "    stop_on: status == STOP\n"
    )
    from harness import load_workflow
    with pytest.raises(ValueError, match="response_schema"):
        load_workflow("mywf", workflows_dir=tmp_path)


def test_load_workflow_stop_on_and_loop_on_raises(tmp_path):
    """Step cannot have both stop_on and loop_on."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: implementer\n"
        "  - name: reviewer\n"
        "    response_schema:\n"
        "      decision:\n"
        "        type: string\n"
        "        enum: [APPROVED, REJECTED, STOP]\n"
        "    stop_on: decision == STOP\n"
        "    loop_on: decision == REJECTED\n"
        "    loop_to: implementer\n"
    )
    from harness import load_workflow
    with pytest.raises(ValueError, match="stop_on.*loop_on"):
        load_workflow("mywf", workflows_dir=tmp_path)


def test_load_workflow_response_schema_field_missing_type_raises(tmp_path):
    """response_schema field without type raises ValueError."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: agent1\n"
        "    response_schema:\n"
        "      decision:\n"
        "        enum: [YES, NO]\n"
    )
    from harness import load_workflow
    with pytest.raises(ValueError, match="type"):
        load_workflow("mywf", workflows_dir=tmp_path)


def test_load_workflow_loop_on_with_schema_validates_field(tmp_path):
    """loop_on with response_schema validates that the field exists in the schema."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: implementer\n"
        "  - name: reviewer\n"
        "    response_schema:\n"
        "      decision:\n"
        "        type: string\n"
        "        enum: [APPROVED, REJECTED]\n"
        "    loop_on: nonexistent == REJECTED\n"
        "    loop_to: implementer\n"
    )
    from harness import load_workflow
    with pytest.raises(ValueError, match="nonexistent"):
        load_workflow("mywf", workflows_dir=tmp_path)


def test_load_workflow_loop_on_with_schema_validates_enum_value(tmp_path):
    """loop_on value must be in the enum if the field has one."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: implementer\n"
        "  - name: reviewer\n"
        "    response_schema:\n"
        "      decision:\n"
        "        type: string\n"
        "        enum: [APPROVED, REJECTED]\n"
        "    loop_on: decision == INVALID\n"
        "    loop_to: implementer\n"
    )
    from harness import load_workflow
    with pytest.raises(ValueError, match="INVALID"):
        load_workflow("mywf", workflows_dir=tmp_path)


def test_load_workflow_loop_on_with_schema_valid(tmp_path):
    """loop_on with response_schema and valid field/value passes validation."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: implementer\n"
        "  - name: reviewer\n"
        "    response_schema:\n"
        "      decision:\n"
        "        type: string\n"
        "        enum: [APPROVED, REJECTED]\n"
        "      feedback:\n"
        "        type: string\n"
        "    loop_on: decision == REJECTED\n"
        "    loop_to: implementer\n"
    )
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps[1]["loop_on"] == "decision == REJECTED"
    assert steps[1]["response_schema"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py -k "response_schema or stop_on" -v`
Expected: FAIL (new fields not in StepConfig, validation not implemented)

- [ ] **Step 3: Update `StepConfig` TypedDict**

In `harness.py`, add to the `StepConfig` class (around line 35):

```python
class StepConfig(TypedDict):
    name: str
    id: NotRequired[str | None]
    prompt: str | None
    inputs: NotRequired[list[str] | None]
    outputs: NotRequired[dict[str, str] | None]
    when: NotRequired[str | None]
    loop_on: NotRequired[str | None]
    loop_to: NotRequired[str | None]
    max_loops: NotRequired[int | None]
    response_schema: NotRequired[dict | None]
    stop_on: NotRequired[str | None]
```

- [ ] **Step 4: Update `load_workflow` to parse and validate new fields**

In `load_workflow` (around line 47), add parsing of `response_schema` and `stop_on` after the existing field parsing (after `when` parsing around line 66), and add validation. The changes go inside the `for step in data.get("steps", []):` loop.

After `when: str | None = step.get("when") or None` (line 66), add:

```python
                response_schema: dict | None = step.get("response_schema") or None
                stop_on: str | None = step.get("stop_on") or None
```

Add validation after the existing `when` validation block (after line 90):

```python
                if response_schema is not None:
                    for field_name, field_def in response_schema.items():
                        if "type" not in field_def:
                            raise ValueError(f"Step '{step_name}' response_schema field '{field_name}' must have a 'type'.")
                        if "enum" in field_def and not isinstance(field_def["enum"], list):
                            raise ValueError(f"Step '{step_name}' response_schema field '{field_name}' enum must be a list.")
                if stop_on is not None and response_schema is None:
                    raise ValueError(f"Step '{step_name}' has stop_on but no response_schema.")
                if stop_on is not None and loop_on is not None:
                    raise ValueError(f"Step '{step_name}' cannot have both stop_on and loop_on.")
                if loop_on is not None and response_schema is not None:
                    parts = loop_on.split("==", 1)
                    if len(parts) != 2:
                        raise ValueError(f"Step '{step_name}' loop_on must be 'field == value' when response_schema is set.")
                    field = parts[0].strip()
                    value = parts[1].strip()
                    if field not in response_schema:
                        raise ValueError(f"Step '{step_name}' loop_on references unknown field '{field}' not in response_schema.")
                    field_def = response_schema[field]
                    if "enum" in field_def and value not in field_def["enum"]:
                        raise ValueError(f"Step '{step_name}' loop_on value '{value}' is not in enum {field_def['enum']}.")
```

Add `response_schema` and `stop_on` to the `steps.append(...)` dict (around line 91):

```python
                steps.append({
                    "name": step_name,
                    "id": step_id,
                    "prompt": step.get("prompt") or None,
                    "inputs": inputs,
                    "outputs": outputs,
                    "when": when,
                    "loop_on": loop_on,
                    "loop_to": loop_to,
                    "max_loops": max_loops,
                    "response_schema": response_schema,
                    "stop_on": stop_on,
                })
```

- [ ] **Step 5: Update existing tests that assert full step dicts**

Tests `test_load_workflow_finds_by_name` and `test_load_workflow_step_with_prompt` assert exact step dicts. Add `"response_schema": None, "stop_on": None` to their expected dicts.

- [ ] **Step 6: Run all tests to verify they pass**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add harness.py tests/test_harness.py
git commit -m "feat: add response_schema and stop_on to StepConfig with validation"
```

---

### Task 4: `agent_loop` intercepts `submit_result`

**Files:**
- Modify: `agent_openrouter.py:105-234` -- Add `submit_result_schema` parameter, intercept tool call
- Test: `tests/test_harness.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_agent_loop_intercepts_submit_result(monkeypatch):
    """agent_loop returns structured result when submit_result tool is called."""
    from unittest.mock import patch
    from agent_openrouter import agent_loop
    from harness import build_submit_result_tool

    schema = {
        "decision": {"type": "string", "enum": ["APPROVED", "REJECTED"]},
        "feedback": {"type": "string"},
    }
    submit_tool = build_submit_result_tool(schema)

    # Simulate streaming response: first chunk has tool call to submit_result
    chunks = [
        {
            "choices": [{
                "finish_reason": "tool_calls",
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call_123",
                        "function": {
                            "name": "submit_result",
                            "arguments": '{"decision": "REJECTED", "feedback": "needs tests"}'
                        }
                    }]
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.01}
        },
    ]

    with patch("agent_openrouter.call_api_streaming", return_value=iter(chunks)):
        messages = [{"role": "system", "content": "You are a reviewer."}]
        usage = agent_loop("Review this", messages, submit_result_schema=submit_tool)

    assert usage["result"] == {"decision": "REJECTED", "feedback": "needs tests"}
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50


def test_agent_loop_without_submit_result_schema_works_unchanged(monkeypatch):
    """agent_loop without submit_result_schema works exactly as before."""
    from unittest.mock import patch
    from agent_openrouter import agent_loop

    chunks = [
        {
            "choices": [{
                "finish_reason": "stop",
                "delta": {"content": "Looks good. APPROVED"}
            }],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20, "cost": 0.005}
        },
    ]

    with patch("agent_openrouter.call_api_streaming", return_value=iter(chunks)):
        messages = [{"role": "system", "content": "You are a reviewer."}]
        usage = agent_loop("Review this", messages)

    assert "result" not in usage
    assert usage["input_tokens"] == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py::test_agent_loop_intercepts_submit_result tests/test_harness.py::test_agent_loop_without_submit_result_schema_works_unchanged -v`
Expected: FAIL (`submit_result_schema` not a valid parameter)

- [ ] **Step 3: Implement `submit_result` interception in `agent_loop`**

In `agent_openrouter.py`, modify the `agent_loop` function:

1. Add `submit_result_schema: dict | None = None` parameter (line 112, after `step_label`):

```python
def agent_loop(
    user_message: str,
    messages: list,
    model: str = MODEL,
    cancel_event: threading.Event | None = None,
    mcp_clients: list | None = None,
    tools: list | None = None,
    trace: object | None = None,
    step_label: str | None = None,
    submit_result_schema: dict | None = None,
) -> dict:
```

2. After building `active_tools` (after line 122), inject the submit_result tool:

```python
    if submit_result_schema is not None:
        active_tools.append(submit_result_schema)
```

3. In the tool execution block (around line 195-228), before the existing tool execution loop, add handling for `submit_result`. Replace the tool execution block:

```python
            if finish_reason == "tool_calls" and tool_calls:
                tool_results = []
                structured_result = None
                for tool_call in tool_calls:
                    name = tool_call["function"]["name"]
                    raw_args = tool_call["function"]["arguments"]
                    try:
                        params = json.loads(raw_args)
                    except json.JSONDecodeError as e:
                        print(f"  [Error: malformed tool call arguments for '{name}': {e}]")
                        print(f"  Raw arguments: {raw_args[:200]}")
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": f"[AGENT_ERROR] Failed to parse tool arguments for '{name}': {e}",
                        })
                        continue
                    if name == "submit_result" and submit_result_schema is not None:
                        print(f"  [submit_result] {params}")
                        structured_result = params
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": "Result accepted.",
                        })
                        continue
                    params_str = str(params)
                    if len(params_str) > 50:
                        params_str = params_str[:50] + "..."
                    print(f"  [Tool: {name}], params: {params_str}")
                    if trace is not None:
                        trace.log(step=step_label, event="tool_call", tool=name, params=params)
                    result = execute_tool(name, params, tool_handlers, mcp_clients)
                    if trace is not None:
                        from trace import _preview
                        trace.log(step=step_label, event="tool_result", tool=name,
                                  result_preview=_preview(result),
                                  error=result if result.startswith("Error:") else None)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result,
                    })
                messages.extend(tool_results)
                if structured_result is not None:
                    return {"input_tokens": total_input, "output_tokens": total_output, "cost": total_cost, "result": structured_result}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py::test_agent_loop_intercepts_submit_result tests/test_harness.py::test_agent_loop_without_submit_result_schema_works_unchanged -v`
Expected: PASS

- [ ] **Step 5: Run all existing tests to verify nothing broke**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add agent_openrouter.py tests/test_harness.py
git commit -m "feat: agent_loop intercepts submit_result tool calls"
```

---

### Task 5: `run_pipeline` structured control flow

**Files:**
- Modify: `harness.py:160-308` -- Update `run_pipeline` to use structured results for `stop_on` and `loop_on`
- Test: `tests/test_harness.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_run_pipeline_stop_on_structured_result(tmp_path):
    """Pipeline exits early when stop_on condition matches structured result."""
    from unittest.mock import patch
    from harness import run_pipeline

    call_count = [0]

    def fake_agent_loop(user_message, messages, **kwargs):
        call_count[0] += 1
        messages.append({"role": "assistant", "content": "No cards found."})
        return {"result": {"status": "STOP", "context": ""}}

    steps = [
        {"name": "agent1", "prompt": None, "response_schema": {"status": {"type": "string", "enum": ["FOUND", "STOP"]}, "context": {"type": "string"}}, "stop_on": "status == STOP"},
        {"name": "agent2", "prompt": None},
    ]

    with patch("harness.load_agent", return_value=_agent_config()), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Do the thing", traces_dir=tmp_path)

    assert call_count[0] == 1


def test_run_pipeline_loop_on_structured_result(tmp_path):
    """Pipeline loops back when loop_on condition matches structured result."""
    from unittest.mock import patch
    from harness import run_pipeline

    call_log = []
    call_count = [0]

    def fake_load_agent(name, **kwargs):
        return _agent_config()

    def fake_agent_loop(user_message, messages, **kwargs):
        call_count[0] += 1
        call_log.append(call_count[0])
        if call_count[0] == 1:
            messages.append({"role": "assistant", "content": "impl v1"})
            return {}
        elif call_count[0] == 2:
            messages.append({"role": "assistant", "content": "Needs work."})
            return {"result": {"decision": "REJECTED", "feedback": "missing tests"}}
        elif call_count[0] == 3:
            messages.append({"role": "assistant", "content": "impl v2"})
            return {}
        else:
            messages.append({"role": "assistant", "content": "Looks good."})
            return {"result": {"decision": "APPROVED", "feedback": "all good"}}

    steps = [
        {"name": "implementer", "prompt": None},
        {"name": "reviewer", "prompt": None,
         "response_schema": {"decision": {"type": "string", "enum": ["APPROVED", "REJECTED"]}, "feedback": {"type": "string"}},
         "loop_on": "decision == REJECTED", "loop_to": "implementer", "max_loops": 3},
    ]

    with patch("harness.load_agent", side_effect=fake_load_agent), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Fix the bug", traces_dir=tmp_path)

    assert call_count[0] == 4  # impl, review(REJECTED), impl, review(APPROVED)


def test_run_pipeline_structured_no_loop_when_condition_not_met(tmp_path):
    """Pipeline does not loop when structured result does not match loop_on."""
    from unittest.mock import patch
    from harness import run_pipeline

    call_count = [0]

    def fake_load_agent(name, **kwargs):
        return _agent_config()

    def fake_agent_loop(user_message, messages, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            messages.append({"role": "assistant", "content": "impl done"})
            return {}
        else:
            messages.append({"role": "assistant", "content": "Approved."})
            return {"result": {"decision": "APPROVED", "feedback": "great"}}

    steps = [
        {"name": "implementer", "prompt": None},
        {"name": "reviewer", "prompt": None,
         "response_schema": {"decision": {"type": "string", "enum": ["APPROVED", "REJECTED"]}, "feedback": {"type": "string"}},
         "loop_on": "decision == REJECTED", "loop_to": "implementer", "max_loops": 3},
    ]

    with patch("harness.load_agent", side_effect=fake_load_agent), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Fix the bug", traces_dir=tmp_path)

    assert call_count[0] == 2  # impl, review(APPROVED) -- no loop


def test_run_pipeline_passes_submit_result_schema_to_agent_loop(tmp_path):
    """run_pipeline passes the submit_result_schema to agent_loop when step has response_schema."""
    from unittest.mock import patch
    from harness import run_pipeline

    captured_kwargs = []

    def fake_agent_loop(user_message, messages, **kwargs):
        captured_kwargs.append(kwargs)
        messages.append({"role": "assistant", "content": "done"})
        return {"result": {"status": "FOUND", "context": "card info"}}

    steps = [
        {"name": "agent1", "prompt": None,
         "response_schema": {"status": {"type": "string"}, "context": {"type": "string"}}},
    ]

    with patch("harness.load_agent", return_value=_agent_config()), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Do the thing", traces_dir=tmp_path)

    assert "submit_result_schema" in captured_kwargs[0]
    assert captured_kwargs[0]["submit_result_schema"]["function"]["name"] == "submit_result"


def test_run_pipeline_no_schema_no_submit_result_kwarg(tmp_path):
    """run_pipeline passes submit_result_schema=None when step has no response_schema."""
    from unittest.mock import patch
    from harness import run_pipeline

    captured_kwargs = []

    def fake_agent_loop(user_message, messages, **kwargs):
        captured_kwargs.append(kwargs)
        messages.append({"role": "assistant", "content": "done"})
        return {}

    steps = [
        {"name": "agent1", "prompt": None},
    ]

    with patch("harness.load_agent", return_value=_agent_config()), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Do the thing", traces_dir=tmp_path)

    assert captured_kwargs[0].get("submit_result_schema") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py -k "structured" -v`
Expected: FAIL

- [ ] **Step 3: Update `run_pipeline` to build and pass schema, and evaluate structured conditions**

In `harness.py`'s `run_pipeline`, make these changes:

1. After building `effective_input` (around line 222), build and pass the schema:

```python
                response_schema = step.get("response_schema")
                submit_schema = build_submit_result_tool(response_schema) if response_schema else None
```

2. Update the `agent_loop` call (around line 231) to pass the schema:

```python
                    usage = agent_loop(effective_input, messages, model=model, tools=agent["tools"],
                                       mcp_clients=mcp_clients, trace=trace, step_label=step_label,
                                       submit_result_schema=submit_schema)
```

3. After getting `step_output` and handling `step_id`/`declared_outputs` (after line 266), add structured `stop_on` evaluation. Replace the existing `STOP` check block (lines 272-276):

```python
                structured_result = usage.get("result")
                stop_on = step.get("stop_on")
                if stop_on and structured_result and eval_condition(stop_on, structured_result):
                    print("Nothing to do.", file=sys.stderr)
                    print(f"\n[total usage]  in={total_input_tokens:,}  out={total_output_tokens:,}  cost=${total_cost:.4f}")
                    trace.status = "completed"
                    return
                elif not stop_on and "STOP" in (step_output or ""):
                    print("Nothing to do.", file=sys.stderr)
                    print(f"\n[total usage]  in={total_input_tokens:,}  out={total_output_tokens:,}  cost=${total_cost:.4f}")
                    trace.status = "completed"
                    return
```

4. Replace the existing `loop_on` check block (lines 277-290):

```python
                loop_on = step.get("loop_on")
                loop_to = step.get("loop_to")
                max_loops = step.get("max_loops")
                if loop_on and loop_to:
                    loop_triggered = False
                    if structured_result and response_schema:
                        loop_triggered = eval_condition(loop_on, structured_result)
                    else:
                        loop_triggered = loop_on in (step_output or "")
                    if loop_triggered:
                        count = loop_counts.get(step_name, 0)
                        if count < max_loops:
                            loop_counts[step_name] = count + 1
                            print(f"[loop] '{step_name}' triggered '{loop_on}' (loop {count + 1}/{max_loops}), jumping to '{loop_to}'", file=sys.stderr)
                            trace.log(step=step_label, event="loop", loop_on=loop_on, loop_to=loop_to,
                                      iteration=count + 1, max=max_loops)
                            step_index = step_index_map[loop_to]
                            continue
                        else:
                            print(f"[loop] '{step_name}' hit max_loops={max_loops}; continuing to next step.", file=sys.stderr)
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py -k "structured" -v`
Expected: PASS

- [ ] **Step 5: Run all tests to verify nothing broke**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py -v`
Expected: ALL PASS (including old substring-based tests which should still work via fallback)

- [ ] **Step 6: Commit**

```bash
git add harness.py tests/test_harness.py
git commit -m "feat: run_pipeline uses structured results for stop_on and loop_on"
```

---

### Task 6: Update `pick-and-fix.yaml` workflow

**Files:**
- Modify: `workflows/pick-and-fix.yaml`

- [ ] **Step 1: Update the workflow file**

Replace the contents of `workflows/pick-and-fix.yaml`:

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

- [ ] **Step 2: Verify the workflow loads without errors**

Run: `cd /Users/jos/projects/agent-harness && python -c "from harness import load_workflow; steps = load_workflow('pick-and-fix'); print(f'{len(steps)} steps loaded OK')"`
Expected: `6 steps loaded OK`

- [ ] **Step 3: Run dry-run to verify resolution**

Run: `cd /Users/jos/projects/agent-harness && python harness.py workflow pick-and-fix --dry-run`
Expected: Prints pipeline config without errors

- [ ] **Step 4: Run all tests one final time**

Run: `cd /Users/jos/projects/agent-harness && python -m pytest tests/test_harness.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add workflows/pick-and-fix.yaml
git commit -m "feat: update pick-and-fix workflow to use structured outputs"
```
