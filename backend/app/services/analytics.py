"""Aggregations that power the analytics dashboard.

Counts and averages are pushed down to the database. Percentiles and daily
bucketing are computed in Python over the (bounded) analysis window so the same
code runs on PostgreSQL in production and SQLite in unit tests.
"""

import math
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, Evaluation, QueryLog, QuerySource
from app.schemas.api import (
    AnalyticsOverview,
    CountItem,
    LatencyStatsOut,
    QualityStatsOut,
    ScoreBucket,
    TimeseriesPoint,
    TotalsOut,
)

MAX_ROWS = 50_000


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile (same definition as PostgreSQL percentile_cont)."""
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return round(ordered[lo], 2)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo), 2)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def build_overview(session: AsyncSession, days: int = 14) -> AnalyticsOverview:
    since = datetime.now(UTC) - timedelta(days=days)

    rows = (
        await session.execute(
            select(
                QueryLog.created_at,
                QueryLog.status,
                QueryLog.total_ms,
                QueryLog.retrieval_ms,
                QueryLog.generation_ms,
                QueryLog.evaluation_ms,
                QueryLog.time_to_first_token_ms,
                Evaluation.faithfulness,
                Evaluation.context_relevance,
                Evaluation.answer_relevance,
                Evaluation.toxicity,
                Evaluation.passed,
                Evaluation.failed_checks,
            )
            .outerjoin(Evaluation, Evaluation.query_id == QueryLog.id)
            .where(QueryLog.created_at >= since)
            .order_by(QueryLog.created_at.desc())
            .limit(MAX_ROWS)
        )
    ).all()

    status_counts = Counter(r.status for r in rows)
    ok_rows = [r for r in rows if r.status != "error"]
    evaluated = [r for r in rows if r.faithfulness is not None]

    totals = TotalsOut(
        queries=len(rows),
        answered=status_counts["answered"],
        blocked=status_counts["blocked"],
        no_context=status_counts["no_context"],
        errors=status_counts["error"],
        documents=await session.scalar(
            select(func.count()).select_from(Document).where(Document.status == "ready")
        )
        or 0,
        chunks=await session.scalar(select(func.count()).select_from(Chunk)) or 0,
    )

    totals_ms = [r.total_ms for r in ok_rows]
    latency = LatencyStatsOut(
        avg_total_ms=_mean(totals_ms),
        p50_total_ms=percentile(totals_ms, 0.5),
        p95_total_ms=percentile(totals_ms, 0.95),
        avg_retrieval_ms=_mean([r.retrieval_ms for r in ok_rows]),
        avg_generation_ms=_mean([r.generation_ms for r in ok_rows if r.generation_ms]),
        avg_evaluation_ms=_mean([r.evaluation_ms for r in ok_rows if r.evaluation_ms]),
        avg_ttft_ms=_mean([r.time_to_first_token_ms for r in ok_rows if r.time_to_first_token_ms]),
    )

    quality = QualityStatsOut(
        evaluated=len(evaluated),
        pass_rate=_mean([1.0 if r.passed else 0.0 for r in evaluated]),
        avg_faithfulness=_mean([r.faithfulness for r in evaluated]),
        avg_context_relevance=_mean([r.context_relevance for r in evaluated]),
        avg_answer_relevance=_mean([r.answer_relevance for r in evaluated]),
        avg_toxicity=_mean([r.toxicity for r in evaluated]),
    )

    # Daily time series (every day in the window, including empty ones).
    by_day: dict[str, list] = defaultdict(list)
    for r in rows:
        by_day[_as_utc(r.created_at).date().isoformat()].append(r)
    today = datetime.now(UTC).date()
    timeseries = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        day_rows = by_day.get(day, [])
        day_ok = [r.total_ms for r in day_rows if r.status != "error"]
        day_eval = [r for r in day_rows if r.faithfulness is not None]
        timeseries.append(
            TimeseriesPoint(
                date=day,
                queries=len(day_rows),
                blocked=sum(1 for r in day_rows if r.status == "blocked"),
                avg_latency_ms=_mean(day_ok),
                p95_latency_ms=percentile(day_ok, 0.95),
                avg_faithfulness=_mean([r.faithfulness for r in day_eval]),
                avg_context_relevance=_mean([r.context_relevance for r in day_eval]),
            )
        )

    failed = Counter(check for r in evaluated for check in (r.failed_checks or []))
    failed_checks = [CountItem(name=name, count=count) for name, count in failed.most_common()]

    top_docs = (
        await session.execute(
            select(QuerySource.filename, func.count().label("n"))
            .join(QueryLog, QueryLog.id == QuerySource.query_id)
            .where(QuerySource.cited.is_(True), QueryLog.created_at >= since)
            .group_by(QuerySource.filename)
            .order_by(func.count().desc())
            .limit(8)
        )
    ).all()

    edges = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0001]
    distribution = []
    for lo, hi in zip(edges, edges[1:], strict=False):
        label = f"{lo:.1f}-{min(hi, 1.0):.1f}"
        distribution.append(
            ScoreBucket(
                bucket=label,
                faithfulness=sum(1 for r in evaluated if lo <= r.faithfulness < hi),
                context_relevance=sum(1 for r in evaluated if lo <= r.context_relevance < hi),
                answer_relevance=sum(1 for r in evaluated if lo <= r.answer_relevance < hi),
            )
        )

    return AnalyticsOverview(
        window_days=days,
        totals=totals,
        latency=latency,
        quality=quality,
        timeseries=timeseries,
        failed_checks=failed_checks,
        top_documents=[CountItem(name=name, count=n) for name, n in top_docs],
        score_distribution=distribution,
    )
