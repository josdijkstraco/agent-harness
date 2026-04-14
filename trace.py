"""Structured trace logging for workflow pipeline runs."""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

PREVIEW_MAX = 500


def _preview(text: str) -> str:
    """Truncate text to PREVIEW_MAX characters."""
    if len(text) <= PREVIEW_MAX:
        return text
    return text[:PREVIEW_MAX] + "..."


@dataclass(frozen=True)
class TraceEvent:
    timestamp: float
    step: str | None
    event: str
    data: dict

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "step": self.step,
            "event": self.event,
            "data": self.data,
        }


class Trace:
    def __init__(self, workflow: str, command: str) -> None:
        self.id = uuid4().hex[:8]
        self.workflow = workflow
        self.command = command
        self.started_at = time.time()
        self.events: list[TraceEvent] = []
        self.status = "running"

    def log(self, step: str | None = None, event: str = "", **data: object) -> None:
        self.events.append(TraceEvent(
            timestamp=time.time(),
            step=step,
            event=event,
            data=data,
        ))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow": self.workflow,
            "command": self.command,
            "started_at": self.started_at,
            "status": self.status,
            "events": [e.to_dict() for e in self.events],
        }

    def save(self, traces_dir: str | Path = "traces") -> Path:
        """Save trace to a JSON file. Returns the path to the saved file."""
        traces_dir = Path(traces_dir)
        traces_dir.mkdir(parents=True, exist_ok=True)
        path = traces_dir / f"{self.id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path

    @classmethod
    def load(cls, trace_id: str, traces_dir: str | Path = "traces") -> "Trace":
        """Load a trace from its JSON file."""
        path = Path(traces_dir) / f"{trace_id}.json"
        data = json.loads(path.read_text())
        trace = cls.__new__(cls)
        trace.id = data["id"]
        trace.workflow = data["workflow"]
        trace.command = data["command"]
        trace.started_at = data["started_at"]
        trace.status = data["status"]
        trace.events = [
            TraceEvent(
                timestamp=e["timestamp"],
                step=e["step"],
                event=e["event"],
                data=e["data"],
            )
            for e in data["events"]
        ]
        return trace
