"""Hybrid retrieval: Qdrant dense search + BM25 keyword search, fused with RRF."""

import asyncio
import uuid
from dataclasses import dataclass

from langchain_core.embeddings import Embeddings

from app.services.bm25 import BM25Index
from app.services.types import IndexedChunk, RetrievedChunk
from app.services.vector_store import QdrantStore


def reciprocal_rank_fusion(
    dense: list[tuple[IndexedChunk, float]],
    sparse: list[tuple[IndexedChunk, float]],
    *,
    k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
    top_n: int = 6,
) -> list[RetrievedChunk]:
    """Merge two ranked lists with (weighted) Reciprocal Rank Fusion.

    ``score(d) = sum_r  w_r / (k + rank_r(d))``

    RRF only looks at *ranks*, so we never have to calibrate cosine similarities
    (0..1) against BM25 scores (unbounded). A chunk that ranks well in both lists
    rises to the top; a chunk found by only one retriever still gets a chance.
    """
    fused: dict[uuid.UUID, RetrievedChunk] = {}

    for rank, (chunk, score) in enumerate(dense, start=1):
        item = fused.setdefault(chunk.chunk_id, RetrievedChunk(chunk=chunk, fused_score=0.0))
        item.dense_score, item.dense_rank = score, rank
        item.fused_score += dense_weight / (k + rank)

    for rank, (chunk, score) in enumerate(sparse, start=1):
        item = fused.setdefault(chunk.chunk_id, RetrievedChunk(chunk=chunk, fused_score=0.0))
        item.sparse_score, item.sparse_rank = score, rank
        item.fused_score += sparse_weight / (k + rank)

    ranked = sorted(fused.values(), key=lambda r: r.fused_score, reverse=True)
    return ranked[:top_n]


@dataclass(slots=True)
class RetrievalConfig:
    dense_top_k: int = 20
    sparse_top_k: int = 20
    final_top_k: int = 6
    rrf_k: int = 60
    dense_weight: float = 1.0
    sparse_weight: float = 1.0


class HybridRetriever:
    def __init__(
        self,
        embeddings: Embeddings,
        vector_store: QdrantStore,
        bm25: BM25Index,
        config: RetrievalConfig,
    ) -> None:
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.bm25 = bm25
        self.config = config

    async def _dense(
        self, question: str, document_ids: set[uuid.UUID] | None
    ) -> list[tuple[IndexedChunk, float]]:
        vector = await self.embeddings.aembed_query(question)
        return await self.vector_store.search(vector, self.config.dense_top_k, document_ids)

    async def _sparse(
        self, question: str, document_ids: set[uuid.UUID] | None
    ) -> list[tuple[IndexedChunk, float]]:
        return self.bm25.search(question, self.config.sparse_top_k, document_ids)

    async def retrieve(
        self, question: str, document_ids: set[uuid.UUID] | None = None
    ) -> list[RetrievedChunk]:
        # Both retrievers run concurrently; total latency ~= the slower one.
        dense, sparse = await asyncio.gather(
            self._dense(question, document_ids), self._sparse(question, document_ids)
        )
        return reciprocal_rank_fusion(
            dense,
            sparse,
            k=self.config.rrf_k,
            dense_weight=self.config.dense_weight,
            sparse_weight=self.config.sparse_weight,
            top_n=self.config.final_top_k,
        )
