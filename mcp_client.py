"""MCP (Model Context Protocol) client — JSON-RPC 2.0 over subprocess stdin/stdout."""

import json
import subprocess
from pathlib import Path


class MCPClient:
    def __init__(self, name: str, command: str, args: list[str]) -> None:
        self.name = name
        self._command = command
        self._args = args
        self._proc: subprocess.Popen | None = None
        self._req_id = 0
        self._tool_schemas: list[dict] = []  # OpenAI-compatible schemas
        self.enabled: bool = True

    # ── transport ──────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _send(self, obj: dict) -> None:
        assert self._proc and self._proc.stdin
        line = json.dumps(obj) + "\n"
        self._proc.stdin.write(line)
        self._proc.stdin.flush()

    def _recv(self) -> dict:
        assert self._proc and self._proc.stdout
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError(f"MCP server '{self.name}' closed stdout unexpectedly")
            line = line.strip()
            if not line:
                continue
            return json.loads(line)

    def _call(self, method: str, params: dict | None = None) -> dict:
        req_id = self._next_id()
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        while True:
            msg = self._recv()
            # Skip notifications (no id field)
            if "id" not in msg:
                continue
            if msg.get("id") != req_id:
                continue
            if "error" in msg:
                raise RuntimeError(f"MCP error from '{self.name}': {msg['error']}")
            return msg.get("result", {})

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._proc = subprocess.Popen(
            [self._command, *self._args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        # Initialize handshake
        self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "coding-harness", "version": "0.1.0"},
        })
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

        # Fetch and cache tool list
        result = self._call("tools/list")
        self._tool_schemas = [_to_openai_schema(t) for t in result.get("tools", [])]

    def close(self) -> None:
        if self._proc:
            try:
                self._proc.stdin.close()  # type: ignore[union-attr]
            except Exception:
                pass
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    # ── tools ──────────────────────────────────────────────────────────────────

    @property
    def tools(self) -> list[dict]:
        """OpenAI-compatible tool schemas exposed by this server."""
        return self._tool_schemas

    def has_tool(self, tool_name: str) -> bool:
        return any(t["function"]["name"] == tool_name for t in self._tool_schemas)

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        result = self._call("tools/call", {"name": tool_name, "arguments": arguments})
        parts = []
        for item in result.get("content", []):
            if item.get("type") == "text":
                parts.append(item["text"])
            elif item.get("type") == "resource":
                parts.append(str(item.get("resource", item)))
            else:
                parts.append(str(item))
        return "\n".join(parts) if parts else "(no output)"


# ── schema conversion ──────────────────────────────────────────────────────────

def _to_openai_schema(mcp_tool: dict) -> dict:
    """Convert MCP tool definition to OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": mcp_tool["name"],
            "description": mcp_tool.get("description", ""),
            "parameters": mcp_tool.get("inputSchema", {"type": "object", "properties": {}}),
        },
    }


# ── module helpers ─────────────────────────────────────────────────────────────

def load_mcp_config(path: str = ".mcp.json") -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def build_mcp_clients(names: list[str], config_path: str = ".mcp.json") -> list[MCPClient]:
    """Instantiate and start MCP clients for the given server names."""
    config = load_mcp_config(config_path)
    clients = []
    for name in names:
        if name not in config:
            raise ValueError(f"MCP server '{name}' not found in {config_path}")
        entry = config[name]
        client = MCPClient(name, entry["command"], entry.get("args", []))
        client.start()
        clients.append(client)
    return clients


def build_all_mcp_clients(config_path: str = ".mcp.json") -> list[MCPClient]:
    """Instantiate and start MCP clients for all servers defined in the config."""
    config = load_mcp_config(config_path)
    return build_mcp_clients(list(config.keys()), config_path)
