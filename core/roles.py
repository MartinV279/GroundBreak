from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import json
import time
import uuid


BASE_DIR = Path(__file__).resolve().parent.parent
ROLES_PATH = BASE_DIR / "data" / "roles.json"


@dataclass
class Role:
    id: str
    name: str
    description: str
    system_prompt: str
    created_at: float
    updated_at: float
    model: str | None = None
    temperature: float | None = None
    attached_location_id: str | None = None
    hybrid_enabled: bool = False


def _load_all() -> List[Role]:
    if not ROLES_PATH.exists():
        return []
    try:
        with ROLES_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    roles: List[Role] = []
    for item in data or []:
        roles.append(
            Role(
                id=item["id"],
                name=item.get("name", "Untitled role"),
                description=item.get("description", ""),
                system_prompt=item.get("system_prompt", ""),
                model=item.get("model"),
                temperature=item.get("temperature"),
                created_at=float(item.get("created_at", time.time())),
                updated_at=float(item.get("updated_at", time.time())),
                attached_location_id=item.get("attached_location_id"),
                hybrid_enabled=bool(item.get("hybrid_enabled", False)),
            )
        )
    return roles


def _save_all(roles: List[Role]) -> None:
    ROLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "system_prompt": r.system_prompt,
            "model": r.model,
            "temperature": r.temperature,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "attached_location_id": r.attached_location_id,
            "hybrid_enabled": r.hybrid_enabled,
        }
        for r in roles
    ]
    with ROLES_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def list_roles() -> List[Role]:
    return _load_all()


def get_role(role_id: str) -> Optional[Role]:
    for r in _load_all():
        if r.id == role_id:
            return r
    return None


def create_role(
    name: str,
    description: str,
    system_prompt: str,
    attached_location_id: str | None = None,
    hybrid_enabled: bool = False,
) -> Role:
    roles = _load_all()
    now = time.time()
    rid = str(uuid.uuid4())
    if not name.strip():
        # Fallback simple title from description
        title = (description or "New role").strip().splitlines()[0]
        if len(title) > 60:
            title = title[:57].rstrip() + "..."
        name = title or "New role"
    role = Role(
        id=rid,
        name=name.strip(),
        description=description.strip(),
        system_prompt=system_prompt.strip(),
        model=None,
        temperature=None,
        created_at=now,
        updated_at=now,
        attached_location_id=attached_location_id,
        hybrid_enabled=hybrid_enabled,
    )
    roles.append(role)
    _save_all(roles)
    return role


def update_role(role: Role) -> None:
    roles = _load_all()
    now = time.time()
    updated: List[Role] = []
    for r in roles:
        if r.id == role.id:
            r = Role(
                id=role.id,
                name=role.name.strip() or "Untitled role",
                description=role.description.strip(),
                system_prompt=role.system_prompt.strip(),
                model=role.model,
                temperature=role.temperature,
                created_at=role.created_at,
                updated_at=now,
                attached_location_id=role.attached_location_id,
                hybrid_enabled=role.hybrid_enabled,
            )
        updated.append(r)
    _save_all(updated)


def delete_role(role_id: str) -> None:
    roles = [r for r in _load_all() if r.id != role_id]
    _save_all(roles)

