#!/usr/bin/env python3
"""Workflow pipeline executor — runs a command through a chain of agents."""

import argparse
import sys
from pathlib import Path
from typing import TypedDict

import yaml

from agent_openrouter import MODEL as DEFAULT_MODEL, agent_loop
from mcp_client import build_mcp_clients
from skills_loader import append_skills
from tools import ALL_TOOLS, Tool

_TOOL_MAP = {t.name: t for t in ALL_TOOLS}
_HERE = Path(__file__).parent


class AgentConfig(TypedDict):
    prompt: str
    tools: list[Tool]
    tool_names: list[str]
    skill_names: list[str]
    mcp_names: list[str]
    model: str | None


def load_workflow(name: str, workflows_dir: Path = _HERE / "workflows") -> list[str]:
    """Scan workflows_dir for a YAML whose name: field matches name."""
    for path in sorted(workflows_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        if data.get("name") == name:
            return [step["name"] for step in data.get("steps", [])]
    print(f"Error: no workflow named '{name}' found in {workflows_dir}/", file=sys.stderr)
    sys.exit(1)


def load_agent(name: str, agents_dir: Path = _HERE / "agents") -> AgentConfig:
    """Scan agents_dir for a YAML whose name: field matches name.

    Returns dict with keys: prompt, tools (list[Tool]), tool_names (list[str]), model (str|None).
    Exits on unknown tool names.
    """
    for path in sorted(agents_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        if data.get("name") == name:
            tool_names = [t["name"] for t in data.get("tools", [])]
            tools = []
            for tool_name in tool_names:
                if tool_name not in _TOOL_MAP:
                    print(f"Error: agent '{name}' references unknown tool '{tool_name}'", file=sys.stderr)
                    sys.exit(1)
                tools.append(_TOOL_MAP[tool_name])
            raw_skills = data.get("skills", [])
            skill_names = [s["name"] if isinstance(s, dict) else s for s in raw_skills]
            prompt = append_skills(data.get("prompt", ""), skill_names)
            raw_mcp = data.get("mcp", [])
            mcp_names = [m["name"] if isinstance(m, dict) else m for m in raw_mcp]
            return {
                "prompt": prompt,
                "tools": tools,
                "model": data.get("model", None),
                "tool_names": tool_names,
                "skill_names": skill_names,
                "mcp_names": mcp_names,
            }
    print(f"Error: no agent named '{name}' found in {agents_dir}/", file=sys.stderr)
    sys.exit(1)


def run_pipeline(step_names: list[str], command: str) -> None:
    """Run command through each agent in sequence, chaining responses."""
    current_input = command
    for step_name in step_names:
        agent = load_agent(step_name)
        model = agent["model"] or DEFAULT_MODEL
        messages: list = [{"role": "system", "content": agent["prompt"]}]
        tools_str = ", ".join(agent["tool_names"]) or "none"
        skills_str = ", ".join(agent["skill_names"]) or "none"
        mcp_names = agent["mcp_names"]
        mcp_str = ", ".join(mcp_names) or "none"
        mcp_clients = build_mcp_clients(mcp_names) if mcp_names else []
        print(f"\n[agent: {step_name}]  tools: {tools_str}  |  skills: {skills_str}  |  mcp: {mcp_str}")
        try:
            usage = agent_loop(current_input, messages, model=model, tools=agent["tools"], mcp_clients=mcp_clients)
        finally:
            for client in mcp_clients:
                client.close()
        if usage.get("cancelled"):
            print("\nPipeline cancelled.", file=sys.stderr)
            sys.exit(0)
        # Extract final assistant text from messages
        updated = False
        for msg in reversed(messages):
            if msg["role"] == "assistant" and msg.get("content"):
                current_input = msg["content"]
                updated = True
                break
        if not updated:
            print(f"Warning: agent '{step_name}' produced no text output; passing previous input forward.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a command through a workflow pipeline")
    parser.add_argument("workflow", help="Name of the workflow to run")
    parser.add_argument("command", help="Initial command to send to the first agent")
    args = parser.parse_args()

    step_names = load_workflow(args.workflow)
    run_pipeline(step_names, args.command)


if __name__ == "__main__":
    main()
