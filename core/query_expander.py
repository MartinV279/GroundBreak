from __future__ import annotations

from typing import List

from ollama import chat as ollama_chat

from core.config import load_config


PROMPT = (
    "You help generate alternative search queries.\n"
    "Given a user question, produce 2-3 short alternative queries:\n"
    "- one more specific\n"
    "- one keyword-focused\n"
    "- optionally one paraphrased\n"
    "Return them as a numbered list.\n"
)


def expand_query(question: str) -> List[str]:
    cfg = load_config()
    q = question.strip()
    if not q:
        return []
    messages = [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": q},
    ]
    try:
        resp = ollama_chat(
            model=cfg.model,
            messages=messages,
            options={"temperature": 0.4},
            think=False,
        )
        msg = getattr(resp, "message", resp)
        text = (getattr(msg, "content", "") or "").strip()
    except Exception:
        return []

    lines = [ln.strip("- ").strip() for ln in text.splitlines() if ln.strip()]
    queries: List[str] = []
    for ln in lines:
        # remove leading numbers like "1." or "1)"
        parts = ln.split(maxsplit=1)
        if parts and parts[0][0].isdigit() and len(parts) > 1:
            queries.append(parts[1])
        else:
            queries.append(ln)
    return queries[:3]

