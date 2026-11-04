"""Qdrant dense-vector store."""

import logging
import uuid
from collections.abc import Sequence

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from app.services.types import IndexedChunk

logger = logging.getLogger(__name__)


class QdrantStore:
    def __init__(self, client: AsyncQdrantClient, collection: str, vector_size: int) -> None:
        self.client = client
        self.collection = collection
        self.vector_size = vector_size

    async def ensure_collection(self) -> None:
        if await self.client.collection_exists(self.collection):
            info = await self.client.get_collection(self.collection)
            params = info.config.params.vectors
            existing = params.size if isinstance(params, qm.VectorParams) else None
            if existing is not None and existing != self.vector_size:
                raise RuntimeError(
                    f"Qdrant collection '{self.collection}' stores {existing}-d vectors but the "
                    f"configured embedding model produces {self.vector_size}-d vectors. Use a "
                    "different QDRANT_COLLECTION or delete the old collection."
                )
            return

        logger.info("Creating Qdrant collection %s (dim=%d)", self.collection, self.vector_size)
        await self.client.create_collection(
            collection_name=self.collection,
            vectors_config=qm.VectorParams(size=self.vector_size, distance=qm.Distance.COSINE),
        )
        await self.client.create_payload_index(
            collection_name=self.collection,
            field_name="document_id",
            field_schema=qm.PayloadSchemaType.KEYWORD,
        )

    async def upsert(self, chunks: Sequence[IndexedChunk], vectors: Sequence[list[float]]) -> None:
        points = [
            qm.PointStruct(
                id=str(chunk.chunk_id),
                vector=vector,
                payload={
                    "document_id": str(chunk.document_id),
                    "filename": chunk.filename,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        # Batch to keep request bodies reasonably small for large PDFs.
        for start in range(0, len(points), 256):
            await self.client.upsert(
                collection_name=self.collection, points=points[start : start + 256], wait=True
            )

    async def search(
        self,
        vector: list[float],
        limit: int,
        document_ids: set[uuid.UUID] | None = None,
    ) -> list[tuple[IndexedChunk, float]]:
        query_filter = None
        if document_ids:
            query_filter = qm.Filter(
                must=[
                    qm.FieldCondition(
                        key="document_id",
                        match=qm.MatchAny(any=[str(d) for d in document_ids]),
                    )
                ]
            )
        response = await self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        )
        results: list[tuple[IndexedChunk, float]] = []
        for point in response.points:
            payload = point.payload or {}
            chunk = IndexedChunk(
                chunk_id=uuid.UUID(str(point.id)),
                document_id=uuid.UUID(payload["document_id"]),
                filename=payload.get("filename", "unknown"),
                page_number=int(payload.get("page_number", 0)),
                chunk_index=int(payload.get("chunk_index", 0)),
                content=payload.get("content", ""),
            )
            results.append((chunk, float(point.score)))
        return results

    async def delete_document(self, document_id: uuid.UUID) -> None:
        await self.client.delete(
            collection_name=self.collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="document_id", match=qm.MatchValue(value=str(document_id))
                        )
                    ]
                )
            ),
            wait=True,
        )

    async def ping(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
