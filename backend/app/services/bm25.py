"""In-memory BM25 (Okapi) keyword index.

Dense embeddings are great at paraphrases but weak on exact identifiers such as
product codes, clause numbers, acronyms or names. BM25 covers that gap.

The index is rebuilt from PostgreSQL (the source of truth for chunk text) at
start-up and updated incrementally as documents are ingested or deleted.
"""

import asyncio
import math
import uuid
from collections import Counter, defaultdict

from app.services.text import tokenize
from app.services.types import IndexedChunk


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._lock = asyncio.Lock()
        self._chunks: dict[uuid.UUID, IndexedChunk] = {}
        self._lengths: dict[uuid.UUID, int] = {}
        self._postings: dict[str, dict[uuid.UUID, int]] = defaultdict(dict)
        self._total_length = 0

    # ------------------------------------------------------------------ write
    def _add(self, chunk: IndexedChunk) -> None:
        if chunk.chunk_id in self._chunks:
            self._remove(chunk.chunk_id)
        terms = Counter(tokenize(chunk.content))
        self._chunks[chunk.chunk_id] = chunk
        length = sum(terms.values())
        self._lengths[chunk.chunk_id] = length
        self._total_length += length
        for term, tf in terms.items():
            self._postings[term][chunk.chunk_id] = tf

    def _remove(self, chunk_id: uuid.UUID) -> None:
        chunk = self._chunks.pop(chunk_id, None)
        if chunk is None:
            return
        self._total_length -= self._lengths.pop(chunk_id, 0)
        for term in set(tokenize(chunk.content)):
            postings = self._postings.get(term)
            if postings is not None:
                postings.pop(chunk_id, None)
                if not postings:
                    del self._postings[term]

    async def rebuild(self, chunks: list[IndexedChunk]) -> None:
        async with self._lock:
            self._chunks.clear()
            self._lengths.clear()
            self._postings.clear()
            self._total_length = 0
            for chunk in chunks:
                self._add(chunk)

    async def add(self, chunks: list[IndexedChunk]) -> None:
        async with self._lock:
            for chunk in chunks:
                self._add(chunk)

    async def remove_document(self, document_id: uuid.UUID) -> None:
        async with self._lock:
            doomed = [c.chunk_id for c in self._chunks.values() if c.document_id == document_id]
            for chunk_id in doomed:
                self._remove(chunk_id)

    # ------------------------------------------------------------------- read
    def __len__(self) -> int:
        return len(self._chunks)

    def _idf(self, term: str) -> float:
        # Lucene-style IDF: always positive, even for very common terms.
        n_docs = len(self._chunks)
        df = len(self._postings.get(term, ()))
        return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))

    def search(
        self,
        query: str,
        k: int,
        document_ids: set[uuid.UUID] | None = None,
    ) -> list[tuple[IndexedChunk, float]]:
        if not self._chunks:
            return []
        avg_len = self._total_length / len(self._chunks) or 1.0
        scores: dict[uuid.UUID, float] = defaultdict(float)
        for term in set(tokenize(query)):
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = self._idf(term)
            for chunk_id, tf in postings.items():
                norm = self.k1 * (1 - self.b + self.b * self._lengths[chunk_id] / avg_len)
                scores[chunk_id] += idf * tf * (self.k1 + 1) / (tf + norm)

        results = [
            (self._chunks[cid], score)
            for cid, score in scores.items()
            if document_ids is None or self._chunks[cid].document_id in document_ids
        ]
        results.sort(key=lambda item: item[1], reverse=True)
        return results[:k]
