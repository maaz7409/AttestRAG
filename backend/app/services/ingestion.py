"""PDF ingestion: parse -> chunk -> embed -> index (Qdrant + BM25) -> persist (PostgreSQL)."""

import asyncio
import hashlib
import io
import logging
import uuid
from dataclasses import dataclass

from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Chunk, Document
from app.services.bm25 import BM25Index
from app.services.text import normalize_whitespace
from app.services.types import IndexedChunk
from app.services.vector_store import QdrantStore

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Raised for user-facing ingestion problems (bad PDF, no text, ...)."""


class DuplicateDocumentError(IngestionError):
    def __init__(self, document: Document) -> None:
        super().__init__(f"'{document.filename}' has already been ingested")
        self.document = document


@dataclass(slots=True)
class PageText:
    page_number: int  # 1-based, as shown in PDF viewers
    text: str


@dataclass(slots=True)
class ChunkDraft:
    chunk_index: int
    page_number: int
    content: str


def parse_pdf(data: bytes) -> list[PageText]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            reader.decrypt("")
        pages = [
            PageText(page_number=i + 1, text=normalize_whitespace(page.extract_text() or ""))
            for i, page in enumerate(reader.pages)
        ]
    except Exception as exc:  # pypdf raises a zoo of exception types
        raise IngestionError(f"Could not read PDF: {exc}") from exc
    return pages


def chunk_pages(pages: list[PageText], chunk_size: int, chunk_overlap: int) -> list[ChunkDraft]:
    """Split each page independently so every chunk maps to exactly one page.

    Exact page attribution is what lets the UI show "report.pdf, p. 12" citations.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""],
        keep_separator="end",
    )
    drafts: list[ChunkDraft] = []
    for page in pages:
        if not page.text:
            continue
        for piece in splitter.split_text(page.text):
            piece = piece.strip()
            if len(piece) < 20:  # drop page numbers, stray headers, etc.
                continue
            drafts.append(ChunkDraft(len(drafts), page.page_number, piece))
    return drafts


class IngestionService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        embeddings: Embeddings,
        vector_store: QdrantStore,
        bm25: BM25Index,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.bm25 = bm25
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    async def ingest_pdf(self, filename: str, data: bytes) -> Document:
        digest = hashlib.sha256(data).hexdigest()
        async with self.sessionmaker() as session:
            existing = await session.scalar(select(Document).where(Document.sha256 == digest))
            if existing is not None:
                if existing.status == "ready":
                    raise DuplicateDocumentError(existing)
                await session.delete(existing)  # retry a previously failed ingestion
                await session.commit()

            document = Document(filename=filename, sha256=digest, size_bytes=len(data))
            session.add(document)
            await session.commit()
            document_id = document.id

            try:
                chunks = await self._process(document, data)
                session.add_all(
                    Chunk(
                        id=c.chunk_id,
                        document_id=document.id,
                        chunk_index=c.chunk_index,
                        page_number=c.page_number,
                        content=c.content,
                        char_count=len(c.content),
                    )
                    for c in chunks
                )
                document.num_chunks = len(chunks)
                document.status = "ready"
                await session.commit()
            except Exception as exc:
                logger.exception("Ingestion failed for %s", filename)
                await session.rollback()
                await self.vector_store.delete_document(document_id)
                await session.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(status="failed", error=str(exc)[:2000])
                )
                await session.commit()
                if isinstance(exc, IngestionError):
                    raise
                raise IngestionError(f"Ingestion failed: {exc}") from exc

            await self.bm25.add(chunks)
            logger.info(
                "Ingested %s: %d pages, %d chunks", filename, document.num_pages, len(chunks)
            )
            return document

    async def _process(self, document: Document, data: bytes) -> list[IndexedChunk]:
        pages = await asyncio.to_thread(parse_pdf, data)
        document.num_pages = len(pages)
        drafts = chunk_pages(pages, self.chunk_size, self.chunk_overlap)
        if not drafts:
            raise IngestionError(
                "No extractable text found. Scanned/image-only PDFs need OCR before ingestion."
            )
        chunks = [
            IndexedChunk(
                chunk_id=uuid.uuid4(),
                document_id=document.id,
                filename=document.filename,
                page_number=d.page_number,
                chunk_index=d.chunk_index,
                content=d.content,
            )
            for d in drafts
        ]
        vectors = await self.embeddings.aembed_documents([c.content for c in chunks])
        await self.vector_store.upsert(chunks, vectors)
        return chunks

    async def delete_document(self, document_id: uuid.UUID) -> bool:
        async with self.sessionmaker() as session:
            document = await session.get(Document, document_id)
            if document is None:
                return False
            await self.vector_store.delete_document(document_id)
            await self.bm25.remove_document(document_id)
            await session.delete(document)
            await session.commit()
            return True

    async def load_bm25_index(self) -> int:
        """Rebuild the in-memory BM25 index from PostgreSQL (called at start-up)."""
        async with self.sessionmaker() as session:
            rows = await session.execute(
                select(Chunk, Document.filename)
                .join(Document, Chunk.document_id == Document.id)
                .where(Document.status == "ready")
            )
            chunks = [
                IndexedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    filename=filename,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                )
                for chunk, filename in rows.all()
            ]
        await self.bm25.rebuild(chunks)
        return len(chunks)
