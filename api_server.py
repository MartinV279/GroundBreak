from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ollama import chat as ollama_chat

from core.config import load_config
from core.sessions import (
    ChatSession,
    create_session,
    load_session,
    save_session,
    list_sessions,
    delete_session,
)
from core.roles import get_role, list_roles, create_role, update_role, delete_role, Role
from core.locations import (
    get_location,
    list_locations,
    create_location,
    update_location,
    delete_location,
    Location,
)
from core.offline_indexer import build_index, OfflineIndexMeta
from core.rag_service import RagService, RagAnswerContext
from tools.registry import ToolRegistry


app = FastAPI(title="Ollama Desktop Chat API")

_config = load_config()
_tool_registry = ToolRegistry()


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    scope_type: Optional[str] = None  # "general" | "role" | "location"
    scope_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    sources: List[Dict[str, Any]]


class RoleCreate(BaseModel):
    name: str
    description: str
    system_prompt: str
    attached_location_id: Optional[str] = None
    hybrid_enabled: bool = False


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    attached_location_id: Optional[str] = None
    hybrid_enabled: Optional[bool] = None


class LocationCreate(BaseModel):
    name: str
    directory: str
    build_index: bool = False


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    directory: Optional[str] = None


class SessionCreate(BaseModel):
    name: Optional[str] = None
    scope_type: Optional[str] = "general"
    scope_id: Optional[str] = None


class SessionUpdate(BaseModel):
    name: Optional[str] = None


def _ensure_session(req: ChatRequest) -> ChatSession:
    if req.session_id:
        sess = load_session(req.session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return sess

    scope_type = req.scope_type or "general"
    scope_id = req.scope_id
    return create_session("New chat", scope_type=scope_type, scope_id=scope_id)


def _build_rag_context_for_scope(
    sess: ChatSession, question: str
) -> tuple[Optional[RagService], RagAnswerContext, str]:
    """Return (rag_service, context, mode) where mode is 'offline', 'hybrid', or ''."""
    if sess.scope_type == "location" and sess.scope_id:
        loc = get_location(sess.scope_id)
        if loc and loc.ready:
            rag = RagService(index_dir=loc.index_dir)
            ctx = rag.build_context(question)
            return rag, ctx, "offline"
        return None, RagAnswerContext(context_text="", sources=[]), ""

    if sess.scope_type == "role" and sess.scope_id:
        role = get_role(sess.scope_id)
        if role and role.hybrid_enabled and role.attached_location_id:
            loc = get_location(role.attached_location_id)
            if loc and loc.ready:
                rag = RagService(index_dir=loc.index_dir)
                ctx = rag.build_context(question)
                return rag, ctx, "hybrid"
    return None, RagAnswerContext(context_text="", sources=[]), ""


def _run_tool_loop(
    messages: List[Dict[str, Any]],
    tools: List[Any],
    max_iterations: int = 5,
) -> str:
    """Simplified version of ChatBackend._chat_turn for HTTP use."""
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        response = ollama_chat(
            model=_config.model,
            messages=messages,
            tools=tools,
            options={"num_ctx": 32000, "temperature": _config.temperature},
            think=False,
        )
        message = getattr(response, "message", response)
        messages.append(
            {
                "role": getattr(message, "role", "assistant"),
                "content": getattr(message, "content", "") or "",
            }
        )

        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            break

        for tc in tool_calls:
            tool_name = getattr(tc.function, "name", "")
            args = getattr(tc.function, "arguments", {}) or {}
            tool_spec = _tool_registry.get_tool_by_name(tool_name)
            if tool_spec is None:
                result = f"Tool '{tool_name}' not found."
            else:
                try:
                    result = str(tool_spec.fn(**args))
                except Exception as exc:
                    result = f"Tool error for {tool_name}: {exc}"
            messages.append(
                {
                    "role": "tool",
                    "content": result,
                    "tool_name": tool_name,
                }
            )

    final = messages[-1]
    return str(final.get("content", "") or "")


@app.get("/health", tags=["meta"])
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/roles", tags=["metadata"])
def list_roles_api() -> List[Dict[str, Any]]:
    return [r.__dict__ for r in list_roles()]


@app.get("/roles/{role_id}", tags=["metadata"])
def get_role_api(role_id: str) -> Dict[str, Any]:
    role = get_role(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role.__dict__


@app.post("/roles", tags=["roles"])
def create_role_api(payload: RoleCreate) -> Dict[str, Any]:
    role = create_role(
        payload.name,
        payload.description,
        payload.system_prompt,
        attached_location_id=payload.attached_location_id,
        hybrid_enabled=payload.hybrid_enabled,
    )
    return role.__dict__


@app.put("/roles/{role_id}", tags=["roles"])
def update_role_api(role_id: str, payload: RoleUpdate) -> Dict[str, Any]:
    role = get_role(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.system_prompt is not None:
        role.system_prompt = payload.system_prompt
    if payload.attached_location_id is not None:
        role.attached_location_id = payload.attached_location_id
    if payload.hybrid_enabled is not None:
        role.hybrid_enabled = payload.hybrid_enabled
    update_role(role)
    return role.__dict__


@app.delete("/roles/{role_id}", tags=["roles"])
def delete_role_api(role_id: str) -> Dict[str, Any]:
    # Mirror desktop behaviour: also delete chats for this role.
    for s in list_sessions():
        if s.scope_type == "role" and s.scope_id == role_id:
            delete_session(s.id)
    delete_role(role_id)
    return {"status": "deleted"}


@app.get("/locations", tags=["metadata"])
def list_locations_api() -> List[Dict[str, Any]]:
    return [loc.__dict__ for loc in list_locations()]


@app.get("/locations/{location_id}", tags=["metadata"])
def get_location_api(location_id: str) -> Dict[str, Any]:
    loc = get_location(location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return loc.__dict__


@app.post("/locations", tags=["locations"])
def create_location_api(payload: LocationCreate) -> Dict[str, Any]:
    loc = create_location(payload.name, payload.directory)
    if payload.build_index:
        meta = build_index(Path(loc.directory), Path(loc.index_dir))
        loc.ready = True
        update_location(loc)
        return {"location": loc.__dict__, "meta": meta.__dict__}
    return {"location": loc.__dict__}


@app.put("/locations/{location_id}", tags=["locations"])
def update_location_api(location_id: str, payload: LocationUpdate) -> Dict[str, Any]:
    loc = get_location(location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Location not found")
    if payload.name is not None:
        loc.name = payload.name
    if payload.directory is not None:
        loc.directory = payload.directory
        loc.ready = False
    update_location(loc)
    return loc.__dict__


@app.delete("/locations/{location_id}", tags=["locations"])
def delete_location_api(location_id: str) -> Dict[str, Any]:
    # Mirror desktop behaviour: also delete chats for this location.
    for s in list_sessions():
        if s.scope_type == "location" and s.scope_id == location_id:
            delete_session(s.id)
    loc = get_location(location_id)
    delete_location(location_id)
    if loc and loc.index_dir:
        try:
            # Best-effort index cleanup; ignore failures.
            import shutil

            shutil.rmtree(Path(loc.index_dir), ignore_errors=True)
        except Exception:
            pass
    return {"status": "deleted"}


@app.post("/locations/{location_id}/reindex", tags=["locations"])
def reindex_location_api(location_id: str) -> Dict[str, Any]:
    loc = get_location(location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Location not found")
    meta = build_index(Path(loc.directory), Path(loc.index_dir))
    loc.ready = True
    update_location(loc)
    return {"location": loc.__dict__, "meta": meta.__dict__}


@app.get("/sessions", tags=["metadata"])
def list_sessions_api() -> List[Dict[str, Any]]:
    return [s.__dict__ for s in list_sessions()]


@app.get("/sessions/{session_id}", tags=["metadata"])
def get_session_api(session_id: str) -> Dict[str, Any]:
    sess = load_session(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess.__dict__


@app.post("/sessions", tags=["sessions"])
def create_session_api(payload: SessionCreate) -> Dict[str, Any]:
    name = (payload.name or "New chat").strip()
    sess = create_session(
        name=name,
        scope_type=payload.scope_type or "general",
        scope_id=payload.scope_id,
    )
    return sess.__dict__


@app.patch("/sessions/{session_id}", tags=["sessions"])
def update_session_api(session_id: str, payload: SessionUpdate) -> Dict[str, Any]:
    sess = load_session(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if payload.name is not None:
        sess.name = payload.name.strip() or sess.name
    save_session(sess)
    return sess.__dict__


@app.delete("/sessions/{session_id}", tags=["sessions"])
def delete_session_api(session_id: str) -> Dict[str, Any]:
    delete_session(session_id)
    return {"status": "deleted"}


@app.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    sess = _ensure_session(req)
    question = req.message.strip()

    # Append user message to session history.
    sess.messages.append({"role": "user", "content": question})

    # Determine RAG behaviour based on session scope.
    rag, ctx, mode = _build_rag_context_for_scope(sess, question)

    # Build conversation history (user + assistant only) for model call.
    convo: List[Dict[str, Any]] = []
    for m in sess.messages:
        role = m.get("role")
        if role in ("user", "assistant"):
            convo.append({"role": role, "content": m.get("content", "") or ""})
    if len(convo) > 8:
        convo = convo[-8:]

    tools = _tool_registry.get_ollama_tools_for_chat()
    messages: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []

    if mode == "offline":
        # Strict offline: no tools, local context only.
        tools = []
        if ctx.context_text:
            sources = ctx.sources
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are in OFFLINE mode. Answer the user's question USING ONLY "
                        "the following local document context. If the context is "
                        "insufficient, say so explicitly and do not invent unsupported "
                        f"facts.\n\n{ctx.context_text}"
                    ),
                },
                *convo,
            ]
        else:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are in OFFLINE mode. There is no relevant local document "
                        "context for this question. You MUST say that the local "
                        "documents do not contain enough information and avoid "
                        "speculative answers."
                    ),
                },
                *convo,
            ]
    elif mode == "hybrid" and ctx.context_text:
        # Hybrid: local context + tools.
        sources = ctx.sources
        messages = [
            {
                "role": "system",
                "content": (
                    "You have access to LOCAL documents (user-specific data) and also "
                    "to web/MCP tools.\n"
                    "Prefer local documents for facts about the user's own data; use "
                    "tools for general web/background info.\n\n"
                    f"Local document context:\n{ctx.context_text}"
                ),
            },
            *convo,
        ]
    elif mode == "hybrid":
        messages = [
            {
                "role": "system",
                "content": (
                    "You have access to LOCAL documents, but none of them appear "
                    "directly relevant to the current question. You may still use "
                    "web/MCP tools, but say explicitly when local documents are "
                    "insufficient."
                ),
            },
            *convo,
        ]
    else:
        # Pure online general/role chat.
        messages = convo or [
            {"role": "user", "content": question},
        ]

    reply = _run_tool_loop(messages, tools)

    # Append assistant reply to session and persist.
    sess.messages.append({"role": "assistant", "content": reply})
    save_session(sess)

    return ChatResponse(session_id=sess.id, reply=reply, sources=sources)

