"""Configurable agent — call_api and agent_loop."""

import os
import time

import httpx

from tools import Tool

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")


def execute_tool(name: str, params: dict, tools: list[Tool]) -> str:
    for tool in tools:
        if tool.name == name:
            try:
                return tool.handler(params)
            except Exception as e:
                return f"[AGENT_ERROR] {e}"
    return f"[AGENT_ERROR] Unknown tool '{name}'"


def call_api(messages: list, system: str, schemas: list, model: str = DEFAULT_MODEL) -> dict:
    max_retries = 5
    last_response = None
    for attempt in range(max_retries):
        last_response = httpx.post(
            API_URL,
            headers={
                "x-api-key": API_KEY or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": MAX_TOKENS,
                "system": system,
                "tools": schemas,
                "messages": messages,
            },
            timeout=300.0,
        )
        if last_response.status_code in (429, 529):
            delay = 2 ** attempt
            print(f"  [API overloaded, retrying in {delay}s...]")
            time.sleep(delay)
            continue
        last_response.raise_for_status()
        return last_response.json()
    if last_response is not None:
        last_response.raise_for_status()
    raise RuntimeError("call_api: no attempts made")  # unreachable


def agent_loop(user_message: str, messages: list, system: str, tools: list[Tool], label: str | None = None, max_turns: int = 20, model: str = DEFAULT_MODEL) -> None:
    messages.append({"role": "user", "content": user_message})
    schemas = [t.schema for t in tools]

    for _turn in range(max_turns):
        if DEBUG:
            print(f"messages: {messages}")

        if label:
            print(f"\n── {label} ──")
        response = call_api(messages, system, schemas, model=model)
        messages.append({"role": "assistant", "content": response["content"]})

        for block in response["content"]:
            if block["type"] == "text":
                print(block["text"])

        usage = response.get("usage", {})
        print(f"  [tokens: {usage.get('input_tokens', '?')} in / {usage.get('output_tokens', '?')} out]")

        if response["stop_reason"] == "end_turn":
            break

        tool_results = []
        for block in response["content"]:
            if block["type"] == "tool_use":
                print(f"  [Tool: {block['name']}], params: {block['input']}")
                result = execute_tool(block["name"], block["input"], tools)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result,
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    else:
        raise RuntimeError(f"{label or 'agent'}: exceeded {max_turns} turns without end_turn")
