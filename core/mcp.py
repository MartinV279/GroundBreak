from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Callable, Optional
import json
import subprocess
import threading
import uuid

from core.config import load_config


@dataclass
class McpToolDescriptor:
    """Descriptor for a tool exposed via MCP or a similar mechanism."""

    name: str
    description: str
    fn: Callable[..., Any]


class McpIntegration:
    """
    Practical but minimal MCP integration over stdio.

    Protocol expected from the MCP server (JSON per line):
    - Request:  {"id": "<uuid>", "method": "list_tools"}
      Response: {"id": "<same>", "result": [{"name": "...", "description": "..."}]}

    - Request:  {"id": "<uuid>", "method": "call_tool",
                 "params": {"name": "<tool_name>", "arguments": {...}}}
      Response: {"id": "<same>", "result": "<string result>"}

    This subset is enough to:
    - Discover tools to surface via the existing ToolRegistry
    - Call those tools from the chat flow
    """

    def __init__(self) -> None:
        cfg = load_config()
        self._cfg = cfg
        self._tools: Dict[str, McpToolDescriptor] = {}
        self._proc: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()
        self._connected = False

        if cfg.mcp_enabled and cfg.mcp_command:
            self._start_process()
            if self._connected:
                self._discover_tools()
        # Always register a fallback echo tool so something is available.
        self._register_fallback_echo()

    # ----- Process & status -------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    def status(self) -> str:
        if not self._cfg.mcp_enabled:
            return "MCP disabled"
        if not self._cfg.mcp_command:
            return "MCP not configured"
        return "MCP connected" if self._connected else "MCP not connected"

    def _start_process(self) -> None:
        try:
            args = [self._cfg.mcp_command, *self._cfg.mcp_args]
            self._proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            self._connected = True
        except Exception:
            self._proc = None
            self._connected = False

    # ----- Tool registration & discovery -----------------------------------

    def _register_fallback_echo(self) -> None:
        if "mcp_echo" in self._tools:
            return

        def echo_tool(text: str) -> str:
            return f"[MCP echo] {text}"

        desc = McpToolDescriptor(
            name="mcp_echo",
            description="Echo text via the MCP integration scaffold.",
            fn=echo_tool,
        )
        self._tools[desc.name] = desc

    def _discover_tools(self) -> None:
        if not self._connected or not self._proc or not self._proc.stdin or not self._proc.stdout:
            return
        req_id = str(uuid.uuid4())
        req = {"id": req_id, "method": "list_tools"}
        try:
            with self._lock:
                self._proc.stdin.write(json.dumps(req) + "\n")
                self._proc.stdin.flush()
                line = self._proc.stdout.readline()
        except Exception:
            return

        if not line:
            return
        try:
            resp = json.loads(line)
        except Exception:
            return
        if resp.get("id") != req_id:
            return

        tools = resp.get("result") or []
        for t in tools:
            name = t.get("name")
            if not name:
                continue
            desc_text = t.get("description", "")
            self._tools[name] = McpToolDescriptor(
                name=name,
                description=desc_text,
                fn=self._make_tool_fn(name),
            )

    def _make_tool_fn(self, name: str) -> Callable[..., Any]:
        def _call_tool(**arguments: Any) -> Any:
            return self.call(name, **arguments)

        return _call_tool

    # ----- Public API -------------------------------------------------------

    def list_tools(self) -> List[McpToolDescriptor]:
        return list(self._tools.values())

    def get_tool(self, name: str) -> McpToolDescriptor | None:
        return self._tools.get(name)

    def call(self, name: str, **kwargs: Any) -> Any:
        tool = self.get_tool(name)
        if tool is None:
            raise ValueError(f"MCP tool '{name}' not found")
        # If this tool is backed by the MCP server, its fn will call back into
        # this method; to avoid recursion, call the server only when connected.
        if self._connected and self._proc and self._proc.stdin and self._proc.stdout and name in self._tools:
            req_id = str(uuid.uuid4())
            req = {
                "id": req_id,
                "method": "call_tool",
                "params": {"name": name, "arguments": kwargs},
            }
            with self._lock:
                self._proc.stdin.write(json.dumps(req) + "\n")
                self._proc.stdin.flush()
                line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError("No response from MCP server")
            resp = json.loads(line)
            if resp.get("id") != req_id:
                raise RuntimeError("Mismatched MCP response id")
            if "error" in resp:
                raise RuntimeError(f"MCP error: {resp['error']}")
            return resp.get("result")
        # Fallback: local implementation (e.g. mcp_echo).
        return tool.fn(**kwargs)

