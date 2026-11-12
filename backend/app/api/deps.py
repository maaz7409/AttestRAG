from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.container import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with get_services(request).db.sessionmaker() as session:
        yield session
