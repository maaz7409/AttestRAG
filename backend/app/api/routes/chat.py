import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_services
from app.schemas.api import ChatRequest, ChatResponse
from app.services.container import Services

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(request: ChatRequest, services: Services = Depends(get_services)):
    """Answer a question as a Server-Sent Events stream.

    Events: ``start``, ``sources``, ``token``, ``evaluation``, ``blocked``, ``done``, ``error``.
    Each SSE message is ``event: <type>`` followed by ``data: <json>``.
    """

    async def event_source() -> AsyncIterator[str]:
        async for event in services.pipeline.stream(request):
            yield f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, services: Services = Depends(get_services)) -> dict:
    """Non-streaming variant for API clients, scripts and integrations."""
    try:
        return await services.pipeline.run(request)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
