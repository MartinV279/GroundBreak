from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict
import json


BASE_DIR = Path(__file__).resolve().parent.parent
OFFLINE_CONFIG_PATH = BASE_DIR / "data" / "offline_config.json"


@dataclass
class OfflineConfig:
    enabled: bool = False
    source_dir: str | None = None
    index_dir: str = str(BASE_DIR / "data" / "offline_index")


def load_offline_config() -> OfflineConfig:
    if not OFFLINE_CONFIG_PATH.exists():
        return OfflineConfig()
    try:
        with OFFLINE_CONFIG_PATH.open("r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
    except Exception:
        return OfflineConfig()
    return OfflineConfig(
        enabled=bool(data.get("enabled", False)),
        source_dir=data.get("source_dir"),
        index_dir=data.get("index_dir", str(BASE_DIR / "data" / "offline_index")),
    )


def save_offline_config(cfg: OfflineConfig) -> None:
    OFFLINE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OFFLINE_CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=2)

