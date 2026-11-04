from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by Docker and the CI smoke test."""
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name, "provider": settings.llm_provider}
