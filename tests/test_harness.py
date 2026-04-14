# tests/test_harness.py
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_load_workflow_finds_by_name(tmp_path):
    """Scans directory and returns step dicts for a matching workflow name."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text("name: mywf\nsteps:\n  - name: agent1\n  - name: agent2\n")
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps == [
        {"name": "agent1", "id": None, "inputs": None, "prompt": None, "outputs": None, "when": None, "loop_on": None, "loop_to": None, "max_loops": None, "response_schema": None, "stop_on": None},
        {"name": "agent2", "id": None, "inputs": None, "prompt": None, "outputs": None, "when": None, "loop_on": None, "loop_to": None, "max_loops": None, "response_schema": None, "stop_on": None},
    ]


def test_load_workflow_step_with_prompt(tmp_path):
    """Step dict includes prompt when present in YAML."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n  - name: agent1\n    prompt: 'Focus on tests.'\n"
    )
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps == [{"name": "agent1", "id": None, "inputs": None, "prompt": "Focus on tests.", "outputs": None, "when": None, "loop_on": None, "loop_to": None, "max_loops": None, "response_schema": None, "stop_on": None}]


def test_load_workflow_step_without_prompt_is_none(tmp_path):
    """Step dict has prompt=None when prompt field is absent."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text("name: mywf\nsteps:\n  - name: agent1\n")
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps[0]["prompt"] is None


def test_load_workflow_not_found_raises(tmp_path):
    """Raises SystemExit when no workflow matches the name."""
    from harness import load_workflow
    with pytest.raises(ValueError):
        load_workflow("missing", workflows_dir=tmp_path)


def test_load_agent_finds_by_name(tmp_path):
    """Scans directory and returns AgentConfig for a matching agent name."""
    ag = tmp_path / "myagent.yaml"
    ag.write_text(
        "name: myagent\nprompt: Do stuff.\ntools:\n  - name: read_file\n"
    )
    from harness import load_agent
    config = load_agent("myagent", agents_dir=tmp_path)
    assert config["prompt"] == "Do stuff."
    assert config["tool_names"] == ["read_file"]
    assert config["model"] is None  # not set in yaml


def test_load_agent_with_model(tmp_path):
    """Model field is read from agent YAML when present."""
    ag = tmp_path / "myagent.yaml"
    ag.write_text(
        "name: myagent\nmodel: google/gemini-2.5-flash-preview\nprompt: Hi.\ntools:\n  - name: bash\n"
    )
    from harness import load_agent
    config = load_agent("myagent", agents_dir=tmp_path)
    assert config["model"] == "google/gemini-2.5-flash-preview"


def test_load_agent_not_found_raises(tmp_path):
    """Raises SystemExit when no agent matches the name."""
    from harness import load_agent
    with pytest.raises(ValueError):
        load_agent("missing", agents_dir=tmp_path)


def test_load_agent_unknown_tool_raises(tmp_path):
    """Raises SystemExit when agent YAML references an unknown tool name."""
    ag = tmp_path / "myagent.yaml"
    ag.write_text(
        "name: myagent\nprompt: Hi.\ntools:\n  - name: nonexistent_tool\n"
    )
    from harness import load_agent
    with pytest.raises(ValueError):
        load_agent("myagent", agents_dir=tmp_path)


def test_main_workflow_subcommand(monkeypatch):
    """main() with workflow subcommand loads workflow and runs pipeline."""
    from unittest.mock import patch
    from harness import main

    # Mock load_workflow and run_pipeline
    with patch("harness.load_workflow") as mock_load_wf, \
         patch("harness.run_pipeline") as mock_run_pipeline:
        mock_load_wf.return_value = [{"name": "agent1", "prompt": None}, {"name": "agent2", "prompt": None}]

        # Set sys.argv for argparse
        test_argv = ["harness.py", "workflow", "example", "Fix the bug"]
        monkeypatch.setattr(sys, "argv", test_argv)

        main()

        # Assert load_workflow was called with correct name
        mock_load_wf.assert_called_once_with("example")
        # Assert run_pipeline was called with steps and prompt
        mock_run_pipeline.assert_called_once_with(
            [{"name": "agent1", "prompt": None}, {"name": "agent2", "prompt": None}],
            "Fix the bug",
            workflow_name="example",
        )


def _agent_config():
    return {
        "prompt": "System prompt",
        "tools": [],
        "tool_names": [],
        "skill_names": [],
        "mcp_names": [],
        "model": None,
    }


def test_run_pipeline_appends_step_prompt(monkeypatch):
    """Step prompt is prepended to current_input with double newline separator."""
    from unittest.mock import patch
    from harness import run_pipeline

    captured_inputs = []

    def fake_agent_loop(user_message, messages, **kwargs):
        captured_inputs.append(user_message)
        messages.append({"role": "assistant", "content": "output"})
        return {}

    with patch("harness.load_agent", return_value=_agent_config()), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline([{"name": "agent1", "prompt": "Extra guidance"}], "Initial command")

    assert captured_inputs[0] == "Extra guidance\n\nInitial command"


def test_run_pipeline_stops_on_stop_signal(monkeypatch, capsys):
    """Pipeline exits early when agent response contains STOP."""
    from unittest.mock import patch
    from harness import run_pipeline

    call_count = 0

    def fake_agent_loop(user_message, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        messages.append({"role": "assistant", "content": "Nothing needed here. STOP"})
        return {}

    with patch("harness.load_agent", return_value=_agent_config()), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(
            [{"name": "agent1", "prompt": None}, {"name": "agent2", "prompt": None}],
            "Do the thing"
        )

    assert call_count == 1
    captured = capsys.readouterr()
    assert "Nothing to do." in captured.err


def test_run_pipeline_no_step_prompt_passes_input_unchanged(monkeypatch):
    """Input is passed unchanged to agent_loop when step has no prompt."""
    from unittest.mock import patch
    from harness import run_pipeline

    captured_inputs = []

    def fake_agent_loop(user_message, messages, **kwargs):
        captured_inputs.append(user_message)
        messages.append({"role": "assistant", "content": "output"})
        return {}

    with patch("harness.load_agent", return_value=_agent_config()), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline([{"name": "agent1", "prompt": None}], "Initial command")

    assert captured_inputs[0] == "Initial command"


# --- Loop-back: load_workflow tests ---

def test_load_workflow_step_with_loop_fields(tmp_path):
    """Loop fields are parsed from YAML and returned in step dict."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: implementer\n"
        "  - name: reviewer\n"
        "    loop_on: UNAPPROVED\n"
        "    loop_to: implementer\n"
        "    max_loops: 2\n"
    )
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps[1]["loop_on"] == "UNAPPROVED"
    assert steps[1]["loop_to"] == "implementer"
    assert steps[1]["max_loops"] == 2


def test_load_workflow_step_loop_default_max_loops(tmp_path):
    """max_loops defaults to 3 when loop_on/loop_to are set but max_loops is absent."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: implementer\n"
        "  - name: reviewer\n"
        "    loop_on: UNAPPROVED\n"
        "    loop_to: implementer\n"
    )
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps[1]["max_loops"] == 3


def test_load_workflow_step_no_loop_fields_are_none(tmp_path):
    """Steps without loop fields have all loop fields as None."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text("name: mywf\nsteps:\n  - name: agent1\n")
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps[0]["loop_on"] is None
    assert steps[0]["loop_to"] is None
    assert steps[0]["max_loops"] is None


def test_load_workflow_loop_on_without_loop_to_raises(tmp_path):
    """loop_on without loop_to triggers SystemExit."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: agent1\n"
        "  - name: agent2\n"
        "    loop_on: UNAPPROVED\n"
    )
    from harness import load_workflow
    with pytest.raises(ValueError):
        load_workflow("mywf", workflows_dir=tmp_path)


def test_load_workflow_loop_to_forward_reference_raises(tmp_path):
    """loop_to referencing a later step triggers SystemExit."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: agent1\n"
        "    loop_on: RETRY\n"
        "    loop_to: agent2\n"
        "  - name: agent2\n"
    )
    from harness import load_workflow
    with pytest.raises(ValueError):
        load_workflow("mywf", workflows_dir=tmp_path)


# --- Loop-back: run_pipeline tests ---


def test_run_pipeline_loops_back_on_keyword():
    """Reviewer outputs UNAPPROVED once then clean; pipeline runs implementer twice."""
    from unittest.mock import patch
    from harness import run_pipeline

    call_log = []
    outputs = {
        "implementer": ["impl output v1", "impl output v2"],
        "reviewer": ["This needs work. UNAPPROVED", "Looks good."],
    }
    counters = {"implementer": 0, "reviewer": 0}

    def fake_load_agent(name, **kwargs):
        return _agent_config()

    def fake_agent_loop(user_message, messages, **kwargs):
        call_log.append(user_message)
        call_index = len(call_log) - 1
        sequence = ["implementer", "reviewer", "implementer", "reviewer"]
        agent = sequence[call_index]
        output = outputs[agent][counters[agent]]
        counters[agent] += 1
        messages.append({"role": "assistant", "content": output})
        return {}

    steps = [
        {"name": "implementer", "prompt": None},
        {"name": "reviewer", "prompt": None, "loop_on": "UNAPPROVED", "loop_to": "implementer", "max_loops": 3},
    ]

    with patch("harness.load_agent", side_effect=fake_load_agent), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Fix the bug")

    assert len(call_log) == 4
    # Second implementer call receives the reviewer's UNAPPROVED feedback
    assert "UNAPPROVED" in call_log[2]


def test_run_pipeline_loop_respects_max_loops(capsys):
    """Reviewer always outputs UNAPPROVED; pipeline stops looping after max_loops and continues."""
    from unittest.mock import patch
    from harness import run_pipeline

    call_count = [0]

    def fake_load_agent(name, **kwargs):
        return _agent_config()

    def fake_agent_loop(user_message, messages, **kwargs):
        call_count[0] += 1
        messages.append({"role": "assistant", "content": "UNAPPROVED always"})
        return {}

    steps = [
        {"name": "implementer", "prompt": None},
        {"name": "reviewer", "prompt": None, "loop_on": "UNAPPROVED", "loop_to": "implementer", "max_loops": 2},
    ]

    with patch("harness.load_agent", side_effect=fake_load_agent), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Fix the bug")

    # implementer(1) → reviewer(1,loop1) → implementer(2) → reviewer(2,loop2) → implementer(3) → reviewer(3,max exceeded) = 6
    assert call_count[0] == 6
    captured = capsys.readouterr()
    assert "max_loops" in captured.err


def test_run_pipeline_no_loop_when_keyword_absent():
    """Pipeline runs linearly when loop_on keyword is not in output."""
    from unittest.mock import patch
    from harness import run_pipeline

    call_count = [0]

    def fake_load_agent(name, **kwargs):
        return _agent_config()

    def fake_agent_loop(user_message, messages, **kwargs):
        call_count[0] += 1
        messages.append({"role": "assistant", "content": "Looks great. APPROVED"})
        return {}

    steps = [
        {"name": "implementer", "prompt": None},
        {"name": "reviewer", "prompt": None, "loop_on": "UNAPPROVED", "loop_to": "implementer", "max_loops": 3},
    ]

    with patch("harness.load_agent", side_effect=fake_load_agent), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Fix the bug")

    assert call_count[0] == 2


def test_run_pipeline_step_prompt_not_duplicated_on_loop():
    """Step prompt is prepended once per execution, not accumulated across loop iterations."""
    from unittest.mock import patch
    from harness import run_pipeline

    captured_inputs = []
    call_count = [0]

    def fake_load_agent(name, **kwargs):
        return _agent_config()

    def fake_agent_loop(user_message, messages, **kwargs):
        captured_inputs.append(user_message)
        call_count[0] += 1
        # implementer runs twice (calls 0 and 2), reviewer runs twice (calls 1 and 3)
        if call_count[0] == 1:
            messages.append({"role": "assistant", "content": "impl done"})
        elif call_count[0] == 2:
            messages.append({"role": "assistant", "content": "UNAPPROVED please fix"})
        elif call_count[0] == 3:
            messages.append({"role": "assistant", "content": "impl done v2"})
        else:
            messages.append({"role": "assistant", "content": "Looks good."})
        return {}

    steps = [
        {"name": "implementer", "prompt": "Do the work."},
        {"name": "reviewer", "prompt": "Review it.", "loop_on": "UNAPPROVED", "loop_to": "implementer", "max_loops": 3},
    ]

    with patch("harness.load_agent", side_effect=fake_load_agent), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Fix the bug")

    # implementer called twice: prompt should be "Do the work.\n\n<input>" each time
    assert captured_inputs[0].startswith("Do the work.\n\n")
    assert captured_inputs[2].startswith("Do the work.\n\n")
    # reviewer called twice: prompt should be "Review it.\n\n<input>" each time
    assert captured_inputs[1].startswith("Review it.\n\n")
    assert captured_inputs[3].startswith("Review it.\n\n")
    # The implementer's prompt must NOT appear in the reviewer's input
    assert "Do the work." not in captured_inputs[1]
    assert "Do the work." not in captured_inputs[3]


def test_run_pipeline_creates_trace(tmp_path):
    """run_pipeline creates a trace JSON file when traces_dir is provided."""
    import json
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

    trace_files = list(tmp_path.glob("*.json"))
    assert len(trace_files) == 1

    data = json.loads(trace_files[0].read_text())
    assert data["workflow"] == "pipeline"
    assert data["command"] == "Fix the bug"
    assert data["status"] == "completed"

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

    trace_file = list(tmp_path.glob("*.json"))[0]
    trace_id = trace_file.stem

    snapshot_dir = tmp_path / f"{trace_id}_messages"
    assert snapshot_dir.is_dir()
    assert (snapshot_dir / "step_0_planner.json").exists()
    assert (snapshot_dir / "step_1_implementer.json").exists()


def test_run_pipeline_trace_on_failure(tmp_path):
    """Trace is saved with status 'failed' when an agent raises."""
    import json
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
    data = json.loads(trace_files[0].read_text())
    assert data["status"] == "failed"


def test_trace_list_command(tmp_path, monkeypatch, capsys):
    """trace list subcommand prints a summary table of traces."""
    import json
    from harness import main

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


# --- Artifacts system tests ---


def test_load_workflow_step_with_outputs(tmp_path):
    """outputs field is parsed from YAML and returned in step dict."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: planner\n"
        "    id: plan\n"
        "    outputs:\n"
        "      plan: json\n"
        "      summary: text\n"
    )
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps[0]["outputs"] == {"plan": "json", "summary": "text"}


def test_load_workflow_step_without_outputs_is_none(tmp_path):
    """Steps without outputs have outputs=None."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text("name: mywf\nsteps:\n  - name: agent1\n")
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps[0]["outputs"] is None


def test_parse_artifacts_extracts_fenced_blocks():
    """parse_artifacts extracts content from fenced code blocks tagged with artifact names."""
    from harness import parse_artifacts
    raw = 'Some text\n```plan\n{"steps": [1, 2]}\n```\nMore text\n```summary\nDone.\n```'
    result = parse_artifacts(raw, {"plan": "json", "summary": "text"})
    assert result["plan"] == '{"steps": [1, 2]}'
    assert result["summary"] == "Done."


def test_parse_artifacts_fallback_to_raw():
    """parse_artifacts falls back to full raw output when no fenced block found."""
    from harness import parse_artifacts
    raw = "Just plain text output with no fenced blocks."
    result = parse_artifacts(raw, {"plan": "json"})
    assert result["plan"] == raw


def test_run_pipeline_artifacts_injected_with_labels():
    """Downstream step receives labeled inputs when using inputs field."""
    from unittest.mock import patch
    from harness import run_pipeline

    captured_inputs = []

    def fake_agent_loop(user_message, messages, **kwargs):
        captured_inputs.append(user_message)
        messages.append({"role": "assistant", "content": "output"})
        return {}

    steps = [
        {"name": "planner", "id": "plan", "prompt": None, "inputs": None,
         "outputs": None, "when": None,
         "loop_on": None, "loop_to": None, "max_loops": None},
        {"name": "implementer", "prompt": None, "inputs": ["plan"],
         "outputs": None, "when": None,
         "loop_on": None, "loop_to": None, "max_loops": None},
    ]

    with patch("harness.load_agent", return_value=_agent_config()), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Do the thing")

    # Second step should get labeled input
    assert captured_inputs[1] == "## Input: plan\noutput"


def test_run_pipeline_artifacts_stored_from_fenced_blocks():
    """Artifacts declared in outputs are parsed and stored in step_outputs."""
    from unittest.mock import patch
    from harness import run_pipeline

    captured_inputs = []

    def fake_agent_loop(user_message, messages, **kwargs):
        captured_inputs.append(user_message)
        if len(captured_inputs) == 1:
            messages.append({"role": "assistant", "content": 'Here is the plan:\n```plan\n{"steps": ["a", "b"]}\n```\nDone.'})
        else:
            messages.append({"role": "assistant", "content": "implemented"})
        return {}

    steps = [
        {"name": "planner", "id": "planner_step", "prompt": None, "inputs": None,
         "outputs": {"plan": "json"}, "when": None,
         "loop_on": None, "loop_to": None, "max_loops": None},
        {"name": "implementer", "prompt": None, "inputs": ["plan"],
         "outputs": None, "when": None,
         "loop_on": None, "loop_to": None, "max_loops": None},
    ]

    with patch("harness.load_agent", return_value=_agent_config()), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Do the thing")

    # The implementer should receive the extracted artifact, not the raw output
    assert '## Input: plan\n{"steps": ["a", "b"]}' == captured_inputs[1]


# --- Conditional branching (when) tests ---


def test_load_workflow_step_with_when(tmp_path):
    """when field is parsed from YAML and returned in step dict."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: reviewer\n"
        "    id: review\n"
        "  - name: implementer\n"
        "    when: 'REVISION_NEEDED in review'\n"
    )
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps[1]["when"] == "REVISION_NEEDED in review"


def test_run_pipeline_when_true_runs_step():
    """Step executes when its when condition matches."""
    from unittest.mock import patch
    from harness import run_pipeline

    call_count = [0]

    def fake_agent_loop(user_message, messages, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            messages.append({"role": "assistant", "content": "REVISION_NEEDED: fix tests"})
        else:
            messages.append({"role": "assistant", "content": "fixed"})
        return {}

    steps = [
        {"name": "reviewer", "id": "review", "prompt": None, "inputs": None,
         "outputs": None, "when": None,
         "loop_on": None, "loop_to": None, "max_loops": None},
        {"name": "implementer", "prompt": None, "inputs": None,
         "outputs": None, "when": "REVISION_NEEDED in review",
         "loop_on": None, "loop_to": None, "max_loops": None},
    ]

    with patch("harness.load_agent", return_value=_agent_config()), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Check it")

    assert call_count[0] == 2  # both steps ran


def test_run_pipeline_when_false_skips_step():
    """Step is skipped when its when condition does not match."""
    from unittest.mock import patch
    from harness import run_pipeline

    call_count = [0]

    def fake_agent_loop(user_message, messages, **kwargs):
        call_count[0] += 1
        messages.append({"role": "assistant", "content": "APPROVED: looks great"})
        return {}

    steps = [
        {"name": "reviewer", "id": "review", "prompt": None, "inputs": None,
         "outputs": None, "when": None,
         "loop_on": None, "loop_to": None, "max_loops": None},
        {"name": "implementer", "prompt": None, "inputs": None,
         "outputs": None, "when": "REVISION_NEEDED in review",
         "loop_on": None, "loop_to": None, "max_loops": None},
    ]

    with patch("harness.load_agent", return_value=_agent_config()), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline(steps, "Check it")

    assert call_count[0] == 1  # only reviewer ran, implementer skipped


def test_load_workflow_when_references_unknown_id_raises(tmp_path):
    """when referencing an unknown step id triggers ValueError."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: agent1\n"
        "  - name: agent2\n"
        "    when: 'FOO in nonexistent'\n"
    )
    from harness import load_workflow
    with pytest.raises(ValueError):
        load_workflow("mywf", workflows_dir=tmp_path)


def test_load_workflow_when_and_loop_on_raises(tmp_path):
    """Step cannot have both loop_on and when."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: implementer\n"
        "    id: impl\n"
        "  - name: reviewer\n"
        "    when: 'FOO in impl'\n"
        "    loop_on: UNAPPROVED\n"
        "    loop_to: implementer\n"
    )
    from harness import load_workflow
    with pytest.raises(ValueError):
        load_workflow("mywf", workflows_dir=tmp_path)


def test_load_workflow_outputs_conflict_with_existing_id_raises(tmp_path):
    """Output artifact name that conflicts with an existing step id raises ValueError."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: planner\n"
        "    id: plan\n"
        "  - name: implementer\n"
        "    id: impl\n"
        "    outputs:\n"
        "      plan: json\n"  # conflicts with planner's id
    )
    from harness import load_workflow
    with pytest.raises(ValueError):
        load_workflow("mywf", workflows_dir=tmp_path)


def test_load_workflow_inputs_can_reference_artifact_names(tmp_path):
    """inputs field can reference artifact names from outputs, not just step ids."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n"
        "  - name: planner\n"
        "    id: plan_step\n"
        "    outputs:\n"
        "      plan: json\n"
        "  - name: implementer\n"
        "    inputs: [plan]\n"
    )
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps[1]["inputs"] == ["plan"]


def test_replay_command(tmp_path, monkeypatch):
    """replay subcommand loads trace and re-runs from given step."""
    import json
    from unittest.mock import patch as mock_patch
    from harness import main

    trace_data = {
        "id": "abc12345",
        "workflow": "example",
        "command": "Fix bug",
        "started_at": 1000.0,
        "status": "completed",
        "events": [],
    }
    (tmp_path / "abc12345.json").write_text(json.dumps(trace_data))

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

    with mock_patch("harness.run_pipeline", side_effect=fake_run_pipeline):
        main()

    assert len(captured_args["steps"]) == 1
    assert captured_args["steps"][0]["name"] == "implementer"


# --- Structured outputs: build_submit_result_tool tests ---


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


# --- Structured outputs: eval_condition tests ---


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


# --- Structured outputs: load_workflow validation tests ---


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


# --- Structured outputs: agent_loop interception tests ---


def test_agent_loop_intercepts_submit_result():
    """agent_loop returns structured result when submit_result tool is called."""
    from unittest.mock import patch
    from agent_openrouter import agent_loop
    from harness import build_submit_result_tool

    schema = {
        "decision": {"type": "string", "enum": ["APPROVED", "REJECTED"]},
        "feedback": {"type": "string"},
    }
    submit_tool = build_submit_result_tool(schema)

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


def test_agent_loop_without_submit_result_schema_works_unchanged():
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


