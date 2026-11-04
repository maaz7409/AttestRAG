from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.api import AnalyticsOverview
from app.services.analytics import build_overview

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverview)
async def overview(
    days: int = Query(14, ge=1, le=90), session: AsyncSession = Depends(get_session)
) -> AnalyticsOverview:
    """Everything the analytics dashboard needs, in a single round-trip."""
    return await build_overview(session, days)
