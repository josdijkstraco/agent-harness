"""Planner agent — explores the codebase and produces a step-by-step implementation plan."""

from tools import find_files, read_file

SYSTEM_PROMPT = (
    "You are a software planner. You receive a task and explore the codebase to produce "
    "a concrete, step-by-step implementation plan: which files to change, what to add or "
    "modify, and in what order. Return only the plan — no code, no explanations beyond "
    "what the implementer needs to execute it."
)

TOOLS = [read_file, find_files]
