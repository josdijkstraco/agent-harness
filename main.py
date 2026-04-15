#!/usr/bin/env python3
"""Multi-agent coding harness — entry point."""

import argparse
import os
import sys
import threading

from dotenv import load_dotenv
from prompt_toolkit import prompt as pt_prompt

load_dotenv()

API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    print("Error: OPENROUTER_API_KEY environment variable is required.")
    sys.exit(1)

from agent_openrouter import AVAILABLE_MODELS, MODEL, agent_loop
from skills_loader import SKILLS, build_system_prompt
from mcp_client import build_all_mcp_clients
from repl_utils import COMMAND_COMPLETER, IS_TTY, status_text, watch_for_escape


def select_model(current: str) -> str:
    print("Available models:")
    for i, m in enumerate(AVAILABLE_MODELS, 1):
        marker = " *" if m == current else ""
        print(f"  {i}. {m}{marker}")
    try:
        choice = input("Pick a number (or press Enter to keep current): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return current
    if not choice:
        return current
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(AVAILABLE_MODELS):
            selected = AVAILABLE_MODELS[idx]
            print(f"Model set to: {selected}")
            return selected
        print("Invalid selection, keeping current model.")
    except ValueError:
        print("Invalid input, keeping current model.")
    return current


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-agent coding harness")
    parser.parse_args()

    if sys.stdout.isatty():
        print()

    mcp_clients = build_all_mcp_clients()
    for client in mcp_clients:
        names = [t["function"]["name"] for t in client.tools]
        print(f"  [{client.name}] tools: {', '.join(names)}")

    skill_names = list(SKILLS.keys())
    system_prompt = build_system_prompt(skill_names)

    print("Multi-Agent Harness (type 'exit' to quit, '/model' to switch, '/clear' to reset history)")
    if skill_names:
        print("Loaded skills: " + ", ".join(skill_names))
    messages: list = [{"role": "system", "content": system_prompt}]
    current_model = MODEL
    session_in = 0
    session_out = 0
    session_cost = 0.0

    turns = 0

    while True:
        try:
            if IS_TTY:
                import warnings
                def _toolbar() -> str:
                    return status_text(current_model, session_in, session_out, turns, session_cost)
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message=".*CPR.*")
                    user_input = pt_prompt("> ", completer=COMMAND_COMPLETER, bottom_toolbar=_toolbar, refresh_interval=0.5)
            else:
                user_input = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.strip().lower() in ("exit", "quit"):
            break
        if user_input.strip() == "/model":
            current_model = select_model(current_model)
            continue
        if user_input.strip() == "/clear":
            messages.clear()
            messages.append({"role": "system", "content": system_prompt})
            session_in = 0
            session_out = 0
            turns = 0
            print("History cleared.")
            continue
        if not user_input.strip():
            continue

        cancel_event = threading.Event()
        done_event = threading.Event()
        result: dict = {}

        def _run() -> None:
            result["usage"] = agent_loop(user_input, messages, model=current_model, cancel_event=cancel_event, mcp_clients=None)

        agent_thread = threading.Thread(target=_run, daemon=True)
        watcher_thread = threading.Thread(target=watch_for_escape, args=(cancel_event, done_event), daemon=True)
        watcher_thread.start()
        agent_thread.start()
        try:
            agent_thread.join()
        except KeyboardInterrupt:
            cancel_event.set()
            agent_thread.join()
        finally:
            done_event.set()

        usage = result.get("usage", {"input_tokens": 0, "output_tokens": 0, "cancelled": True})
        if usage.get("cancelled"):
            print("\nRequest interrupted.")
        else:
            session_in += usage["input_tokens"]
            session_out += usage["output_tokens"]
            session_cost += usage.get("cost", 0.0)
            turns = (len(messages) - 1) // 2

    for client in mcp_clients:
        client.close()


if __name__ == "__main__":
    main()
