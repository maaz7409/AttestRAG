import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_session
from app.db.models import Evaluation, QueryLog
from app.schemas.api import PaginatedQueries, QueryDetailOut, QuerySummaryOut

router = APIRouter(prefix="/queries", tags=["queries"])


@router.get("", response_model=PaginatedQueries)
async def list_queries(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="answered | blocked | no_context | error"),
    session: AsyncSession = Depends(get_session),
) -> PaginatedQueries:
    """The query trail: every question asked, newest first, with its judge scores."""
    base = select(QueryLog)
    if status:
        base = base.where(QueryLog.status == status)
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = await session.execute(
        base.add_columns(
            Evaluation.faithfulness,
            Evaluation.context_relevance,
            Evaluation.toxicity,
            Evaluation.passed,
        )
        .outerjoin(Evaluation, Evaluation.query_id == QueryLog.id)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        QuerySummaryOut(
            id=log.id,
            session_id=log.session_id,
            question=log.question,
            status=log.status,
            total_ms=log.total_ms,
            created_at=log.created_at,
            faithfulness=faithfulness,
            context_relevance=context_relevance,
            toxicity=toxicity,
            passed=passed,
        )
        for log, faithfulness, context_relevance, toxicity, passed in rows.all()
    ]
    return PaginatedQueries(items=items, total=total)


@router.get("/{query_id}", response_model=QueryDetailOut)
async def get_query(query_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> QueryLog:
    log = await session.scalar(
        select(QueryLog)
        .where(QueryLog.id == query_id)
        .options(selectinload(QueryLog.sources), selectinload(QueryLog.evaluation))
    )
    if log is None:
        raise HTTPException(404, "Query not found")
    return log
