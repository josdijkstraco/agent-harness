"""Tool definitions and handlers for the coding agent."""

import glob
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT_DIR = Path("/Users/jos/projects/agent-harness")


def _validate_path(path: str) -> str | None:
    """Validate that a resolved path is within ROOT_DIR. Returns error message or None."""
    resolved = (ROOT_DIR / path).resolve()
    try:
        resolved.relative_to(ROOT_DIR.resolve())
        return None
    except ValueError:
        return f"Error: Access denied. Path '{path}' resolves outside the root directory {ROOT_DIR}."


def _validate_paths_in_command(command: str) -> str | None:
    """Check if a shell command tries to access paths outside ROOT_DIR.
    
    This provides basic protection against common escape patterns. Not bulletproof
    but catches the most obvious cases. Returns error message or None.
    """
    # Check for cd commands that go above root
    cd_pattern = r'\bcd\s+([^\s;&|]+)'
    for match in re.finditer(cd_pattern, command):
        target = match.group(1)
        if target.startswith('/') and not target.startswith(str(ROOT_DIR)):
            return f"Error: Access denied. Cannot cd to directory outside {ROOT_DIR}."
        resolved = (ROOT_DIR / target).resolve()
        try:
            resolved.relative_to(ROOT_DIR.resolve())
        except ValueError:
            return f"Error: Access denied. Cannot cd to '{target}' as it resolves outside {ROOT_DIR}."
    
    # Check for absolute paths that might access files outside root
    abs_path_pattern = r'(?<!\w)(/[a-zA-Z0-9_./-]+)'
    for match in re.finditer(abs_path_pattern, command):
        abs_path = match.group(1)
        # Allow paths within root
        if abs_path.startswith(str(ROOT_DIR)):
            continue
        # Allow common system commands and special dirs
        system_allowed = ['/dev/null', '/usr/bin/', '/bin/', '/usr/local/']
        if any(abs_path.startswith(p) for p in system_allowed):
            continue
        # Block access to absolute paths outside root
        try:
            Path(abs_path).resolve().relative_to(ROOT_DIR.resolve())
        except ValueError:
            return f"Error: Access denied. Cannot access '{abs_path}' outside {ROOT_DIR}."
    
    return None


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
    path = params["path"]
    
    error = _validate_path(path)
    if error:
        return error
    
    resolved = (ROOT_DIR / path).resolve()
    
    if not resolved.exists():
        return f"Error: File not found: {resolved}"
    if not resolved.is_file():
        return f"Error: Not a file: {resolved}"
    
    return resolved.read_text()


def handle_write_file(params: dict) -> str:
    path = params["path"]
    
    error = _validate_path(path)
    if error:
        return error
    
    resolved = (ROOT_DIR / path).resolve()
    
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(params["content"])
    return f"Successfully wrote {len(params['content'])} bytes to {resolved}"


def handle_bash(params: dict) -> str:
    command = params["command"]
    
    error = _validate_paths_in_command(command)
    if error:
        return error
    
    # Ensure command runs from within ROOT_DIR
    original_cwd = os.getcwd()
    try:
        os.chdir(ROOT_DIR)
        result = subprocess.run(
            command,
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
    finally:
        os.chdir(original_cwd)


def handle_find_files(params: dict) -> str:
    pattern = params["pattern"]
    
    # Resolve glob relative to ROOT_DIR
    full_pattern = str(ROOT_DIR / pattern)
    matches = glob.glob(full_pattern, recursive=True)
    
    # Filter to only include paths within ROOT_DIR
    matches = [m for m in matches if Path(m).resolve().is_relative_to(ROOT_DIR.resolve())]
    
    if not matches:
        return "No files found."
    
    # Return paths relative to ROOT_DIR for cleaner output
    relative_paths = [str(Path(m).relative_to(ROOT_DIR)) for m in sorted(matches)]
    return "\n".join(relative_paths)


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
