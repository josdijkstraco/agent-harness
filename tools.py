"""Tool definitions and handlers for the coding agent."""

import glob
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Tool:
    schema: dict
    handler: Callable[[dict], str]

    @property
    def name(self) -> str:
        return self.schema["name"]


def make_schema(name: str, description: str, **params: str) -> dict:
    """Build a tool schema from keyword arguments (param_name='description')."""
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {k: {"type": "string", "description": v} for k, v in params.items()},
            "required": list(params.keys()),
        },
    }


def handle_read_file(params: dict) -> str:
    path = Path(params["path"])
    if not path.exists():
        return f"Error: File not found: {path}"
    return path.read_text()


def handle_write_file(params: dict) -> str:
    path = Path(params["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(params["content"])
    return f"Successfully wrote {len(params['content'])} bytes to {path}"


def handle_bash(params: dict) -> str:
    try:
        result = subprocess.run(
            params["command"],
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += result.stderr
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."


def handle_find_files(params: dict) -> str:
    matches = glob.glob(params["pattern"], recursive=True)
    if not matches:
        return "No files found."
    return "\n".join(sorted(matches))


read_file = Tool(
    schema=make_schema("read_file", "Read the contents of a file at the given path.", path="Path to the file to read."),
    handler=handle_read_file,
)

write_file = Tool(
    schema=make_schema("write_file", "Write content to a file, creating parent directories if needed.", path="Path to the file to write.", content="Content to write to the file."),
    handler=handle_write_file,
)

bash = Tool(
    schema=make_schema("bash", "Run a shell command and return its output.", command="Shell command to execute."),
    handler=handle_bash,
)

find_files = Tool(
    schema=make_schema("find_files", "Find files matching a glob pattern (supports ** for recursive).", pattern="Glob pattern to match files."),
    handler=handle_find_files,
)


def handle_ask_user(params: dict) -> str:
    question = params.get("question", "")
    if question:
        print(f"\n{question}")
    return input("> ").strip()


ask_user = Tool(
    schema=make_schema("ask_user", "Ask the user a question and wait for their response.", question="The question to ask the user."),
    handler=handle_ask_user,
)

ALL_TOOLS = [read_file, write_file, bash, find_files, ask_user]
