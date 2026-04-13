#!/usr/bin/env python3
"""Agent pipeline executor — runs workflows through agent chains."""

import argparse
import sys
from pathlib import Path
from typing import NotRequired, TypedDict

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


class StepConfig(TypedDict):
    name: str
    prompt: str | None
    loop_on: NotRequired[str | None]
    loop_to: NotRequired[str | None]
    max_loops: NotRequired[int | None]


def load_workflow(name: str, workflows_dir: Path = _HERE / "workflows") -> list[StepConfig]:
    """Scan workflows_dir for a YAML whose name: field matches name."""
    for path in sorted(workflows_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        if data.get("name") == name:
            steps: list[StepConfig] = []
            seen_names: set[str] = set()
            for step in data.get("steps", []):
                step_name = step["name"]
                loop_on = step.get("loop_on") or None
                loop_to = step.get("loop_to") or None
                max_loops = step.get("max_loops")
                if (loop_on is None) != (loop_to is None):
                    print(f"Error: step '{step_name}' must have both loop_on and loop_to, or neither.", file=sys.stderr)
                    sys.exit(1)
                if loop_to is not None and loop_to not in seen_names:
                    print(f"Error: step '{step_name}' loop_to='{loop_to}' must refer to an earlier step.", file=sys.stderr)
                    sys.exit(1)
                if loop_on is not None and max_loops is None:
                    max_loops = 3
                steps.append({
                    "name": step_name,
                    "prompt": step.get("prompt") or None,
                    "loop_on": loop_on,
                    "loop_to": loop_to,
                    "max_loops": max_loops,
                })
                seen_names.add(step_name)
            return steps
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


def run_pipeline(steps: list[StepConfig], command: str) -> None:
    """Run command through each agent in sequence, chaining responses."""
    step_index_map: dict[str, int] = {s["name"]: i for i, s in enumerate(steps)}
    agent_cache: dict[str, AgentConfig] = {}
    loop_counts: dict[str, int] = {}
    current_input = command
    step_index = 0

    while step_index < len(steps):
        step = steps[step_index]
        step_name = step["name"]
        step_prompt = step.get("prompt")
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
        print(f"[prompt] {effective_input}")
        try:
            usage = agent_loop(effective_input, messages, model=model, tools=agent["tools"], mcp_clients=mcp_clients)
        finally:
            for client in mcp_clients:
                client.close()
        if usage.get("cancelled"):
            print("\nPipeline cancelled.", file=sys.stderr)
            sys.exit(0)
        updated = False
        for msg in reversed(messages):
            if msg["role"] == "assistant" and msg.get("content"):
                current_input = msg["content"]
                updated = True
                break
        if not updated:
            print(f"Warning: agent '{step_name}' produced no text output; passing previous input forward.", file=sys.stderr)
            step_index += 1
            continue
        if "STOP" in current_input:
            print("Nothing to do.", file=sys.stderr)
            return
        loop_on = step.get("loop_on")
        loop_to = step.get("loop_to")
        max_loops = step.get("max_loops")
        if loop_on and loop_to and loop_on in current_input:
            count = loop_counts.get(step_name, 0)
            if count < max_loops:
                loop_counts[step_name] = count + 1
                print(f"[loop] '{step_name}' triggered '{loop_on}' (loop {count + 1}/{max_loops}), jumping to '{loop_to}'", file=sys.stderr)
                step_index = step_index_map[loop_to]
                continue
            else:
                print(f"[loop] '{step_name}' hit max_loops={max_loops}; continuing to next step.", file=sys.stderr)
        step_index += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run agent pipelines")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    wf = subparsers.add_parser("workflow", help="Run a workflow with an ad-hoc prompt")
    wf.add_argument("name", help="workflow name")
    wf.add_argument("prompt", help="initial prompt to send to the first agent")

    args = parser.parse_args()

    if args.subcommand == "workflow":
        step_names = load_workflow(args.name)
        run_pipeline(step_names, args.prompt)
    else:
        parser.error(f"Unknown subcommand: {args.subcommand}")


if __name__ == "__main__":
    main()
