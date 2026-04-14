"""Shared REPL utilities for main.py and harness.py agent mode."""

import select
import sys
import termios
import threading
import tty

from prompt_toolkit.completion import WordCompleter

IS_TTY = sys.stdout.isatty()
COMMAND_COMPLETER = WordCompleter(["/model", "/clear"], sentence=True)


def watch_for_escape(cancel_event: threading.Event, done_event: threading.Event) -> None:
    """Set cancel_event if Escape is pressed; runs in a background thread."""
    if not IS_TTY:
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while not done_event.is_set():
            if select.select([sys.stdin], [], [], 0.05)[0]:
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    cancel_event.set()
                    return
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def status_text(model: str, session_in: int, session_out: int, turns: int, session_cost: float = 0.0) -> str:
    return (
        f" Tokens: {session_in:,} in / {session_out:,} out"
        f"  |  Cost: ${session_cost:.4f}"
        f"  |  History: {turns} turn{'s' if turns != 1 else ''}"
        f"  |  Model: {model}"
    )
