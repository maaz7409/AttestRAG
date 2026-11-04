"""Request / response models for the public HTTP API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------- documents
class DocumentOut(ORMModel):
    id: uuid.UUID
    filename: str
    size_bytes: int
    num_pages: int
    num_chunks: int
    status: str
    error: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------- chat
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=64)
    document_ids: list[uuid.UUID] | None = Field(
        default=None, description="Restrict retrieval to these documents (all if omitted)."
    )
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class SourceOut(BaseModel):
    index: int = Field(description="1-based citation number used in the answer, e.g. [1]")
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int
    content: str
    dense_score: float | None
    sparse_score: float | None
    fused_score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    cited: bool = False


class EvaluationOut(BaseModel):
    judge_model: str
    faithfulness: float
    context_relevance: float
    answer_relevance: float
    toxicity: float
    passed: bool
    blocked: bool
    failed_checks: list[str]
    unsupported_claims: list[str]
    reasoning: dict[str, str]
    latency_ms: float


class LatencyOut(BaseModel):
    retrieval_ms: float
    generation_ms: float
    evaluation_ms: float
    total_ms: float
    time_to_first_token_ms: float | None


class ChatResponse(BaseModel):
    query_id: uuid.UUID
    status: str
    answer: str
    sources: list[SourceOut]
    evaluation: EvaluationOut | None
    latency: LatencyOut


# ------------------------------------------------------------------- queries
class QuerySummaryOut(ORMModel):
    id: uuid.UUID
    session_id: str | None
    question: str
    status: str
    total_ms: float
    created_at: datetime
    faithfulness: float | None = None
    context_relevance: float | None = None
    toxicity: float | None = None
    passed: bool | None = None


class QuerySourceOut(ORMModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int
    rank: int
    dense_score: float | None
    sparse_score: float | None
    fused_score: float
    cited: bool


class QueryEvaluationOut(ORMModel):
    judge_model: str
    faithfulness: float
    context_relevance: float
    answer_relevance: float
    toxicity: float
    passed: bool
    failed_checks: list[str]
    unsupported_claims: list[str]
    reasoning: dict
    latency_ms: float


class QueryDetailOut(ORMModel):
    id: uuid.UUID
    session_id: str | None
    question: str
    answer: str | None
    status: str
    chat_model: str
    guardrail_mode: str
    retrieval_ms: float
    generation_ms: float
    evaluation_ms: float
    total_ms: float
    time_to_first_token_ms: float | None
    error: str | None
    created_at: datetime
    sources: list[QuerySourceOut]
    evaluation: QueryEvaluationOut | None


class PaginatedQueries(BaseModel):
    items: list[QuerySummaryOut]
    total: int


# ----------------------------------------------------------------- analytics
class TotalsOut(BaseModel):
    queries: int
    answered: int
    blocked: int
    no_context: int
    errors: int
    documents: int
    chunks: int


class LatencyStatsOut(BaseModel):
    avg_total_ms: float | None
    p50_total_ms: float | None
    p95_total_ms: float | None
    avg_retrieval_ms: float | None
    avg_generation_ms: float | None
    avg_evaluation_ms: float | None
    avg_ttft_ms: float | None


class QualityStatsOut(BaseModel):
    evaluated: int
    pass_rate: float | None
    avg_faithfulness: float | None
    avg_context_relevance: float | None
    avg_answer_relevance: float | None
    avg_toxicity: float | None


class TimeseriesPoint(BaseModel):
    date: str
    queries: int
    blocked: int
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    avg_faithfulness: float | None
    avg_context_relevance: float | None


class CountItem(BaseModel):
    name: str
    count: int


class ScoreBucket(BaseModel):
    bucket: str
    faithfulness: int
    context_relevance: int
    answer_relevance: int


class AnalyticsOverview(BaseModel):
    window_days: int
    totals: TotalsOut
    latency: LatencyStatsOut
    quality: QualityStatsOut
    timeseries: list[TimeseriesPoint]
    failed_checks: list[CountItem]
    top_documents: list[CountItem]
    score_distribution: list[ScoreBucket]
