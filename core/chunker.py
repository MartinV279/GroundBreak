from __future__ import annotations

from dataclasses import dataclass
from typing import List

from sentence_splitter import SentenceSplitter


@dataclass
class Chunk:
    id: str
    source_file_path: str
    source_file_name: str
    text: str
    chunk_index: int


_splitter = SentenceSplitter(language="en")


def split_sentences(text: str) -> List[str]:
    stripped = text.strip()
    if not stripped:
        return []
    return [s.strip() for s in _splitter.split(text) if s.strip()]


def chunk_sentences(
    sentences: List[str],
    source_file_path: str,
    source_file_name: str,
    max_chars: int = 800,
    start_id: int = 0,
) -> List[Chunk]:
    chunks: List[Chunk] = []
    buf: List[str] = []
    current_len = 0
    chunk_idx = start_id

    def flush() -> None:
        nonlocal buf, current_len, chunk_idx
        if not buf:
            return
        text = " ".join(buf).strip()
        if text:
            chunks.append(
                Chunk(
                    id=f"chunk-{chunk_idx}",
                    source_file_path=source_file_path,
                    source_file_name=source_file_name,
                    text=text,
                    chunk_index=chunk_idx,
                )
            )
            chunk_idx += 1
        buf = []
        current_len = 0

    for i, sent in enumerate(sentences):
        s = sent.strip()
        if not s:
            continue
        if current_len + len(s) + 1 > max_chars and buf:
            flush()
            # one sentence overlap with previous chunk
            prev = sentences[i - 1].strip() if i > 0 else ""
            if prev:
                buf.append(prev)
                current_len += len(prev) + 1
        buf.append(s)
        current_len += len(s) + 1

    flush()
    return chunks

