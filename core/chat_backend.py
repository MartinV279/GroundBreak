from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from PySide6.QtCore import QObject, Signal, Slot

from core.config import AppConfig
from tools.registry import ToolRegistry
from ollama import chat as ollama_chat
from core.rag_service import RagService, RagAnswerContext


Message = Dict[str, Any]


@dataclass
class ToolCallEvent:
    name: str
    arguments: Dict[str, Any]


class ChatBackend(QObject):
    """Background chat engine that talks to Ollama and tools."""

    assistant_reply = Signal(str)
    tool_call_started = Signal(str, dict)
    tool_call_finished = Signal(str, str, bool)
    error = Signal(str)
    rag_sources = Signal(list)

    def __init__(self, config: AppConfig, tool_registry: ToolRegistry) -> None:
        super().__init__()
        self._config = config
        self._tool_registry = tool_registry
        self._system_prompt_override: str | None = None
        self._temperature: float = config.temperature
        self._messages: List[Message] = [self._build_system_message()]
        self._rag: RagService | None = None
        # _rag_mode: "offline" for strict offline (Location chats),
        # "hybrid" for roles with attached Locations, or None.
        self._rag_mode: str | None = None
        self._rag_location_name: str | None = None

    def _build_system_message(self) -> Message:
        if self._system_prompt_override:
            return {"role": "system", "content": self._system_prompt_override}

        now = datetime.now()
        content = (
            "You are a helpful assistant with access to web search and other tools.\n"
            f"Current date: {now.strftime('%A, %B %d, %Y')}\n"
            f"Current time: {now.strftime('%H:%M')} (local time)\n"
            "Use tools for questions about current events, news, or information that may have changed recently."
        )
        return {"role": "system", "content": content}

    def _debug(self, label: str, value: Any | None = None) -> None:
        if not self._config.debug:
            return
        text = f"[DBG] {label}"
        if value is not None:
            text += f" {value}"
        print(text, flush=True)

    def _run_tool(self, tool_call: Any) -> str:
        tool_name = getattr(tool_call.function, "name", "")
        args = getattr(tool_call.function, "arguments", {}) or {}
        self._debug("tool_call", f"{tool_name}({args})")

        tool_spec = self._tool_registry.get_tool_by_name(tool_name)
        if tool_spec is None:
            msg = f"Tool '{tool_name}' not found."
            self.error.emit(msg)
            return msg

        self.tool_call_started.emit(tool_name, dict(args))
        try:
            result = tool_spec.fn(**args)
            result_str = str(result)
        except Exception as exc:
            msg = f"Tool error for {tool_name}: {exc}"
            self.error.emit(msg)
            self.tool_call_finished.emit(tool_name, msg, False)
            return msg

        max_len = self._config.max_tool_output_chars
        if len(result_str) > max_len:
            preview = result_str[:max_len] + "... [truncated]"
        else:
            preview = result_str

        self.tool_call_finished.emit(tool_name, preview, True)
        self._debug("tool_result_preview", preview[:200])
        return preview

    def _chat_turn(self) -> str:
        """Send messages, handle tool calls in a loop, return final text."""
        iteration = 0
        max_iterations = 5
        while iteration < max_iterations:
            iteration += 1
            self._debug("chat_turn_iteration", iteration)

            messages = self._messages
            tools = self._tool_registry.get_ollama_tools_for_chat()
            # RAG integration: either strict offline (Location chats) or hybrid (Roles).
            if self._rag is not None and self._rag.is_ready() and self._rag_mode is not None:
                # Build a short conversational history (user + assistant only),
                # but use RAG strictly over the latest user question.
                convo: List[Message] = []
                for m in self._messages:
                    role = m.get("role")
                    if role in ("user", "assistant"):
                        convo.append(
                            {
                                "role": role,
                                "content": m.get("content", "") or "",
                            }
                        )
                # Keep only the last few turns to avoid unbounded growth.
                if len(convo) > 8:
                    convo = convo[-8:]

                last_user = None
                for m in reversed(convo):
                    if m.get("role") == "user":
                        last_user = m
                        break
                question = last_user.get("content", "") if last_user else ""

                ctx: RagAnswerContext = self._rag.build_context(question)

                if self._rag_mode == "offline":
                    # Strict offline: disable tools and build a RAG-only prompt.
                    tools = []  # disable web/MCP tools in offline mode
                    if ctx.context_text:
                        self.rag_sources.emit(ctx.sources)
                        messages = [
                            self._build_system_message(),
                            {
                                "role": "system",
                                "content": (
                                    "You are in OFFLINE mode for a specific local folder. "
                                    "Answer the user's question USING ONLY the following "
                                    "local document context. If the context is insufficient, "
                                    "say so explicitly and do not invent unsupported facts.\n\n"
                                    f"{ctx.context_text}"
                                ),
                            },
                            *convo,
                        ]
                    else:
                        # No context found; instruct the model to admit lack of evidence.
                        self.rag_sources.emit([])
                        messages = [
                            self._build_system_message(),
                            {
                                "role": "system",
                                "content": (
                                    "You are in OFFLINE mode for a specific local folder. "
                                    "There is no relevant local document context for this "
                                    "question. You MUST say that the local documents do not "
                                    "contain enough information and avoid speculative answers."
                                ),
                            },
                            *convo,
                        ]
                elif self._rag_mode == "hybrid":
                    # Hybrid: keep tools enabled, but inject local context as an additional system message.
                    if ctx.context_text:
                        self.rag_sources.emit(ctx.sources)
                        loc_label = self._rag_location_name or "the attached Location"
                        messages = [
                            self._build_system_message(),
                            {
                                "role": "system",
                                "content": (
                                    f"You have access to LOCAL documents from {loc_label} "
                                    "and also to web/MCP tools.\n"
                                    "Prefer local documents for facts about the user's own "
                                    "data; use tools for general web/background info.\n\n"
                                    f"Local document context:\n{ctx.context_text}"
                                ),
                            },
                            *convo,
                        ]
                    else:
                        # No local context; still allow tools, but be transparent.
                        self.rag_sources.emit([])
                        loc_label = self._rag_location_name or "the attached Location"
                        messages = [
                            self._build_system_message(),
                            {
                                "role": "system",
                                "content": (
                                    f"You have access to LOCAL documents from {loc_label}, "
                                    "but none of them appear directly relevant to the current "
                                    "question. You may still use web/MCP tools, but you should "
                                    "say explicitly when the local documents are insufficient."
                                ),
                            },
                            *convo,
                        ]

            response = ollama_chat(
                model=self._config.model,
                messages=messages,
                tools=tools,
                options={"num_ctx": 32000, "temperature": self._temperature},
                think=False,
            )

            message = getattr(response, "message", response)
            self._messages.append({
                "role": getattr(message, "role", "assistant"),
                "content": getattr(message, "content", "") or "",
            })

            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    result = self._run_tool(tc)
                    tool_msg: Message = {
                        "role": "tool",
                        "content": result,
                        "tool_name": getattr(tc.function, "name", ""),
                    }
                    self._messages.append(tool_msg)
                continue

            final_text = getattr(message, "content", "") or ""
            self._debug("final_text", final_text[:200])
            # Keep message history bounded.
            max_history = 40
            if len(self._messages) > max_history:
                self._messages = self._messages[-max_history:]
            return final_text

        # Safety valve: avoid an infinite tool-calling loop that would feel like a freeze.
        raise RuntimeError("Too many tool-call iterations for a single message; aborted.")

    @Slot(str)
    def handle_user_message(self, text: str) -> None:
        """Entry point from the UI; runs on the worker thread."""
        text = text.strip()
        if not text:
            return

        self._messages.append({"role": "user", "content": text})
        try:
            reply = self._chat_turn()
        except Exception as exc:
            msg = f"Chat error: {exc}"
            self.error.emit(msg)
            # Remove the last user message so they can retry.
            if self._messages and self._messages[-1].get("role") == "user":
                self._messages.pop()
            return

        self.assistant_reply.emit(reply)

    @Slot()
    def reset_conversation(self) -> None:
        """Reset the current conversation while keeping the same configuration."""
        self._messages = [self._build_system_message()]

    @Slot(str)
    def update_model(self, model: str) -> None:
        """Update the model used for subsequent chat turns."""
        model = model.strip()
        if not model:
            return
        self._config.model = model

    @Slot(float)
    def update_temperature(self, temperature: float) -> None:
        """Update the temperature used for subsequent chat turns."""
        try:
            t = float(temperature)
        except (TypeError, ValueError):
            return
        if t < 0:
            t = 0.0
        self._temperature = t

    @Slot(str)
    def set_system_prompt(self, prompt: str) -> None:
        """Override the system prompt for subsequent turns."""
        text = prompt.strip()
        self._system_prompt_override = text or None
        self.reset_conversation()

    def offline_ready(self) -> bool:
        return bool(self._rag and self._rag.is_ready())

    def set_rag_index(
        self,
        index_dir: str | None,
        mode: str | None = None,
        location_name: str | None = None,
    ) -> None:
        """Configure which offline index (if any) should be used.

        mode: "offline" for strict offline (Location chats),
              "hybrid" for roles with attached Locations,
              None to disable RAG.
        """
        if index_dir is None or mode is None:
            self._rag = None
            self._rag_mode = None
            self._rag_location_name = None
            return
        if self._rag is None:
            self._rag = RagService(index_dir=index_dir)
        else:
            self._rag.set_index_dir(index_dir)
        self._rag_mode = mode
        self._rag_location_name = location_name


