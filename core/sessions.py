from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import time
import uuid


BASE_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = BASE_DIR / "data" / "sessions"


@dataclass
class ChatSession:
    id: str
    name: str
    created_at: float
    updated_at: float
    messages: List[Dict[str, Any]]
    scope_type: str = "general"  # "general" or "role"
    scope_id: Optional[str] = None


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def ensure_sessions_dir() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def create_session(
    name: str = "New chat",
    scope_type: str = "general",
    scope_id: Optional[str] = None,
) -> ChatSession:
    now = time.time()
    session = ChatSession(
        id=str(uuid.uuid4()),
        name=name,
        created_at=now,
        updated_at=now,
        messages=[],
        scope_type=scope_type,
        scope_id=scope_id,
    )
    save_session(session)
    return session


def save_session(session: ChatSession) -> None:
    ensure_sessions_dir()
    session.updated_at = time.time()
    data = {
        "id": session.id,
        "name": session.name,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": session.messages,
        "scope_type": session.scope_type,
        "scope_id": session.scope_id,
    }
    with _session_path(session.id).open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_session(session_id: str) -> Optional[ChatSession]:
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return ChatSession(
            id=data["id"],
            name=data.get("name", "Chat"),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            messages=list(data.get("messages", [])),
            scope_type=data.get("scope_type", "general"),
            scope_id=data.get("scope_id"),
        )
    except Exception:
        return None


def delete_session(session_id: str) -> None:
    path = _session_path(session_id)
    if path.exists():
        path.unlink()


def list_sessions() -> List[ChatSession]:
    ensure_sessions_dir()
    sessions: List[ChatSession] = []
    for path in sorted(SESSIONS_DIR.glob("*.json")):
        sid = path.stem
        sess = load_session(sid)
        if sess is not None:
            sessions.append(sess)
    sessions.sort(key=lambda s: s.updated_at, reverse=True)
    return sessions

