"""Hybrid retrieval. Role filters run before either ranker."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from knowledge_assistant.platform import AppError

STOP = {
    "what", "is", "the", "a", "an", "of", "for", "to", "and", "does", "do", "how",
    "which", "in", "on", "at", "by", "or", "be", "are",
}

ACL_FILTER_SQL = """
SELECT c.chunk_id, c.text
FROM chunks c
WHERE c.tenant_id = %(tenant_id)s
  AND EXISTS (
      SELECT 1 FROM chunk_acl a
      WHERE a.chunk_id = c.chunk_id
        AND a.role_name = ANY(%(roles)s)
  )
"""


def tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9#-]+", text.lower()) if token not in STOP and len(token) > 1]


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    tenant_id: str
    source: str
    section: str
    text: str
    acl: set[str]
    embedding: list[float]
    embedding_model: str


class HashingEmbedder:
    def __init__(self, model_id: str, dims: int = 384) -> None:
        self.model_id = model_id
        self.dims = dims

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dims
        for token in tokenize(text) or ["empty"]:
            digest = hashlib.sha256(token.encode()).digest()
            vector[int.from_bytes(digest[:2], "big") % self.dims] += 1 if digest[2] % 2 == 0 else -1
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


def _bm25(query: str, chunks: list[Chunk]) -> list[Chunk]:
    docs = [tokenize(chunk.text) for chunk in chunks]
    if not docs:
        return []
    average = sum(len(tokens) for tokens in docs) / len(docs)
    df: dict[str, int] = defaultdict(int)
    for tokens in docs:
        for term in set(tokens):
            df[term] += 1
    query_terms = tokenize(query)
    scored: list[tuple[float, Chunk]] = []
    for chunk, tokens in zip(chunks, docs, strict=True):
        counts = Counter(tokens)
        score = 0.0
        for term in query_terms:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            idf = math.log(1 + (len(docs) - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (frequency * 2.5) / (frequency + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / average))
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _score, chunk in scored]


def _score(query: str, text: str) -> float:
    query_terms = tokenize(query)
    passage = set(tokenize(text))
    if not query_terms:
        return 0.0
    return round(len(set(query_terms) & passage) / len(set(query_terms)), 6)


@dataclass
class Corpus:
    chunks: list[Chunk] = field(default_factory=list)
    embedding_model: str | None = None

    def add(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        model = chunks[0].embedding_model
        if self.embedding_model and model != self.embedding_model:
            raise AppError(409, "Embedding model mismatch", "Rebuild the index before changing embedders.", "embedding-mismatch")
        self.embedding_model = model
        self.chunks.extend(chunks)

    def search(self, *, tenant_id: str, roles: set[str], query: str, embedding: list[float], embedding_model: str) -> list[tuple[Chunk, float]]:
        if self.embedding_model and embedding_model != self.embedding_model:
            raise AppError(409, "Embedding model mismatch", "Rebuild the index.", "embedding-mismatch")
        visible = [
            chunk
            for chunk in self.chunks
            if chunk.tenant_id == tenant_id and chunk.acl & roles
        ]
        if not visible:
            return []
        dense = sorted(
            visible,
            key=lambda chunk: sum(a * b for a, b in zip(embedding, chunk.embedding, strict=False)),
            reverse=True,
        )[:20]
        sparse = _bm25(query, visible)[:20]
        scores: dict[str, float] = defaultdict(float)
        for rank, chunk in enumerate(dense, start=1):
            scores[chunk.chunk_id] += 1 / (60 + rank)
        for rank, chunk in enumerate(sparse, start=1):
            scores[chunk.chunk_id] += 1 / (60 + rank)
        by_id = {chunk.chunk_id: chunk for chunk in visible}
        ordered = sorted(scores, key=lambda identifier: scores[identifier], reverse=True)[:5]
        return [(by_id[identifier], _score(query, by_id[identifier].text)) for identifier in ordered]
