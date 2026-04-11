#!/usr/bin/env python3
"""Minimal coding agent — interactive REPL powered by Claude via OpenRouter."""

import json
import os
import sys
import threading
import time
import httpx

from dotenv import load_dotenv
from tools import ALL_TOOLS

load_dotenv()

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "qwen/qwen3.6-plus"
AVAILABLE_MODELS = [
    "qwen/qwen3.6-plus",
    "z-ai/glm-4.5-air:free",
    "qwen/qwen3-235b-a22b:free",
    "google/gemini-2.5-flash-preview",
    "deepseek/deepseek-chat-v3-0324:free",
]

MAX_TOKENS = 4096


class RequestCancelled(Exception):
    pass

API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    print("Error: OPENROUTER_API_KEY environment variable is required.")
    sys.exit(1)


# Convert Anthropic-format schemas to OpenAI-compatible format
def _to_openai_tool(tool) -> dict:
    s = tool.schema
    return {
        "type": "function",
        "function": {
            "name": s["name"],
            "description": s["description"],
            "parameters": s["input_schema"],
        },
    }

def execute_tool(name: str, params: dict, tool_handlers: dict, mcp_clients: list | None = None) -> str:
    handler = tool_handlers.get(name)
    if handler:
        try:
            return handler(params)
        except Exception as e:
            return f"Error: {e}"
    for client in (mcp_clients or []):
        if client.has_tool(name):
            try:
                return client.call_tool(name, params)
            except Exception as e:
                return f"Error: {e}"
    return f"Error: Unknown tool '{name}'"

def call_api_streaming(messages: list, tools: list, model: str = MODEL, cancel_event: threading.Event | None = None):
    """Yield parsed SSE data dicts from a streaming API call, with retry on overload."""
    max_retries = 5
    for attempt in range(max_retries):
        with httpx.stream(
            "POST",
            API_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": MAX_TOKENS,
                "tools": tools,
                "messages": messages,
                "stream": True,
            },
            timeout=300.0,
        ) as response:
            if response.status_code in (429, 529):
                delay = 2 ** attempt
                print(f"  [API overloaded, retrying in {delay}s...]")
                time.sleep(delay)
                continue
            response.raise_for_status()
            for line in response.iter_lines():
                if cancel_event and cancel_event.is_set():
                    raise RequestCancelled()
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload == "[DONE]":
                        return
                    yield json.loads(payload)
            return
    return


def agent_loop(
    user_message: str,
    messages: list,
    model: str = MODEL,
    cancel_event: threading.Event | None = None,
    mcp_clients: list | None = None,
    tools: list | None = None,
) -> dict:
    initial_len = len(messages)
    messages.append({"role": "user", "content": user_message})

    active_tool_list = tools if tools is not None else ALL_TOOLS
    tool_handlers = {t.name: t.handler for t in active_tool_list}
    active_tools = [_to_openai_tool(t) for t in active_tool_list]
    for client in (mcp_clients or []):
        active_tools.extend(client.tools)

    total_input = 0
    total_output = 0

    try:
        while True:
            content_parts: list[str] = []
            tool_calls_acc: dict[int, dict] = {}
            finish_reason = None
            usage: dict = {}

            for chunk in call_api_streaming(messages, active_tools, model, cancel_event):
                choice = chunk["choices"][0]
                finish_reason = choice.get("finish_reason") or finish_reason
                delta = choice.get("delta", {})

                # Accumulate and stream text content
                if delta.get("content"):
                    print(delta["content"], end="", flush=True)
                    content_parts.append(delta["content"])

                # Accumulate tool call deltas
                for tc in delta.get("tool_calls", []):
                    idx = tc["index"]
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    acc = tool_calls_acc[idx]
                    if tc.get("id"):
                        acc["id"] = tc["id"]
                    fn = tc.get("function", {})
                    if fn.get("name"):
                        acc["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        acc["function"]["arguments"] += fn["arguments"]

                if chunk.get("usage"):
                    usage = chunk["usage"]

            if content_parts:
                print()  # newline after streamed content

            total_input += usage.get("prompt_tokens", 0)
            total_output += usage.get("completion_tokens", 0)

            content = "".join(content_parts) or None
            tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)] or None
            message: dict = {"role": "assistant"}
            if content is not None:
                message["content"] = content
            if tool_calls is not None:
                message["tool_calls"] = tool_calls
            messages.append(message)

            if finish_reason == "stop":
                break

            if finish_reason == "tool_calls" and tool_calls:
                tool_results = []
                for tool_call in tool_calls:
                    name = tool_call["function"]["name"]
                    params = json.loads(tool_call["function"]["arguments"])
                    print(f"  [Tool: {name}], params: {params}")
                    result = execute_tool(name, params, tool_handlers, mcp_clients)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result,
                    })
                messages.extend(tool_results)

    except RequestCancelled:
        del messages[initial_len:]
        return {"input_tokens": total_input, "output_tokens": total_output, "cancelled": True}

    return {"input_tokens": total_input, "output_tokens": total_output}
