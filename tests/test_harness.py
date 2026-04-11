# tests/test_harness.py
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_load_workflow_finds_by_name(tmp_path):
    """Scans directory and returns steps for a matching workflow name."""
    wf = tmp_path / "mywf.yaml"
    wf.write_text("name: mywf\nsteps:\n  - name: agent1\n  - name: agent2\n")
    from harness import load_workflow
    steps = load_workflow("mywf", workflows_dir=tmp_path)
    assert steps == ["agent1", "agent2"]


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
