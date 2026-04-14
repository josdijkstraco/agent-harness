# Trace Logging & Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured trace logging to workflow pipeline runs for debugging, cost analysis, and step-level replay.

**Architecture:** A `Trace` object is created in `run_pipeline` and passed into `agent_loop`. Both log events at key points. Traces are saved as JSON files in `traces/`. Conversation snapshots are saved per-step for replay support.

**Tech Stack:** Python 3.12, pytest, JSON files for storage.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `trace.py` | Create | `TraceEvent` dataclass, `Trace` class with `log()`, `save()`, loading, and formatting |
| `agent_openrouter.py` | Modify | Accept optional `trace` param in `agent_loop`, log `api_call`, `tool_call`, `tool_result` |
| `harness.py` | Modify | Create `Trace` in `run_pipeline`, log pipeline/step events, save snapshots, add CLI subcommands |
| `.gitignore` | Modify | Add `traces/` |
| `tests/test_trace.py` | Create | Tests for `Trace` and `TraceEvent` |
| `tests/test_harness.py` | Modify | Tests for trace integration in `run_pipeline` and CLI subcommands |

---

### Task 1: TraceEvent and Trace core

**Files:**
- Create: `trace.py`
- Create: `tests/test_trace.py`

- [ ] **Step 1: Write failing test for TraceEvent creation**

```python
# tests/test_trace.py
import time
from trace import TraceEvent, Trace


def test_trace_event_creation():
    ts = time.time()
    event = TraceEvent(timestamp=ts, step="0:planner", event="tool_call", data={"tool": "read_file"})
    assert event.timestamp == ts
    assert event.step == "0:planner"
    assert event.event == "tool_call"
    assert event.data == {"tool": "read_file"}


def test_trace_event_to_dict():
    ts = 1000.0
    event = TraceEvent(timestamp=ts, step=None, event="pipeline_start", data={"workflow": "example"})
    d = event.to_dict()
    assert d == {"timestamp": 1000.0, "step": None, "event": "pipeline_start", "data": {"workflow": "example"}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_trace.py::test_trace_event_creation tests/test_trace.py::test_trace_event_to_dict -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trace'` (well, `trace` is a stdlib module, but our local one will shadow it; the import will fail because our classes don't exist yet)

Note: Python has a stdlib `trace` module, but since we import from the local directory and this project uses direct imports (not packages), the local `trace.py` will shadow it. The stdlib `trace` module is not used anywhere in this project.

- [ ] **Step 3: Implement TraceEvent**

```python
# trace.py
"""Structured trace logging for workflow pipeline runs."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

PREVIEW_MAX = 500


def _preview(text: str) -> str:
    """Truncate text to PREVIEW_MAX characters."""
    if len(text) <= PREVIEW_MAX:
        return text
    return text[:PREVIEW_MAX] + "..."


@dataclass(frozen=True)
class TraceEvent:
    timestamp: float
    step: str | None
    event: str
    data: dict

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "step": self.step,
            "event": self.event,
            "data": self.data,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_trace.py::test_trace_event_creation tests/test_trace.py::test_trace_event_to_dict -v`
Expected: PASS

- [ ] **Step 5: Write failing test for Trace.log() and Trace.to_dict()**

```python
# tests/test_trace.py (append)

def test_trace_log_appends_event():
    trace = Trace(workflow="example", command="Fix bug")
    trace.log(step="0:planner", event="tool_call", tool="read_file", params={"path": "foo.py"})
    assert len(trace.events) == 1
    e = trace.events[0]
    assert e.step == "0:planner"
    assert e.event == "tool_call"
    assert e.data == {"tool": "read_file", "params": {"path": "foo.py"}}
    assert isinstance(e.timestamp, float)


def test_trace_to_dict():
    trace = Trace(workflow="example", command="Fix bug")
    trace.status = "completed"
    d = trace.to_dict()
    assert d["workflow"] == "example"
    assert d["command"] == "Fix bug"
    assert d["status"] == "completed"
    assert isinstance(d["id"], str)
    assert len(d["id"]) == 8
    assert d["events"] == []
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/test_trace.py::test_trace_log_appends_event tests/test_trace.py::test_trace_to_dict -v`
Expected: FAIL — `Trace` not defined

- [ ] **Step 7: Implement Trace class with log() and to_dict()**

```python
# trace.py (append after TraceEvent)

class Trace:
    def __init__(self, workflow: str, command: str) -> None:
        self.id = uuid4().hex[:8]
        self.workflow = workflow
        self.command = command
        self.started_at = time.time()
        self.events: list[TraceEvent] = []
        self.status = "running"

    def log(self, step: str | None = None, event: str = "", **data: object) -> None:
        self.events.append(TraceEvent(
            timestamp=time.time(),
            step=step,
            event=event,
            data=data,
        ))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow": self.workflow,
            "command": self.command,
            "started_at": self.started_at,
            "status": self.status,
            "events": [e.to_dict() for e in self.events],
        }
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_trace.py -v`
Expected: all 4 tests PASS

- [ ] **Step 9: Commit**

```bash
git add trace.py tests/test_trace.py
git commit -m "feat: add TraceEvent and Trace core classes"
```

---

### Task 2: Trace.save() and Trace.load()

**Files:**
- Modify: `trace.py`
- Modify: `tests/test_trace.py`

- [ ] **Step 1: Write failing test for save()**

```python
# tests/test_trace.py (append)

def test_trace_save_creates_json_file(tmp_path):
    trace = Trace(workflow="example", command="Fix bug")
    trace.log(step="0:planner", event="step_start", model="qwen")
    trace.status = "completed"
    trace.save(traces_dir=tmp_path)

    trace_file = tmp_path / f"{trace.id}.json"
    assert trace_file.exists()
    data = json.loads(trace_file.read_text())
    assert data["id"] == trace.id
    assert data["workflow"] == "example"
    assert data["status"] == "completed"
    assert len(data["events"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_trace.py::test_trace_save_creates_json_file -v`
Expected: FAIL — `Trace.save` not defined

- [ ] **Step 3: Implement save()**

```python
# trace.py — add to Trace class

    def save(self, traces_dir: str | Path = "traces") -> Path:
        """Save trace to a JSON file. Returns the path to the saved file."""
        traces_dir = Path(traces_dir)
        traces_dir.mkdir(parents=True, exist_ok=True)
        path = traces_dir / f"{self.id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_trace.py::test_trace_save_creates_json_file -v`
Expected: PASS

- [ ] **Step 5: Write failing test for load()**

```python
# tests/test_trace.py (append)

def test_trace_load_roundtrips(tmp_path):
    trace = Trace(workflow="example", command="Fix bug")
    trace.log(step="0:planner", event="step_start", model="qwen")
    trace.log(step="0:planner", event="tool_call", tool="read_file", params={"path": "x.py"})
    trace.status = "completed"
    trace.save(traces_dir=tmp_path)

    loaded = Trace.load(trace.id, traces_dir=tmp_path)
    assert loaded.id == trace.id
    assert loaded.workflow == "example"
    assert loaded.command == "Fix bug"
    assert loaded.status == "completed"
    assert len(loaded.events) == 2
    assert loaded.events[0].event == "step_start"
    assert loaded.events[1].data["tool"] == "read_file"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/test_trace.py::test_trace_load_roundtrips -v`
Expected: FAIL — `Trace.load` not defined

- [ ] **Step 7: Implement load()**

```python
# trace.py — add to Trace class as @classmethod

    @classmethod
    def load(cls, trace_id: str, traces_dir: str | Path = "traces") -> "Trace":
        """Load a trace from its JSON file."""
        path = Path(traces_dir) / f"{trace_id}.json"
        data = json.loads(path.read_text())
        trace = cls.__new__(cls)
        trace.id = data["id"]
        trace.workflow = data["workflow"]
        trace.command = data["command"]
        trace.started_at = data["started_at"]
        trace.status = data["status"]
        trace.events = [
            TraceEvent(
                timestamp=e["timestamp"],
                step=e["step"],
                event=e["event"],
                data=e["data"],
            )
            for e in data["events"]
        ]
        return trace
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_trace.py -v`
Expected: all tests PASS

- [ ] **Step 9: Commit**

```bash
git add trace.py tests/test_trace.py
git commit -m "feat: add Trace save/load for JSON persistence"
```

---

### Task 3: Conversation snapshots (save_snapshot / load_snapshot)

**Files:**
- Modify: `trace.py`
- Modify: `tests/test_trace.py`

- [ ] **Step 1: Write failing test for save_snapshot()**

```python
# tests/test_trace.py (append)

def test_trace_save_snapshot(tmp_path):
    trace = Trace(workflow="example", command="Fix bug")
    messages = [
        {"role": "system", "content": "You are a planner."},
        {"role": "user", "content": "Fix bug"},
        {"role": "assistant", "content": "Here is the plan."},
    ]
    trace.save_snapshot(step_index=0, step_name="planner", messages=messages, traces_dir=tmp_path)

    snapshot_dir = tmp_path / f"{trace.id}_messages"
    assert snapshot_dir.is_dir()
    snapshot_file = snapshot_dir / "step_0_planner.json"
    assert snapshot_file.exists()
    loaded = json.loads(snapshot_file.read_text())
    assert len(loaded) == 3
    assert loaded[2]["content"] == "Here is the plan."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_trace.py::test_trace_save_snapshot -v`
Expected: FAIL — `save_snapshot` not defined

- [ ] **Step 3: Implement save_snapshot()**

```python
# trace.py — add to Trace class

    def save_snapshot(self, step_index: int, step_name: str, messages: list, traces_dir: str | Path = "traces") -> Path:
        """Save the messages list after a step completes."""
        traces_dir = Path(traces_dir)
        snapshot_dir = traces_dir / f"{self.id}_messages"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = snapshot_dir / f"step_{step_index}_{step_name}.json"
        path.write_text(json.dumps(messages, indent=2))
        return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_trace.py::test_trace_save_snapshot -v`
Expected: PASS

- [ ] **Step 5: Write failing test for load_snapshot()**

```python
# tests/test_trace.py (append)

def test_trace_load_snapshot(tmp_path):
    trace = Trace(workflow="example", command="Fix bug")
    messages = [{"role": "user", "content": "hello"}]
    trace.save_snapshot(step_index=2, step_name="reviewer", messages=messages, traces_dir=tmp_path)

    loaded = Trace.load_snapshot(trace.id, step_index=2, step_name="reviewer", traces_dir=tmp_path)
    assert loaded == [{"role": "user", "content": "hello"}]
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/test_trace.py::test_trace_load_snapshot -v`
Expected: FAIL — `load_snapshot` not defined

- [ ] **Step 7: Implement load_snapshot()**

```python
# trace.py — add to Trace class as @staticmethod

    @staticmethod
    def load_snapshot(trace_id: str, step_index: int, step_name: str, traces_dir: str | Path = "traces") -> list:
        """Load a conversation snapshot for a specific step."""
        path = Path(traces_dir) / f"{trace_id}_messages" / f"step_{step_index}_{step_name}.json"
        return json.loads(path.read_text())
```

- [ ] **Step 8: Run all tests**

Run: `pytest tests/test_trace.py -v`
Expected: all tests PASS

- [ ] **Step 9: Commit**

```bash
git add trace.py tests/test_trace.py
git commit -m "feat: add conversation snapshot save/load for replay"
```

---

### Task 4: Trace formatting (summary table and detail view)

**Files:**
- Modify: `trace.py`
- Modify: `tests/test_trace.py`

- [ ] **Step 1: Write failing test for summary_row()**

```python
# tests/test_trace.py (append)

def test_trace_summary_row():
    trace = Trace(workflow="pick-and-fix", command="Fix the auth bug")
    trace.started_at = 1000.0
    trace.log(step=None, event="pipeline_start", workflow="pick-and-fix", command="Fix the auth bug")
    trace.log(step="0:planner", event="step_start")
    trace.log(step="0:planner", event="step_end", output_preview="plan done")
    trace.log(step="1:implementer", event="step_start")
    trace.log(step="1:implementer", event="step_end", output_preview="impl done")
    trace.log(step=None, event="pipeline_end", status="completed", total_cost=0.0342, duration=45.0, total_input=1000, total_output=500)
    trace.status = "completed"

    row = trace.summary_row()
    assert row["id"] == trace.id
    assert row["workflow"] == "pick-and-fix"
    assert row["status"] == "completed"
    assert row["steps"] == 2
    assert row["cost"] == 0.0342
    assert row["duration"] == 45.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_trace.py::test_trace_summary_row -v`
Expected: FAIL — `summary_row` not defined

- [ ] **Step 3: Implement summary_row()**

```python
# trace.py — add to Trace class

    def summary_row(self) -> dict:
        """Return a dict summarizing this trace for table display."""
        step_count = sum(1 for e in self.events if e.event == "step_start")
        pipeline_end = next((e for e in self.events if e.event == "pipeline_end"), None)
        cost = pipeline_end.data.get("total_cost", 0.0) if pipeline_end else 0.0
        duration = pipeline_end.data.get("duration", 0.0) if pipeline_end else 0.0
        return {
            "id": self.id,
            "workflow": self.workflow,
            "status": self.status,
            "steps": step_count,
            "cost": cost,
            "duration": duration,
            "started_at": self.started_at,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_trace.py::test_trace_summary_row -v`
Expected: PASS

- [ ] **Step 5: Write failing test for format_detail()**

```python
# tests/test_trace.py (append)

def test_trace_format_detail():
    trace = Trace(workflow="example", command="Fix bug")
    trace.log(step=None, event="pipeline_start", workflow="example", command="Fix bug")
    trace.log(step="0:planner", event="step_start", model="qwen", tools=["read_file"])
    trace.log(step="0:planner", event="tool_call", tool="read_file", params={"path": "foo.py"})
    trace.log(step="0:planner", event="tool_result", tool="read_file", result_preview="contents...")
    trace.log(step="0:planner", event="step_end", output_preview="Here is the plan.", duration=3.4, cost=0.005)
    trace.log(step=None, event="pipeline_end", status="completed", total_cost=0.005, duration=3.4, total_input=500, total_output=200)
    trace.status = "completed"

    output = trace.format_detail()
    assert "example" in output
    assert "Fix bug" in output
    assert "planner" in output
    assert "read_file" in output
    assert "Here is the plan." in output
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/test_trace.py::test_trace_format_detail -v`
Expected: FAIL — `format_detail` not defined

- [ ] **Step 7: Implement format_detail()**

```python
# trace.py — add to Trace class

    def format_detail(self) -> str:
        """Format trace as human-readable step-by-step detail."""
        lines = [f"Trace {self.id} — {self.workflow} ({self.status})", f'Command: "{self.command}"', ""]
        current_step = None
        for e in self.events:
            if e.event == "step_start":
                current_step = e.step
                model = e.data.get("model", "?")
                lines.append(f"Step {current_step} (model: {model})")
            elif e.event == "tool_call":
                tool = e.data.get("tool", "?")
                params = e.data.get("params", {})
                lines.append(f"  -> tool: {tool}({params})")
            elif e.event == "tool_result":
                tool = e.data.get("tool", "?")
                preview = e.data.get("result_preview", "")
                error = e.data.get("error")
                if error:
                    lines.append(f"  <- {tool}: ERROR: {error}")
                else:
                    lines.append(f"  <- {tool}: {preview[:100]}")
            elif e.event == "step_end":
                preview = e.data.get("output_preview", "")
                duration = e.data.get("duration", 0)
                cost = e.data.get("cost", 0)
                lines.append(f"  -> output: \"{preview[:200]}\"")
                lines.append(f"  ({duration:.1f}s, ${cost:.4f})")
                lines.append("")
            elif e.event == "pipeline_end":
                total_cost = e.data.get("total_cost", 0)
                duration = e.data.get("duration", 0)
                total_in = e.data.get("total_input", 0)
                total_out = e.data.get("total_output", 0)
                lines.append(f"Total: {duration:.1f}s, ${total_cost:.4f}, {total_in:,} in / {total_out:,} out")
        return "\n".join(lines)
```

- [ ] **Step 8: Run all tests**

Run: `pytest tests/test_trace.py -v`
Expected: all tests PASS

- [ ] **Step 9: Commit**

```bash
git add trace.py tests/test_trace.py
git commit -m "feat: add trace summary and detail formatting"
```

---

### Task 5: Integrate trace into agent_loop

**Files:**
- Modify: `agent_openrouter.py:104-218` (the `agent_loop` function)
- Modify: `tests/test_trace.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_trace.py (append)
from unittest.mock import patch

def test_agent_loop_logs_trace_events():
    """agent_loop logs api_call, tool_call, and tool_result events to trace."""
    from trace import Trace
    from agent_openrouter import agent_loop

    trace = Trace(workflow="test", command="test")

    # Fake streaming: first call returns a tool call, second call returns text
    call_count = [0]
    def fake_call_api_streaming(messages, tools, model, cancel_event=None):
        call_count[0] += 1
        if call_count[0] == 1:
            # Return a tool call
            yield {
                "choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "read_file", "arguments": '{"path": "foo.py"}'}}]}, "finish_reason": None}],
            }
            yield {
                "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.001},
            }
        else:
            # Return text
            yield {
                "choices": [{"delta": {"content": "Done."}, "finish_reason": None}],
            }
            yield {
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 150, "completion_tokens": 10, "cost": 0.001},
            }

    def fake_read_file(params):
        return "file contents"

    from tools import read_file as rf
    messages = [{"role": "system", "content": "You are helpful."}]

    with patch("agent_openrouter.call_api_streaming", side_effect=fake_call_api_streaming):
        agent_loop("test prompt", messages, tools=[rf], trace=trace, step_label="0:planner")

    event_types = [e.event for e in trace.events]
    assert "api_call" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    # Should have 2 api_calls (one for tool call response, one for final text)
    assert event_types.count("api_call") == 2
    # All events should have the step label
    for e in trace.events:
        assert e.step == "0:planner"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_trace.py::test_agent_loop_logs_trace_events -v`
Expected: FAIL — `agent_loop() got an unexpected keyword argument 'trace'`

- [ ] **Step 3: Add trace parameter and logging to agent_loop**

In `agent_openrouter.py`, modify the `agent_loop` function signature at line 104:

Change:
```python
def agent_loop(
    user_message: str,
    messages: list,
    model: str = MODEL,
    cancel_event: threading.Event | None = None,
    mcp_clients: list | None = None,
    tools: list | None = None,
) -> dict:
```

To:
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
) -> dict:
```

Then add trace logging at three points inside the `while True` loop:

**After token counting (after line 171 `total_cost += usage.get("cost", 0.0)`):**
```python
            if trace is not None:
                trace.log(step=step_label, event="api_call",
                          input_tokens=usage.get("prompt_tokens", 0),
                          output_tokens=usage.get("completion_tokens", 0),
                          cost=usage.get("cost", 0.0))
```

**Before `execute_tool` call (before line 206 `result = execute_tool(...)`):**
```python
                    if trace is not None:
                        trace.log(step=step_label, event="tool_call", tool=name, params=params)
```

**After `execute_tool` call (after line 206 `result = execute_tool(...)`):**
```python
                    if trace is not None:
                        from trace import _preview
                        trace.log(step=step_label, event="tool_result", tool=name,
                                  result_preview=_preview(result),
                                  error=result if result.startswith("Error:") else None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_trace.py::test_agent_loop_logs_trace_events -v`
Expected: PASS

- [ ] **Step 5: Run all tests to check nothing broke**

Run: `pytest -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add agent_openrouter.py tests/test_trace.py
git commit -m "feat: integrate trace logging into agent_loop"
```

---

### Task 6: Integrate trace into run_pipeline

**Files:**
- Modify: `harness.py:116-207` (the `run_pipeline` function)
- Modify: `tests/test_harness.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_harness.py (append)

def test_run_pipeline_creates_trace(tmp_path):
    """run_pipeline creates a trace JSON file when traces_dir is provided."""
    from unittest.mock import patch
    from harness import run_pipeline

    def fake_load_agent(name, **kwargs):
        return _agent_config()

    def fake_agent_loop(user_message, messages, **kwargs):
        messages.append({"role": "assistant", "content": "output from agent"})
        return {"input_tokens": 100, "output_tokens": 50, "cost": 0.001}

    steps = [
        {"name": "planner", "id": None, "prompt": None, "inputs": None, "loop_on": None, "loop_to": None, "max_loops": None},
    ]

    with patch("harness.load_agent", side_effect=fake_load_agent), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Fix the bug", traces_dir=tmp_path)

    # Should have exactly one trace file
    trace_files = list(tmp_path.glob("*.json"))
    assert len(trace_files) == 1

    import json
    data = json.loads(trace_files[0].read_text())
    assert data["workflow"] == "pipeline"
    assert data["command"] == "Fix the bug"
    assert data["status"] == "completed"

    # Check events
    event_types = [e["event"] for e in data["events"]]
    assert "pipeline_start" in event_types
    assert "step_start" in event_types
    assert "step_end" in event_types
    assert "pipeline_end" in event_types


def test_run_pipeline_saves_snapshots(tmp_path):
    """run_pipeline saves conversation snapshots per step."""
    from unittest.mock import patch
    from harness import run_pipeline

    def fake_load_agent(name, **kwargs):
        return _agent_config()

    def fake_agent_loop(user_message, messages, **kwargs):
        messages.append({"role": "assistant", "content": "step output"})
        return {"input_tokens": 50, "output_tokens": 25, "cost": 0.0005}

    steps = [
        {"name": "planner", "id": None, "prompt": None, "inputs": None, "loop_on": None, "loop_to": None, "max_loops": None},
        {"name": "implementer", "id": None, "prompt": None, "inputs": None, "loop_on": None, "loop_to": None, "max_loops": None},
    ]

    with patch("harness.load_agent", side_effect=fake_load_agent), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Fix the bug", traces_dir=tmp_path)

    # Find the trace id from the JSON file
    trace_file = list(tmp_path.glob("*.json"))[0]
    trace_id = trace_file.stem

    snapshot_dir = tmp_path / f"{trace_id}_messages"
    assert snapshot_dir.is_dir()
    assert (snapshot_dir / "step_0_planner.json").exists()
    assert (snapshot_dir / "step_1_implementer.json").exists()


def test_run_pipeline_trace_on_failure(tmp_path):
    """Trace is saved with status 'failed' when an agent raises."""
    from unittest.mock import patch
    from harness import run_pipeline

    def fake_load_agent(name, **kwargs):
        return _agent_config()

    def fake_agent_loop(user_message, messages, **kwargs):
        raise RuntimeError("API exploded")

    steps = [
        {"name": "planner", "id": None, "prompt": None, "inputs": None, "loop_on": None, "loop_to": None, "max_loops": None},
    ]

    with patch("harness.load_agent", side_effect=fake_load_agent), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        with pytest.raises(RuntimeError):
            run_pipeline(steps, "Fix the bug", traces_dir=tmp_path)

    trace_files = list(tmp_path.glob("*.json"))
    assert len(trace_files) == 1
    import json
    data = json.loads(trace_files[0].read_text())
    assert data["status"] == "failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_harness.py::test_run_pipeline_creates_trace tests/test_harness.py::test_run_pipeline_saves_snapshots tests/test_harness.py::test_run_pipeline_trace_on_failure -v`
Expected: FAIL — `run_pipeline() got an unexpected keyword argument 'traces_dir'`

- [ ] **Step 3: Modify run_pipeline to create and populate trace**

In `harness.py`, modify `run_pipeline` signature at line 116:

Change:
```python
def run_pipeline(steps: list[StepConfig], command: str) -> None:
```

To:
```python
def run_pipeline(steps: list[StepConfig], command: str, traces_dir: str | Path = "traces", workflow_name: str = "pipeline") -> None:
```

Add import at top of file:
```python
from trace import Trace, _preview
```

Restructure `run_pipeline` body to wrap the main loop in try/finally:

```python
def run_pipeline(steps: list[StepConfig], command: str, traces_dir: str | Path = "traces", workflow_name: str = "pipeline") -> None:
    """Run command through each agent in sequence, chaining responses."""
    step_index_map: dict[str, int] = {s["name"]: i for i, s in enumerate(steps)}
    agent_cache: dict[str, AgentConfig] = {}
    loop_counts: dict[str, int] = {}
    step_outputs: dict[str, str] = {"__input__": command}
    last_output: str = command
    step_index = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    trace = Trace(workflow=workflow_name, command=command)
    trace.log(event="pipeline_start", workflow=workflow_name, command=command)
    pipeline_start_time = time.time()

    try:
        while step_index < len(steps):
            step = steps[step_index]
            step_name = step["name"]
            step_id = step.get("id")
            step_prompt = step.get("prompt")
            input_ids = step.get("inputs")
            step_label = f"{step_index}:{step_name}"

            if input_ids is not None:
                parts = [step_outputs[ref] for ref in input_ids if ref in step_outputs]
                current_input = "\n\n---\n\n".join(parts)
            else:
                current_input = last_output

            try:
                if step_name not in agent_cache:
                    agent_cache[step_name] = load_agent(step_name)
                agent = agent_cache[step_name]
                model = agent["model"] or DEFAULT_MODEL
                messages: list = [{"role": "system", "content": agent["prompt"]}]
                tools_str = ", ".join(agent["tool_names"]) or "none"
                skills_str = ", ".join(agent["skill_names"]) or "none"
                mcp_names = agent["mcp_names"]
                mcp_str = ", ".join(mcp_names) or "none"
                mcp_clients = build_mcp_clients(mcp_names) if mcp_names else []
                print(f"\n[agent: {step_name}]  tools: {tools_str}  |  skills: {skills_str}  |  mcp: {mcp_str}")
                effective_input = (step_prompt + "\n\n" + current_input) if step_prompt else current_input
                print(f"[system prompt] {agent['prompt']}")
                print(f"[user prompt] {effective_input}")

                trace.log(step=step_label, event="step_start", model=model,
                          tools=agent["tool_names"], prompt_preview=_preview(effective_input))
                step_start_time = time.time()

                try:
                    usage = agent_loop(effective_input, messages, model=model, tools=agent["tools"],
                                       mcp_clients=mcp_clients, trace=trace, step_label=step_label)
                finally:
                    for client in mcp_clients:
                        client.close()
                in_tok = usage.get("input_tokens", 0)
                out_tok = usage.get("output_tokens", 0)
                cost = usage.get("cost", 0.0)
                total_input_tokens += in_tok
                total_output_tokens += out_tok
                total_cost += cost
                print(f"[usage: {step_name}]  in={in_tok:,}  out={out_tok:,}  cost=${cost:.4f}")
                if usage.get("cancelled"):
                    trace.status = "cancelled"
                    print("\nPipeline cancelled.", file=sys.stderr)
                    sys.exit(0)
                step_output: str | None = None
                for msg in reversed(messages):
                    if msg["role"] == "assistant" and msg.get("content"):
                        step_output = msg["content"]
                        break
                if step_output is None:
                    print(f"Warning: agent '{step_name}' produced no text output; passing previous input forward.", file=sys.stderr)
                    trace.log(step=step_label, event="step_end", output_preview="(no output)",
                              duration=time.time() - step_start_time, cost=cost)
                    trace.save_snapshot(step_index, step_name, messages, traces_dir=traces_dir)
                    step_index += 1
                    continue
                last_output = step_output
                if step_id:
                    step_outputs[step_id] = step_output

                trace.log(step=step_label, event="step_end", output_preview=_preview(step_output),
                          duration=time.time() - step_start_time, cost=cost)
                trace.save_snapshot(step_index, step_name, messages, traces_dir=traces_dir)

                if "STOP" in step_output:
                    print("Nothing to do.", file=sys.stderr)
                    print(f"\n[total usage]  in={total_input_tokens:,}  out={total_output_tokens:,}  cost=${total_cost:.4f}")
                    trace.status = "completed"
                    return
                loop_on = step.get("loop_on")
                loop_to = step.get("loop_to")
                max_loops = step.get("max_loops")
                if loop_on and loop_to and loop_on in step_output:
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
                step_index += 1
            except Exception:
                print(f"\n[error: {step_name}] step failed", file=sys.stderr)
                print(f"\n[total usage]  in={total_input_tokens:,}  out={total_output_tokens:,}  cost=${total_cost:.4f}")
                raise

        trace.status = "completed"
        print(f"\n[total usage]  in={total_input_tokens:,}  out={total_output_tokens:,}  cost=${total_cost:.4f}")
    except Exception:
        if trace.status == "running":
            trace.status = "failed"
        raise
    finally:
        duration = time.time() - pipeline_start_time
        trace.log(event="pipeline_end", status=trace.status, total_input=total_input_tokens,
                  total_output=total_output_tokens, total_cost=total_cost, duration=duration)
        trace.save(traces_dir=traces_dir)
```

Also add `import time` at the top of `harness.py` if not already present.

- [ ] **Step 4: Run the new tests**

Run: `pytest tests/test_harness.py::test_run_pipeline_creates_trace tests/test_harness.py::test_run_pipeline_saves_snapshots tests/test_harness.py::test_run_pipeline_trace_on_failure -v`
Expected: PASS

- [ ] **Step 5: Run ALL tests to make sure nothing broke**

Run: `pytest -v`
Expected: all tests PASS. Existing tests still pass because `traces_dir` defaults to `"traces"` and `trace`/`step_label` default to `None` in `agent_loop`.

- [ ] **Step 6: Commit**

```bash
git add harness.py tests/test_harness.py
git commit -m "feat: integrate trace logging into run_pipeline"
```

---

### Task 7: CLI subcommands (trace list, trace show, replay)

**Files:**
- Modify: `harness.py:210-232` (the `main` function and argparse setup)
- Modify: `tests/test_harness.py`

- [ ] **Step 1: Write failing test for trace list**

```python
# tests/test_harness.py (append)

def test_trace_list_command(tmp_path, monkeypatch, capsys):
    """trace list subcommand prints a summary table of traces."""
    import json
    from harness import main

    # Create a fake trace file
    trace_data = {
        "id": "abc12345",
        "workflow": "example",
        "command": "Fix bug",
        "started_at": 1000.0,
        "status": "completed",
        "events": [
            {"timestamp": 1000.0, "step": "0:planner", "event": "step_start", "data": {}},
            {"timestamp": 1001.0, "step": None, "event": "pipeline_end",
             "data": {"total_cost": 0.0342, "duration": 45.0, "total_input": 1000, "total_output": 500, "status": "completed"}},
        ],
    }
    (tmp_path / "abc12345.json").write_text(json.dumps(trace_data))

    monkeypatch.setattr(sys, "argv", ["harness.py", "trace", "list", "--traces-dir", str(tmp_path)])
    main()

    captured = capsys.readouterr()
    assert "abc12345" in captured.out
    assert "example" in captured.out
    assert "completed" in captured.out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_harness.py::test_trace_list_command -v`
Expected: FAIL — argparse doesn't recognize `trace` subcommand

- [ ] **Step 3: Write failing test for trace show**

```python
# tests/test_harness.py (append)

def test_trace_show_command(tmp_path, monkeypatch, capsys):
    """trace show subcommand prints detail view of a trace."""
    import json
    from harness import main

    trace_data = {
        "id": "abc12345",
        "workflow": "example",
        "command": "Fix bug",
        "started_at": 1000.0,
        "status": "completed",
        "events": [
            {"timestamp": 1000.0, "step": None, "event": "pipeline_start", "data": {"workflow": "example", "command": "Fix bug"}},
            {"timestamp": 1000.1, "step": "0:planner", "event": "step_start", "data": {"model": "qwen", "tools": ["read_file"]}},
            {"timestamp": 1000.5, "step": "0:planner", "event": "step_end", "data": {"output_preview": "Here is the plan.", "duration": 3.4, "cost": 0.005}},
            {"timestamp": 1001.0, "step": None, "event": "pipeline_end",
             "data": {"total_cost": 0.005, "duration": 3.4, "total_input": 500, "total_output": 200, "status": "completed"}},
        ],
    }
    (tmp_path / "abc12345.json").write_text(json.dumps(trace_data))

    monkeypatch.setattr(sys, "argv", ["harness.py", "trace", "show", "abc12345", "--traces-dir", str(tmp_path)])
    main()

    captured = capsys.readouterr()
    assert "abc12345" in captured.out
    assert "planner" in captured.out
    assert "Here is the plan." in captured.out
```

- [ ] **Step 4: Write failing test for replay**

```python
# tests/test_harness.py (append)

def test_replay_command(tmp_path, monkeypatch):
    """replay subcommand loads snapshot and re-runs from given step."""
    import json
    from unittest.mock import patch as mock_patch
    from harness import main

    # Create trace file
    trace_data = {
        "id": "abc12345",
        "workflow": "example",
        "command": "Fix bug",
        "started_at": 1000.0,
        "status": "completed",
        "events": [],
    }
    (tmp_path / "abc12345.json").write_text(json.dumps(trace_data))

    # Create snapshot for step 0
    msg_dir = tmp_path / "abc12345_messages"
    msg_dir.mkdir()
    snapshot = [{"role": "system", "content": "You are a planner."}, {"role": "user", "content": "Fix bug"}, {"role": "assistant", "content": "Plan done."}]
    (msg_dir / "step_0_planner.json").write_text(json.dumps(snapshot))

    # Create workflow file
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "example.yaml").write_text("name: example\nsteps:\n  - name: planner\n  - name: implementer\n")

    captured_args = {}

    def fake_run_pipeline(steps, command, **kwargs):
        captured_args["steps"] = steps
        captured_args["command"] = command
        captured_args.update(kwargs)

    monkeypatch.setattr(sys, "argv", [
        "harness.py", "replay", "abc12345", "--from-step", "1",
        "--traces-dir", str(tmp_path), "--workflows-dir", str(wf_dir),
    ])

    with mock_patch("harness.run_pipeline", side_effect=fake_run_pipeline), \
         mock_patch("harness.load_workflow") as mock_load_wf:
        mock_load_wf.return_value = [
            {"name": "planner", "id": None, "prompt": None, "inputs": None, "loop_on": None, "loop_to": None, "max_loops": None},
            {"name": "implementer", "id": None, "prompt": None, "inputs": None, "loop_on": None, "loop_to": None, "max_loops": None},
        ]
        main()

    # Should run from step 1 onward (just implementer)
    assert len(captured_args["steps"]) == 1
    assert captured_args["steps"][0]["name"] == "implementer"
```

- [ ] **Step 5: Run all three tests to verify they fail**

Run: `pytest tests/test_harness.py::test_trace_list_command tests/test_harness.py::test_trace_show_command tests/test_harness.py::test_replay_command -v`
Expected: FAIL

- [ ] **Step 6: Implement CLI subcommands in main()**

In `harness.py`, replace the `main()` function:

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Run agent pipelines")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # workflow subcommand
    wf = subparsers.add_parser("workflow", help="Run a workflow with an ad-hoc prompt")
    wf.add_argument("name", help="workflow name")
    wf.add_argument("prompt", help="initial prompt to send to the first agent")

    # trace subcommand
    tr = subparsers.add_parser("trace", help="Inspect traces")
    tr_sub = tr.add_subparsers(dest="trace_action", required=True)

    tr_list = tr_sub.add_parser("list", help="List recent traces")
    tr_list.add_argument("--traces-dir", default="traces", help="traces directory")

    tr_show = tr_sub.add_parser("show", help="Show trace detail")
    tr_show.add_argument("trace_id", help="trace ID")
    tr_show.add_argument("--traces-dir", default="traces", help="traces directory")

    # replay subcommand
    rp = subparsers.add_parser("replay", help="Replay a pipeline from a specific step")
    rp.add_argument("trace_id", help="trace ID to replay from")
    rp.add_argument("--from-step", type=int, required=True, help="step index to resume from")
    rp.add_argument("--traces-dir", default="traces", help="traces directory")
    rp.add_argument("--workflows-dir", default=str(_HERE / "workflows"), help="workflows directory")

    args = parser.parse_args()

    try:
        if args.subcommand == "workflow":
            step_names = load_workflow(args.name)
            run_pipeline(step_names, args.prompt, workflow_name=args.name)
        elif args.subcommand == "trace":
            if args.trace_action == "list":
                _trace_list(args.traces_dir)
            elif args.trace_action == "show":
                _trace_show(args.trace_id, args.traces_dir)
        elif args.subcommand == "replay":
            _replay(args.trace_id, args.from_step, args.traces_dir, args.workflows_dir)
        else:
            parser.error(f"Unknown subcommand: {args.subcommand}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _trace_list(traces_dir: str) -> None:
    """List recent traces."""
    from trace import Trace
    traces_path = Path(traces_dir)
    if not traces_path.is_dir():
        print("No traces found.")
        return
    trace_files = sorted(traces_path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not trace_files:
        print("No traces found.")
        return
    print(f"{'ID':<10} {'Workflow':<20} {'Status':<12} {'Steps':>5} {'Cost':>10} {'Duration':>10} {'Started'}")
    for tf in trace_files:
        t = Trace.load(tf.stem, traces_dir=traces_dir)
        row = t.summary_row()
        import datetime
        started = datetime.datetime.fromtimestamp(row["started_at"]).strftime("%Y-%m-%d %H:%M")
        duration_s = f"{row['duration']:.0f}s"
        print(f"{row['id']:<10} {row['workflow']:<20} {row['status']:<12} {row['steps']:>5} ${row['cost']:>9.4f} {duration_s:>10} {started}")


def _trace_show(trace_id: str, traces_dir: str) -> None:
    """Show trace detail."""
    from trace import Trace
    t = Trace.load(trace_id, traces_dir=traces_dir)
    print(t.format_detail())


def _replay(trace_id: str, from_step: int, traces_dir: str, workflows_dir: str) -> None:
    """Replay a pipeline from a specific step."""
    from trace import Trace
    t = Trace.load(trace_id, traces_dir=traces_dir)
    all_steps = load_workflow(t.workflow, workflows_dir=Path(workflows_dir))
    if from_step >= len(all_steps):
        raise ValueError(f"--from-step {from_step} is out of range (workflow has {len(all_steps)} steps)")
    remaining_steps = all_steps[from_step:]
    run_pipeline(remaining_steps, t.command, traces_dir=traces_dir, workflow_name=t.workflow)
```

- [ ] **Step 7: Run the CLI tests**

Run: `pytest tests/test_harness.py::test_trace_list_command tests/test_harness.py::test_trace_show_command tests/test_harness.py::test_replay_command -v`
Expected: PASS

- [ ] **Step 8: Run ALL tests**

Run: `pytest -v`
Expected: all tests PASS

- [ ] **Step 9: Commit**

```bash
git add harness.py tests/test_harness.py
git commit -m "feat: add trace list, trace show, and replay CLI commands"
```

---

### Task 8: Gitignore and final verification

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add traces/ to .gitignore**

Append `traces/` to `.gitignore`.

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: all tests PASS

- [ ] **Step 3: Manual smoke test**

Run: `python harness.py trace list`
Expected: "No traces found." (no traces directory yet)

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: add traces/ to gitignore"
```
