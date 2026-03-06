from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Protocol, runtime_checkable


ToolFn = Callable[..., Any]


@runtime_checkable
class ToolProvider(Protocol):
    """Protocol for modules that provide tools to the registry."""

    def get_tools(self) -> list["ToolSpec"]:
        ...


@dataclass
class ToolSpec:
    """
    Canonical schema for a tool exposed to the model.

    - name: unique identifier, must match the function name Ollama will call.
    - fn:   callable implementing the tool (kwargs from the model).
    - display_name: user-facing name.
    - description: short explanation of what the tool does.
    - kind: optional type hint, e.g. "shell", "http", "mcp".
    """

    name: str
    fn: ToolFn
    display_name: str | None = None
    description: str | None = None
    kind: str | None = None


class ShellSafetyError(RuntimeError):
    pass


SAFE_SHELL_WHITELIST = {
    "ls",
    "pwd",
    "whoami",
}


def enforce_safe_shell_command(command: str) -> None:
    """
    Guardrail for shell tools.

    - Only allow whitelisted leading commands.
    - Forbid obvious dangerous patterns.
    """
    cmd = command.strip()
    if not cmd:
        raise ShellSafetyError("Empty shell command is not allowed.")

    head = cmd.split()[0]
    if head not in SAFE_SHELL_WHITELIST:
        raise ShellSafetyError(f"Shell command '{head}' is not allowed.")

    forbidden = [
        "sudo",
        "rm ",
        "rm -rf",
        "mkfs",
        "dd ",
        ">:",
        ">>",
        ":(){",
    ]
    lowered = cmd.lower()
    if any(tok in lowered for tok in forbidden):
        raise ShellSafetyError("Destructive or privileged shell commands are not allowed.")

