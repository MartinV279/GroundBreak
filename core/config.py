from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List
import json
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
CONFIG_JSON_PATH = BASE_DIR / "data" / "config.json"

load_dotenv(ENV_PATH)


@dataclass
class AppConfig:
    """Simple configuration object with env + JSON support."""

    model: str = "qwen3.5:4b"
    temperature: float = 0.3
    debug: bool = False
    window_title: str = "Ollama Desktop Chat"
    max_tool_output_chars: int = 4000
    mcp_enabled: bool = False
    mcp_command: str | None = None
    mcp_args: List[str] = field(default_factory=list)


def _load_json_config() -> Dict[str, Any]:
    if not CONFIG_JSON_PATH.exists():
        return {}
    try:
        with CONFIG_JSON_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # Fail soft if config is invalid; fall back to env/defaults.
        return {}


def load_config() -> AppConfig:
    """Merge .env, config.json, and defaults into a single AppConfig."""
    data = _load_json_config()

    model = os.getenv("MODEL", data.get("model", "qwen3.5:4b"))
    temperature = float(data.get("temperature", 0.3))
    debug_env = os.getenv("DEBUG")
    if debug_env is not None:
        debug = debug_env in ("1", "true", "True", "yes", "on")
    else:
        debug = bool(data.get("debug", False))

    window_title = data.get("window_title", "Ollama Desktop Chat")
    max_tool_output_chars = int(data.get("max_tool_output_chars", 4000))

    mcp_cfg = data.get("mcp", {})
    mcp_enabled = bool(mcp_cfg.get("enabled", False))
    mcp_command = mcp_cfg.get("command")
    mcp_args = list(mcp_cfg.get("args", []))

    return AppConfig(
        model=model,
        temperature=temperature,
        debug=debug,
        window_title=window_title,
        max_tool_output_chars=max_tool_output_chars,
        mcp_enabled=mcp_enabled,
        mcp_command=mcp_command,
        mcp_args=mcp_args,
    )


def save_config(config: AppConfig) -> None:
    """Persist the current configuration to data/config.json."""
    CONFIG_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(config)
    with CONFIG_JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


