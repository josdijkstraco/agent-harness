"""Implementer agent — executes a coding plan by reading and writing files."""

from tools import bash, find_files, read_file, write_file

SYSTEM_PROMPT = (
    "You are an expert software implementer. You receive a specific coding task "
    "with context. Implement it cleanly, write tests if asked, and report what "
    "files you changed and why. Do not over-engineer — implement exactly what was asked."
)

TOOLS = [read_file, write_file, bash, find_files]
