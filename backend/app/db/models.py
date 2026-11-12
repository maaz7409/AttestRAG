"""Relational schema.

PostgreSQL is the system of record for everything that is *not* a vector:

* ``documents`` / ``chunks``   - what was ingested (chunk text also feeds the BM25 index)
* ``query_logs``               - one row per user question, with latency breakdown
* ``query_sources``            - source attribution: which chunks were retrieved / cited
* ``evaluations``              - LLM-as-a-Judge scores for each answer
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSONB on PostgreSQL, plain JSON elsewhere (e.g. SQLite in unit tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    num_pages: Mapped[int] = mapped_column(Integer, default=0)
    num_chunks: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="processing")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_document_position", "document_id", "chunk_index"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="chunks")


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # answered | blocked | no_context | error
    status: Mapped[str] = mapped_column(String(32), default="answered", index=True)
    chat_model: Mapped[str] = mapped_column(String(128))
    guardrail_mode: Mapped[str] = mapped_column(String(16))

    # Latency breakdown in milliseconds.
    retrieval_ms: Mapped[float] = mapped_column(Float, default=0.0)
    generation_ms: Mapped[float] = mapped_column(Float, default=0.0)
    evaluation_ms: Mapped[float] = mapped_column(Float, default=0.0)
    total_ms: Mapped[float] = mapped_column(Float, default=0.0)
    time_to_first_token_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    sources: Mapped[list["QuerySource"]] = relationship(
        back_populates="query",
        cascade="all, delete-orphan",
        order_by="QuerySource.rank",
        passive_deletes=True,
    )
    evaluation: Mapped["Evaluation | None"] = relationship(
        back_populates="query", cascade="all, delete-orphan", uselist=False, passive_deletes=True
    )


class QuerySource(Base):
    """Source attribution metadata: one row per chunk handed to the generator."""

    __tablename__ = "query_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("query_logs.id", ondelete="CASCADE"), index=True
    )
    # Not a hard FK: deleting a document must not erase historical query logs.
    chunk_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    filename: Mapped[str] = mapped_column(String(512))
    page_number: Mapped[int] = mapped_column(Integer)
    rank: Mapped[int] = mapped_column(Integer)
    dense_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sparse_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fused_score: Mapped[float] = mapped_column(Float)
    cited: Mapped[bool] = mapped_column(Boolean, default=False)

    query: Mapped[QueryLog] = relationship(back_populates="sources")


class Evaluation(Base):
    """LLM-as-a-Judge verdict for a single answer."""

    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("query_logs.id", ondelete="CASCADE"), unique=True
    )
    judge_model: Mapped[str] = mapped_column(String(128))
    faithfulness: Mapped[float] = mapped_column(Float)
    context_relevance: Mapped[float] = mapped_column(Float)
    answer_relevance: Mapped[float] = mapped_column(Float)
    toxicity: Mapped[float] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean, index=True)
    failed_checks: Mapped[list[str]] = mapped_column(JSONType, default=list)
    reasoning: Mapped[dict] = mapped_column(JSONType, default=dict)
    unsupported_claims: Mapped[list[str]] = mapped_column(JSONType, default=list)
    latency_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    query: Mapped[QueryLog] = relationship(back_populates="evaluation")
