from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any

from core.offline_retriever import OfflineRetriever, RetrievedChunk
from core.query_expander import expand_query


@dataclass
class RagAnswerContext:
    context_text: str
    sources: List[Dict[str, Any]]


class RagService:
    def __init__(self, index_dir: str | None = None) -> None:
        self._retriever: OfflineRetriever | None = None
        self._index_dir: Path | None = None
        if index_dir is not None:
            self.set_index_dir(index_dir)

    def is_ready(self) -> bool:
        return bool(self._retriever and self._retriever.is_ready())

    def set_index_dir(self, index_dir: str | None) -> None:
        """Configure which on-disk index this service should use.

        Passing None disables offline retrieval.
        """
        if index_dir is None:
            self._retriever = None
            self._index_dir = None
            return

        path = Path(index_dir)
        self._index_dir = path
        self._retriever = OfflineRetriever(path)

    def build_context(self, question: str, max_chunks: int = 10) -> RagAnswerContext:
        if not self.is_ready():
            return RagAnswerContext(context_text="", sources=[])

        assert self._retriever is not None
        base_q = question.strip()
        queries = [base_q]
        expansions = expand_query(base_q)
        queries.extend(expansions)

        merged: Dict[str, RetrievedChunk] = {}
        for q in queries:
            for rc in self._retriever.retrieve(q, top_k=6):
                existing = merged.get(rc.chunk_id)
                if existing is None or rc.score > existing.score:
                    merged[rc.chunk_id] = rc

        ranked = sorted(merged.values(), key=lambda c: c.score, reverse=True)[:max_chunks]

        context_parts: List[str] = []
        sources: List[Dict[str, Any]] = []
        for rc in ranked:
            context_parts.append(
                f"Source: {rc.source_file_path} [chunk {rc.chunk_index}]\n{rc.text}\n"
            )
            sources.append(
                {
                    "chunk_id": rc.chunk_id,
                    "source_file_path": rc.source_file_path,
                    "source_file_name": rc.source_file_name,
                    "chunk_index": rc.chunk_index,
                    "score": rc.score,
                }
            )

        context_text = "\n---\n".join(context_parts)
        return RagAnswerContext(context_text=context_text, sources=sources)

