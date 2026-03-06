from __future__ import annotations

from typing import Optional

from ollama import chat as ollama_chat

from core.config import load_config


ROLE_PROMPT_SYSTEM = (
    "You are an AI that generates high-quality system prompts for other AI assistants.\n"
    "Given a natural language description of a role, write a clear, practical, reusable "
    "system prompt that:\n"
    "- Sets expectations for tone, behaviour and scope.\n"
    "- Mentions the target domain and audience.\n"
    "- Avoids referring to itself as an AI language model.\n"
    "- Is suitable to be used as a system message for many conversations.\n"
    "Respond ONLY with the system prompt, no explanation or commentary."
)


def generate_role_system_prompt(description: str) -> Optional[str]:
    """Use the configured model to generate a role system prompt."""
    cfg = load_config()
    desc = description.strip()
    if not desc:
        return None

    messages = [
        {"role": "system", "content": ROLE_PROMPT_SYSTEM},
        {
            "role": "user",
            "content": f"Role description:\n{desc}",
        },
    ]
    try:
        resp = ollama_chat(
            model=cfg.model,
            messages=messages,
            options={"temperature": 0.4},
            think=False,
        )
    except Exception:
        return None

    msg = getattr(resp, "message", resp)
    text = (getattr(msg, "content", "") or "").strip()
    if not text:
        return None
    return text

