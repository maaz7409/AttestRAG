"""Plain data types passed between pipeline stages."""

import uuid
from dataclasses import dataclass


@dataclass(slots=True)
class IndexedChunk:
    """A chunk as known to the retrieval indexes."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int
    chunk_index: int
    content: str


@dataclass(slots=True)
class RetrievedChunk:
    """A chunk returned by hybrid retrieval, with per-retriever diagnostics."""

    chunk: IndexedChunk
    fused_score: float
    dense_score: float | None = None
    sparse_score: float | None = None
    dense_rank: int | None = None
    sparse_rank: int | None = None

    @property
    def chunk_id(self) -> uuid.UUID:
        return self.chunk.chunk_id
