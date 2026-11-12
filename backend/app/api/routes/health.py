from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_services
from app.services.container import Services

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe: the process is up and serving requests."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(response: Response, services: Services = Depends(get_services)) -> dict:
    """Readiness probe: PostgreSQL and Qdrant are reachable."""
    checks = await services.check_health()
    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if healthy else "degraded",
        "checks": checks,
        "provider": services.settings.llm_provider,
        "embedding_provider": services.settings.resolved_embedding_provider,
        "guardrail_mode": services.settings.guardrail_mode,
        "judge_enabled": services.settings.judge_enabled,
        "indexed_chunks": len(services.bm25),
    }
