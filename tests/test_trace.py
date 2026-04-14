import json
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
