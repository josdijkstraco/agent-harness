"""Agent registry and routing graph — the single place to define agents and their connections."""

from dataclasses import dataclass, field

from agent import agent_loop
from agents import coordinator, implementer, planner, reviewer
from tools import Tool

OPUS = "claude-opus-4-20250514"
SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5"


@dataclass
class AgentConfig:
    system_prompt: str
    tools: list[Tool]
    model: str
    delegates_to: list[str] = field(default_factory=list)


REGISTRY: dict[str, AgentConfig] = {
    "coordinator": AgentConfig(coordinator.SYSTEM_PROMPT, coordinator.BASE_TOOLS, SONNET, ["planner", "implementer", "reviewer"]),
    "planner":     AgentConfig(planner.SYSTEM_PROMPT,     planner.TOOLS,          SONNET),
    "implementer": AgentConfig(implementer.SYSTEM_PROMPT, implementer.TOOLS,      SONNET),
    "reviewer":    AgentConfig(reviewer.SYSTEM_PROMPT,    reviewer.TOOLS,         SONNET),
}


def make_handoff(target_name: str) -> Tool:
    """Build a handoff Tool that delegates to target_name with its own routing-aware tool set."""
    def handler(params: dict) -> str:
        config = REGISTRY[target_name]
        tools = build_tools(target_name)  # lazy — called at invocation time
        context = params.get("context", "")
        user_message = f"{context}\n\n{params['task']}" if context else params["task"]
        messages: list = []
        agent_loop(user_message, messages, config.system_prompt, tools, label=target_name, model=config.model)
        for block in reversed(messages[-1]["content"]):
            if isinstance(block, dict) and block.get("type") == "text":
                return block["text"]
        return "(no output)"

    return Tool(
        schema={
            "name": f"delegate_to_{target_name}",
            "description": f"Delegate a task to the {target_name} agent.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Instruction for the agent — what to do.",
                    },
                    "context": {
                        "type": "string",
                        "description": "Output from the previous agent to pass as input.",
                    },
                },
                "required": ["task", "context"],
            },
        },
        handler=handler,
    )


def build_tools(agent_name: str) -> list[Tool]:
    """Return base tools + handoff tools for all agents this agent is allowed to call."""
    config = REGISTRY[agent_name]
    handoffs = [make_handoff(t) for t in config.delegates_to]
    return config.tools + handoffs
