"""Dependency wiring: builds every long-lived service once per process."""

import asyncio
import logging
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import Database
from app.services.bm25 import BM25Index
from app.services.generation import AnswerGenerator, ExtractiveAnswerGenerator, LLMAnswerGenerator
from app.services.ingestion import IngestionService
from app.services.judge import (
    EvaluationService,
    HeuristicJudge,
    Judge,
    LLMJudge,
    Thresholds,
)
from app.services.pipeline import RAGPipeline
from app.services.providers import build_chat_model, build_embeddings
from app.services.retrieval import HybridRetriever, RetrievalConfig
from app.services.vector_store import QdrantStore

logger = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    db: Database
    qdrant: AsyncQdrantClient
    vector_store: QdrantStore
    bm25: BM25Index
    ingestion: IngestionService
    pipeline: RAGPipeline

    async def startup(self, retries: int = 30, delay: float = 2.0) -> None:
        """Wait for PostgreSQL and Qdrant, create schema/collection, warm the BM25 index."""
        for attempt in range(1, retries + 1):
            try:
                await self.db.create_all()
                await self.vector_store.ensure_collection()
                break
            except RuntimeError:
                raise  # configuration error (e.g. vector size mismatch): fail fast
            except Exception as exc:
                if attempt == retries:
                    raise
                logger.warning("Dependencies not ready (%s), retry %d/%d", exc, attempt, retries)
                await asyncio.sleep(delay)
        count = await self.ingestion.load_bm25_index()
        logger.info("BM25 index warmed with %d chunks", count)

    async def shutdown(self) -> None:
        await self.pipeline.drain()
        await self.qdrant.close()
        await self.db.dispose()

    async def check_health(self) -> dict[str, str]:
        status = {"postgres": "ok", "qdrant": "ok"}
        try:
            async with self.db.sessionmaker() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            status["postgres"] = "unavailable"
        if not await self.vector_store.ping():
            status["qdrant"] = "unavailable"
        return status


def build_services(settings: Settings, qdrant: AsyncQdrantClient | None = None) -> Services:
    db = Database(settings.database_url)
    if qdrant is None:
        if settings.qdrant_url == ":memory:":  # embedded mode for local dev without a server
            qdrant = AsyncQdrantClient(location=":memory:")
        else:
            qdrant = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    vector_store = QdrantStore(qdrant, settings.qdrant_collection, settings.vector_size)
    bm25 = BM25Index()
    embeddings = build_embeddings(settings)

    ingestion = IngestionService(
        sessionmaker=db.sessionmaker,
        embeddings=embeddings,
        vector_store=vector_store,
        bm25=bm25,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    retriever = HybridRetriever(
        embeddings,
        vector_store,
        bm25,
        RetrievalConfig(
            dense_top_k=settings.dense_top_k,
            sparse_top_k=settings.sparse_top_k,
            final_top_k=settings.final_top_k,
            rrf_k=settings.rrf_k,
            dense_weight=settings.dense_weight,
            sparse_weight=settings.sparse_weight,
        ),
    )

    generator: AnswerGenerator
    judge: Judge
    if settings.llm_provider == "fake":
        generator = ExtractiveAnswerGenerator()
        judge = HeuristicJudge()
    else:
        generator = LLMAnswerGenerator(
            build_chat_model(settings, settings.chat_model), settings.chat_model
        )
        judge = LLMJudge(
            build_chat_model(settings, settings.judge_model, streaming=False), settings.judge_model
        )

    evaluator = (
        EvaluationService(
            judge,
            Thresholds(
                faithfulness=settings.faithfulness_threshold,
                context_relevance=settings.context_relevance_threshold,
                toxicity=settings.toxicity_threshold,
            ),
        )
        if settings.judge_enabled
        else None
    )
    pipeline = RAGPipeline(
        retriever=retriever,
        generator=generator,
        evaluator=evaluator,
        sessionmaker=db.sessionmaker,
        guardrail_mode=settings.guardrail_mode,
    )
    return Services(
        settings=settings,
        db=db,
        qdrant=qdrant,
        vector_store=vector_store,
        bm25=bm25,
        ingestion=ingestion,
        pipeline=pipeline,
    )
