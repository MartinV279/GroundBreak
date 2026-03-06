from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Dict, List

from ollama import web_search, web_fetch

from core.mcp import McpIntegration
from tools.base import (
    ToolFn,
    ToolSpec,
    ToolProvider,
    enforce_safe_shell_command,
    ShellSafetyError,
)


class ToolRegistry:
    """Registry for tools exposed to the model and UI."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        self._mcp = McpIntegration()
        self._register_builtin_tools()
        self._register_mcp_tools()
        self._load_plugin_tools()

    def _register_builtin_tools(self) -> None:
        self.register(
            ToolSpec(
                name="web_search",
                fn=web_search,
                display_name="Web Search",
                description="Search the web via Ollama's web_search tool.",
            )
        )
        self.register(
            ToolSpec(
                name="web_fetch",
                fn=web_fetch,
                display_name="Web Fetch",
                description="Fetch and summarize a web page via Ollama's web_fetch tool.",
            )
        )

    def _register_mcp_tools(self) -> None:
        for desc in self._mcp.list_tools():
            self.register(
                ToolSpec(
                    name=desc.name,
                    fn=desc.fn,
                    display_name=desc.name,
                    description=desc.description,
                )
            )

    def _load_plugin_tools(self) -> None:
        """Automatically discover additional tools from the tools/ folder."""
        base_dir = Path(__file__).resolve().parent
        for path in base_dir.glob("*.py"):
            if path.stem in {"__init__", "registry", "base"}:
                continue
            module_name = f"tools.{path.stem}"
            try:
                mod = import_module(module_name)
            except Exception:
                continue

            provider: ToolProvider | None = None
            if hasattr(mod, "get_tools"):
                provider = mod  # type: ignore[assignment]
            if provider is None:
                continue
            try:
                for tool in provider.get_tools():
                    self.register(tool)
            except Exception:
                continue

    def register(self, tool: ToolSpec) -> None:
        # Wrap shell tools with safety checks.
        if tool.kind == "shell":
            original_fn = tool.fn

            def safe_fn(*args: Any, **kwargs: Any) -> Any:
                cmd = kwargs.get("command") or (args[0] if args else "")
                enforce_safe_shell_command(str(cmd))
                return original_fn(*args, **kwargs)

            tool.fn = safe_fn

        self._tools[tool.name] = tool

    def get_tool_by_name(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def get_ollama_tools_for_chat(self) -> List[ToolFn]:
        """Return tool callables suitable for passing to ollama.chat."""
        return [spec.fn for spec in self._tools.values()]

    def list_tools(self) -> List[ToolSpec]:
        return list(self._tools.values())

