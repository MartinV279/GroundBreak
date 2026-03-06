from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any
import json
import re

from rank_bm25 import BM25Okapi

from core.document_loader import load_documents
from core.chunker import split_sentences, chunk_sentences, Chunk
from core.embedding_model import get_sentence_model


@dataclass
class OfflineIndexMeta:
    source_dir: str
    chunk_count: int
    file_count: int
    ready: bool


def build_index(source_dir: Path, index_dir: Path) -> OfflineIndexMeta:
    index_dir.mkdir(parents=True, exist_ok=True)

    docs = load_documents(source_dir)
    file_count = len(docs)

    chunks: List[Chunk] = []
    for doc in docs:
        sentences = split_sentences(doc.text)
        doc_chunks = chunk_sentences(
            sentences,
            source_file_path=str(doc.path),
            source_file_name=doc.name,
            max_chars=800,
            start_id=len(chunks),
        )
        chunks.extend(doc_chunks)

    chunks_json = [
        {
            "id": c.id,
            "source_file_path": c.source_file_path,
            "source_file_name": c.source_file_name,
            "text": c.text,
            "chunk_index": c.chunk_index,
        }
        for c in chunks
    ]
    (index_dir / "chunks.json").write_text(json.dumps(chunks_json, indent=2), encoding="utf-8")

    # Simple tokenization for BM25 (alphanumeric words, lowercased).
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    # Build BM25 and embeddings
    tokenized_corpus = [_tokenize(c.text) for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    bm25_data = {
        "corpus": tokenized_corpus,
        "idf": bm25.idf,
        "doc_len": bm25.doc_len,
        "avgdl": bm25.avgdl,
    }
    (index_dir / "bm25.json").write_text(json.dumps(bm25_data, indent=2), encoding="utf-8")

    model = get_sentence_model()
    embeddings = model.encode([c.text for c in chunks], convert_to_numpy=False)
    emb_data = [list(map(float, vec)) for vec in embeddings]
    (index_dir / "embeddings.json").write_text(json.dumps(emb_data), encoding="utf-8")

    meta = OfflineIndexMeta(
        source_dir=str(source_dir),
        chunk_count=len(chunks),
        file_count=file_count,
        ready=True,
    )
    (index_dir / "meta.json").write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")
    return meta

