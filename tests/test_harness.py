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
        {"name": "agent1", "prompt": None, "loop_on": None, "loop_to": None, "max_loops": None},
        {"name": "agent2", "prompt": None, "loop_on": None, "loop_to": None, "max_loops": None},
    ]


def test_load_workflow_step_with_prompt(tmp_path):
    """Step dict includes prompt when present in YAML."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n  - name: agent1\n    prompt: 'Focus on tests.'\n"
    )
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps == [{"name": "agent1", "prompt": "Focus on tests.", "loop_on": None, "loop_to": None, "max_loops": None}]


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
    with pytest.raises(SystemExit):
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
    with pytest.raises(SystemExit):
        load_agent("missing", agents_dir=tmp_path)


def test_load_agent_unknown_tool_raises(tmp_path):
    """Raises SystemExit when agent YAML references an unknown tool name."""
    ag = tmp_path / "myagent.yaml"
    ag.write_text(
        "name: myagent\nprompt: Hi.\ntools:\n  - name: nonexistent_tool\n"
    )
    from harness import load_agent
    with pytest.raises(SystemExit):
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
        )


def test_run_pipeline_appends_step_prompt(monkeypatch):
    """Step prompt is prepended to current_input with double newline separator."""
    from unittest.mock import patch
    from harness import run_pipeline

    agent_config = {
        "prompt": "System prompt",
        "tools": [],
        "tool_names": [],
        "skill_names": [],
        "mcp_names": [],
        "model": None,
    }

    captured_inputs = []

    def fake_agent_loop(user_message, messages, **kwargs):
        captured_inputs.append(user_message)
        messages.append({"role": "assistant", "content": "output"})
        return {}

    with patch("harness.load_agent", return_value=agent_config), \
         patch("harness.agent_loop", side_effect=fake_agent_loop), \
         patch("harness.build_mcp_clients", return_value=[]):
        run_pipeline([{"name": "agent1", "prompt": "Extra guidance"}], "Initial command")

    assert captured_inputs[0] == "Extra guidance\n\nInitial command"


def test_run_pipeline_stops_on_stop_signal(monkeypatch, capsys):
    """Pipeline exits early when agent response contains STOP."""
    from unittest.mock import patch
    from harness import run_pipeline

    agent_config = {
        "prompt": "System prompt",
        "tools": [], "tool_names": [], "skill_names": [], "mcp_names": [], "model": None,
    }

    call_count = 0

    def fake_agent_loop(user_message, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        messages.append({"role": "assistant", "content": "Nothing needed here. STOP"})
        return {}

    with patch("harness.load_agent", return_value=agent_config), \
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

    agent_config = {
        "prompt": "System prompt",
        "tools": [],
        "tool_names": [],
        "skill_names": [],
        "mcp_names": [],
        "model": None,
    }

    captured_inputs = []

    def fake_agent_loop(user_message, messages, **kwargs):
        captured_inputs.append(user_message)
        messages.append({"role": "assistant", "content": "output"})
        return {}

    with patch("harness.load_agent", return_value=agent_config), \
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
    with pytest.raises(SystemExit):
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
    with pytest.raises(SystemExit):
        load_workflow("mywf", workflows_dir=tmp_path)


# --- Loop-back: run_pipeline tests ---

def _agent_config():
    return {
        "prompt": "System prompt",
        "tools": [],
        "tool_names": [],
        "skill_names": [],
        "mcp_names": [],
        "model": None,
    }


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
        # Determine which agent is running from the call log length
        # We need to know the step name - use a side channel via messages[0]["content"]
        # Actually we don't have direct access to step name here. Use a closure counter.
        # The order is: implementer, reviewer(UNAPPROVED), implementer, reviewer(clean)
        call_log.append(user_message)
        call_index = len(call_log) - 1
        # call 0: implementer, call 1: reviewer(UNAPPROVED), call 2: implementer, call 3: reviewer(clean)
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


