from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Tuple
import json
import math
import re

from rank_bm25 import BM25Okapi

from core.embedding_model import get_sentence_model


@dataclass
class RetrievedChunk:
    chunk_id: str
    source_file_path: str
    source_file_name: str
    text: str
    chunk_index: int
    score: float


class OfflineRetriever:
    def __init__(self, index_dir: Path) -> None:
        self._index_dir = index_dir
        self._chunks: List[Dict[str, Any]] = []
        self._embeddings: List[List[float]] = []
        self._bm25: BM25Okapi | None = None
        self._load()

    def _load(self) -> None:
        chunks_path = self._index_dir / "chunks.json"
        emb_path = self._index_dir / "embeddings.json"
        bm25_path = self._index_dir / "bm25.json"
        if not (chunks_path.exists() and emb_path.exists() and bm25_path.exists()):
            return
        self._chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        self._embeddings = json.loads(emb_path.read_text(encoding="utf-8"))

        bm25_data = json.loads(bm25_path.read_text(encoding="utf-8"))
        corpus = bm25_data["corpus"]
        self._bm25 = BM25Okapi(corpus)
        # Restore internal stats
        self._bm25.idf = bm25_data["idf"]
        self._bm25.doc_len = bm25_data["doc_len"]
        self._bm25.avgdl = bm25_data["avgdl"]

    def is_ready(self) -> bool:
        return bool(self._chunks and self._embeddings and self._bm25)

    def _cosine_scores(self, query_emb: List[float]) -> List[float]:
        scores: List[float] = []
        q_norm = math.sqrt(sum(x * x for x in query_emb)) or 1.0
        for vec in self._embeddings:
            dot = sum(a * b for a, b in zip(query_emb, vec))
            v_norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            scores.append(dot / (q_norm * v_norm))
        return scores

    def retrieve(self, query: str, top_k: int = 8) -> List[RetrievedChunk]:
        if not self.is_ready():
            return []

        assert self._bm25 is not None

        def _tokenize(text: str) -> List[str]:
            return re.findall(r"\w+", text.lower())

        tokens = _tokenize(query)
        bm25_scores = list(self._bm25.get_scores(tokens))

        # Use shared model for semantic retrieval.
        model = get_sentence_model()
        q_emb = model.encode([query], convert_to_numpy=False)[0]
        sem_scores = self._cosine_scores(q_emb)

        def normalize(scores: List[float]) -> List[float]:
            if not scores:
                return []
            mn = min(scores)
            mx = max(scores)
            if mx - mn < 1e-9:
                return [0.0 for _ in scores]
            return [(s - mn) / (mx - mn) for s in scores]

        bm25_n = normalize(bm25_scores)
        sem_n = normalize(sem_scores)

        alpha = 0.6  # semantic weight
        combined = [alpha * s + (1 - alpha) * b for s, b in zip(sem_n, bm25_n)]
        ranked: List[Tuple[int, float]] = sorted(
            enumerate(combined), key=lambda x: x[1], reverse=True
        )[:top_k]

        results: List[RetrievedChunk] = []
        for idx, score in ranked:
            c = self._chunks[idx]
            results.append(
                RetrievedChunk(
                    chunk_id=c["id"],
                    source_file_path=c["source_file_path"],
                    source_file_name=c["source_file_name"],
                    text=c["text"],
                    chunk_index=int(c.get("chunk_index", idx)),
                    score=float(score),
                )
            )
        return results

