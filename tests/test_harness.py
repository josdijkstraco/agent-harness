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
    assert steps == [{"name": "agent1", "prompt": None}, {"name": "agent2", "prompt": None}]


def test_load_workflow_step_with_prompt(tmp_path):
    """Step dict includes prompt when present in YAML."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text(
        "name: mywf\nsteps:\n  - name: agent1\n    prompt: 'Focus on tests.'\n"
    )
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps == [{"name": "agent1", "prompt": "Focus on tests."}]


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


def test_load_job_finds_by_name(tmp_path):
    """Resolves steps from the referenced workflow."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text("name: mywf\nsteps:\n  - name: agent1\n")
    job = tmp_path / "myjob.yaml"
    job.write_text("name: myjob\nworkflow: mywf\nprompt: Do something.")
    from harness import load_job
    job_cfg = load_job("myjob", jobs_dir=tmp_path, workflows_dir=tmp_path)
    assert job_cfg["steps"] == [{"name": "agent1", "prompt": None}]
    assert job_cfg["prompt"] == "Do something."


def test_load_job_not_found_raises(tmp_path):
    """Raises SystemExit when no job matches the name."""
    from harness import load_job
    with pytest.raises(SystemExit):
        load_job("missing", jobs_dir=tmp_path)


def test_load_job_unknown_workflow_raises(tmp_path):
    """Raises SystemExit when the referenced workflow does not exist."""
    job = tmp_path / "myjob.yaml"
    job.write_text("name: myjob\nworkflow: nonexistent\nprompt: Do something.\n")
    from harness import load_job
    with pytest.raises(SystemExit):
        load_job("myjob", jobs_dir=tmp_path, workflows_dir=tmp_path)


def test_load_job_missing_prompt_defaults_to_empty(tmp_path):
    """Returns empty string for prompt when the field is absent from YAML."""
    job = tmp_path / "myjob.yaml"
    job.write_text("name: myjob\n")
    from harness import load_job
    job_cfg = load_job("myjob", jobs_dir=tmp_path)
    assert job_cfg["prompt"] == ""


def test_load_job_missing_workflow_defaults_to_empty_steps(tmp_path):
    """Returns empty steps list when workflow field is absent."""
    job = tmp_path / "myjob.yaml"
    job.write_text("name: myjob\nprompt: Do something.\n")
    from harness import load_job
    job_cfg = load_job("myjob", jobs_dir=tmp_path)
    assert job_cfg["steps"] == []


def test_load_job_returns_prompt(tmp_path):
    """Job prompt is returned verbatim, including multi-line content."""
    job = tmp_path / "myjob.yaml"
    job.write_text(
        "name: myjob\nprompt: |\n  Line 1\n  Line 2\n  Line 3\n"
    )
    from harness import load_job
    job_cfg = load_job("myjob", jobs_dir=tmp_path)
    assert job_cfg["prompt"] == "Line 1\nLine 2\nLine 3\n"


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
    """Step prompt is appended to current_input with double newline separator."""
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

    assert captured_inputs[0] == "Initial command\n\nExtra guidance"


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


def test_main_job_subcommand(monkeypatch):
    """main() with job subcommand loads job and runs pipeline."""
    from unittest.mock import patch
    from harness import main

    # Mock load_job and run_pipeline
    with patch("harness.load_job") as mock_load_job, \
         patch("harness.run_pipeline") as mock_run_pipeline:
        mock_load_job.return_value = {
            "steps": [{"name": "agent3", "prompt": None}, {"name": "agent4", "prompt": None}],
            "prompt": "Fix the login bug.\n",
        }

        # Set sys.argv for argparse
        test_argv = ["harness.py", "job", "fix-login"]
        monkeypatch.setattr(sys, "argv", test_argv)

        main()

        # Assert load_job was called with correct name
        mock_load_job.assert_called_once_with("fix-login")
        # Assert run_pipeline was called with steps and prompt from job config
        mock_run_pipeline.assert_called_once_with(
            [{"name": "agent3", "prompt": None}, {"name": "agent4", "prompt": None}],
            "Fix the login bug.\n",
        )
