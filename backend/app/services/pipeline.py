"""End-to-end RAG pipeline: retrieve -> generate -> judge -> deliver -> log.

The pipeline is an async generator of events that the API layer serialises as
Server-Sent Events. Event types, in order:

``start`` -> ``sources`` -> ``token``* -> ``evaluation`` -> ``blocked``? -> ``done``

(``error`` may replace the tail of the sequence if something fails.)

Guardrail modes
---------------
``stream``  Tokens are forwarded as soon as the model produces them (lowest
            perceived latency). The judge runs right after; if the answer fails
            a blocking check the UI receives ``blocked`` and retracts it.
``strict``  The answer is buffered, judged, and only released if it passes -
            nothing unverified ever reaches the user.

Persistence to PostgreSQL happens in a background task so logging never adds
latency to the user-facing response.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Evaluation, QueryLog, QuerySource
from app.schemas.api import ChatRequest
from app.services.generation import NO_ANSWER, AnswerGenerator, extract_citations, to_history
from app.services.judge import EvaluationService, JudgeResult
from app.services.retrieval import HybridRetriever
from app.services.types import RetrievedChunk

logger = logging.getLogger(__name__)

BLOCKED_MESSAGE = (
    "This answer was withheld because our automated quality check could not verify it "
    "against your documents. Try rephrasing the question or narrowing it to a specific document."
)
TOXIC_MESSAGE = "This answer was withheld because it did not meet our content-safety standards."

Event = dict[str, Any]


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def serialize_sources(chunks: Sequence[RetrievedChunk], cited: set[int]) -> list[dict]:
    return [
        {
            "index": i,
            "chunk_id": str(item.chunk.chunk_id),
            "document_id": str(item.chunk.document_id),
            "filename": item.chunk.filename,
            "page_number": item.chunk.page_number,
            "content": item.chunk.content,
            "dense_score": item.dense_score,
            "sparse_score": item.sparse_score,
            "fused_score": round(item.fused_score, 6),
            "dense_rank": item.dense_rank,
            "sparse_rank": item.sparse_rank,
            "cited": i in cited,
        }
        for i, item in enumerate(chunks, start=1)
    ]


def serialize_evaluation(result: JudgeResult) -> dict:
    v = result.verdict
    return {
        "judge_model": result.judge_model,
        "faithfulness": v.faithfulness,
        "context_relevance": v.context_relevance,
        "answer_relevance": v.answer_relevance,
        "toxicity": v.toxicity,
        "passed": result.passed,
        "blocked": result.blocked,
        "failed_checks": result.failed_checks,
        "unsupported_claims": v.unsupported_claims,
        "reasoning": {
            "faithfulness": v.faithfulness_reasoning,
            "relevance": v.relevance_reasoning,
            "toxicity": v.toxicity_reasoning,
        },
        "latency_ms": round(result.latency_ms, 2),
    }


@dataclass(slots=True)
class QueryRecord:
    """Everything the background logger needs to persist one query."""

    query_id: uuid.UUID
    request: ChatRequest
    status: str = "answered"
    answer: str | None = None
    chunks: Sequence[RetrievedChunk] = ()
    cited: frozenset[int] = frozenset()
    judge: JudgeResult | None = None
    retrieval_ms: float = 0.0
    generation_ms: float = 0.0
    evaluation_ms: float = 0.0
    total_ms: float = 0.0
    ttft_ms: float | None = None
    error: str | None = None


class RAGPipeline:
    def __init__(
        self,
        retriever: HybridRetriever,
        generator: AnswerGenerator,
        evaluator: EvaluationService | None,
        sessionmaker: async_sessionmaker[AsyncSession],
        guardrail_mode: Literal["stream", "strict"] = "stream",
    ) -> None:
        self.retriever = retriever
        self.generator = generator
        self.evaluator = evaluator
        self.sessionmaker = sessionmaker
        self.guardrail_mode = guardrail_mode
        self._background: set[asyncio.Task] = set()

    # ------------------------------------------------------------- streaming
    async def stream(self, request: ChatRequest) -> AsyncIterator[Event]:
        record = QueryRecord(query_id=uuid.uuid4(), request=request)
        started = time.perf_counter()
        strict = self.guardrail_mode == "strict"
        yield {
            "type": "start",
            "query_id": str(record.query_id),
            "guardrail_mode": self.guardrail_mode,
        }

        try:
            # 1) Hybrid retrieval ------------------------------------------------
            t = time.perf_counter()
            doc_filter = set(request.document_ids) if request.document_ids else None
            chunks = await self.retriever.retrieve(request.question, doc_filter)
            record.retrieval_ms = _ms(t)
            record.chunks = chunks
            yield {"type": "sources", "sources": serialize_sources(chunks, set())}

            # 2) Generation --------------------------------------------------------
            if not chunks:
                record.status = "no_context"
                record.answer = NO_ANSWER
                yield {"type": "token", "content": NO_ANSWER}
            else:
                t = time.perf_counter()
                history = to_history([(h.role, h.content) for h in request.history])
                parts: list[str] = []
                async for token in self.generator.astream(request.question, chunks, history):
                    if record.ttft_ms is None:
                        record.ttft_ms = _ms(started)
                    parts.append(token)
                    if not strict:
                        yield {"type": "token", "content": token}
                record.generation_ms = _ms(t)
                record.answer = "".join(parts).strip() or NO_ANSWER
                record.cited = frozenset(extract_citations(record.answer, len(chunks)))

                # 3) LLM-as-a-Judge ------------------------------------------------
                if self.evaluator is not None:
                    t = time.perf_counter()
                    try:
                        record.judge = await self.evaluator.evaluate(
                            request.question, record.answer, chunks
                        )
                    except Exception:  # judge outage must not take the product down
                        logger.exception("Judge failed for query %s", record.query_id)
                    record.evaluation_ms = _ms(t)
                    if record.judge is not None:
                        yield {"type": "evaluation", **serialize_evaluation(record.judge)}

                # 4) Guardrail decision -------------------------------------------
                if record.judge is not None and record.judge.blocked:
                    record.status = "blocked"
                    toxic = "toxicity" in record.judge.failed_checks
                    yield {
                        "type": "blocked",
                        "reasons": record.judge.failed_checks,
                        "message": TOXIC_MESSAGE if toxic else BLOCKED_MESSAGE,
                    }
                elif strict:
                    # Release the verified answer (re-chunked so the UI still "types").
                    for i in range(0, len(record.answer), 24):
                        yield {"type": "token", "content": record.answer[i : i + 24]}

            record.total_ms = _ms(started)
            yield {
                "type": "done",
                "query_id": str(record.query_id),
                "status": record.status,
                "cited": sorted(record.cited),
                "latency": {
                    "retrieval_ms": record.retrieval_ms,
                    "generation_ms": record.generation_ms,
                    "evaluation_ms": record.evaluation_ms,
                    "total_ms": record.total_ms,
                    "time_to_first_token_ms": record.ttft_ms,
                },
            }
        except Exception as exc:
            logger.exception("Pipeline failed for query %s", record.query_id)
            record.status = "error"
            record.error = f"{type(exc).__name__}: {exc}"[:2000]
            record.total_ms = _ms(started)
            yield {"type": "error", "query_id": str(record.query_id), "message": "Internal error"}
        finally:
            if record.total_ms == 0.0:  # client disconnected mid-stream
                record.status = "error"
                record.error = record.error or "client disconnected"
                record.total_ms = _ms(started)
            self._spawn_persist(record)

    # ----------------------------------------------------------- persistence
    def _spawn_persist(self, record: QueryRecord) -> None:
        task = asyncio.create_task(self._persist(record))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def drain(self) -> None:
        """Wait for in-flight log writes (used on shutdown and in tests)."""
        if self._background:
            await asyncio.gather(*list(self._background), return_exceptions=True)

    async def _persist(self, record: QueryRecord) -> None:
        try:
            async with self.sessionmaker() as session:
                log = QueryLog(
                    id=record.query_id,
                    session_id=record.request.session_id,
                    question=record.request.question,
                    answer=record.answer,
                    status=record.status,
                    chat_model=self.generator.model_name,
                    guardrail_mode=self.guardrail_mode,
                    retrieval_ms=record.retrieval_ms,
                    generation_ms=record.generation_ms,
                    evaluation_ms=record.evaluation_ms,
                    total_ms=record.total_ms,
                    time_to_first_token_ms=record.ttft_ms,
                    error=record.error,
                )
                log.sources = [
                    QuerySource(
                        chunk_id=item.chunk.chunk_id,
                        document_id=item.chunk.document_id,
                        filename=item.chunk.filename,
                        page_number=item.chunk.page_number,
                        rank=rank,
                        dense_score=item.dense_score,
                        sparse_score=item.sparse_score,
                        fused_score=item.fused_score,
                        cited=rank in record.cited,
                    )
                    for rank, item in enumerate(record.chunks, start=1)
                ]
                if record.judge is not None:
                    v = record.judge.verdict
                    log.evaluation = Evaluation(
                        judge_model=record.judge.judge_model,
                        faithfulness=v.faithfulness,
                        context_relevance=v.context_relevance,
                        answer_relevance=v.answer_relevance,
                        toxicity=v.toxicity,
                        passed=record.judge.passed,
                        failed_checks=record.judge.failed_checks,
                        unsupported_claims=v.unsupported_claims,
                        reasoning={
                            "faithfulness": v.faithfulness_reasoning,
                            "relevance": v.relevance_reasoning,
                            "toxicity": v.toxicity_reasoning,
                        },
                        latency_ms=record.judge.latency_ms,
                    )
                session.add(log)
                await session.commit()
        except Exception:
            logger.exception("Failed to persist query log %s", record.query_id)

    # ---------------------------------------------------------- non-streaming
    async def run(self, request: ChatRequest) -> dict[str, Any]:
        """Collect the event stream into a single JSON-friendly response."""
        answer_parts: list[str] = []
        result: dict[str, Any] = {"sources": [], "evaluation": None}
        async for event in self.stream(request):
            kind = event["type"]
            if kind == "token":
                answer_parts.append(event["content"])
            elif kind == "sources":
                result["sources"] = event["sources"]
            elif kind == "evaluation":
                result["evaluation"] = {k: v for k, v in event.items() if k != "type"}
            elif kind == "blocked":
                answer_parts = [event["message"]]
            elif kind == "done":
                cited = set(event["cited"])
                for source in result["sources"]:
                    source["cited"] = source["index"] in cited
                result.update(
                    query_id=event["query_id"], status=event["status"], latency=event["latency"]
                )
            elif kind == "error":
                raise RuntimeError(event["message"])
        result["answer"] = "".join(answer_parts).strip()
        return result
