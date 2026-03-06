from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import json
import time
import uuid


BASE_DIR = Path(__file__).resolve().parent.parent
LOCATIONS_PATH = BASE_DIR / "data" / "locations.json"
OFFLINE_INDEX_BASE = BASE_DIR / "data" / "offline_index"


@dataclass
class Location:
    id: str
    name: str
    directory: str
    index_dir: str
    ready: bool
    created_at: float
    updated_at: float


def _load_all() -> List[Location]:
    if not LOCATIONS_PATH.exists():
        return []
    try:
        with LOCATIONS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    locations: List[Location] = []
    for item in data or []:
        try:
            locations.append(
                Location(
                    id=item["id"],
                    name=item.get("name", "Untitled location"),
                    directory=item.get("directory", ""),
                    index_dir=item.get(
                        "index_dir",
                        str(OFFLINE_INDEX_BASE / item["id"]),
                    ),
                    ready=bool(item.get("ready", False)),
                    created_at=float(item.get("created_at", time.time())),
                    updated_at=float(item.get("updated_at", time.time())),
                )
            )
        except Exception:
            continue
    return locations


def _save_all(locations: List[Location]) -> None:
    LOCATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": loc.id,
            "name": loc.name,
            "directory": loc.directory,
            "index_dir": loc.index_dir,
            "ready": loc.ready,
            "created_at": loc.created_at,
            "updated_at": loc.updated_at,
        }
        for loc in locations
    ]
    with LOCATIONS_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def list_locations() -> List[Location]:
    return _load_all()


def get_location(location_id: str) -> Optional[Location]:
    for loc in _load_all():
        if loc.id == location_id:
            return loc
    return None


def create_location(name: str, directory: str) -> Location:
    locations = _load_all()
    now = time.time()
    loc_id = str(uuid.uuid4())
    directory = directory.strip()
    if not name.strip():
        # Fallback simple title from directory
        title = Path(directory).name or "New location"
        if len(title) > 60:
            title = title[:57].rstrip() + "..."
        name = title
    index_dir = str(OFFLINE_INDEX_BASE / loc_id)
    loc = Location(
        id=loc_id,
        name=name.strip(),
        directory=directory,
        index_dir=index_dir,
        ready=False,
        created_at=now,
        updated_at=now,
    )
    locations.append(loc)
    _save_all(locations)
    return loc


def update_location(location: Location) -> None:
    locations = _load_all()
    now = time.time()
    updated: List[Location] = []
    for loc in locations:
        if loc.id == location.id:
            loc = Location(
                id=location.id,
                name=location.name.strip() or "Untitled location",
                directory=location.directory.strip(),
                index_dir=location.index_dir.strip()
                or str(OFFLINE_INDEX_BASE / location.id),
                ready=bool(location.ready),
                created_at=location.created_at,
                updated_at=now,
            )
        updated.append(loc)
    _save_all(updated)


def delete_location(location_id: str) -> None:
    locations = [loc for loc in _load_all() if loc.id != location_id]
    _save_all(locations)

