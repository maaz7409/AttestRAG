import asyncio
import io
import os
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient
from reportlab.pdfgen import canvas
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.main import create_app
from app.services.container import build_services
from app.services.types import IndexedChunk, RetrievedChunk

HANDBOOK_PAGES = [
    "The annual leave policy grants every full-time employee 25 days of paid vacation per "
    "year. Unused vacation days may be carried over until the end of March.",
    "Expense reports must be submitted within 30 days through the Concur portal. "
    "Travel expenses above 500 EUR require pre-approval under policy code EXP-4471.",
    "Remote work is permitted up to three days per week with manager approval. "
    "Employees must be reachable during core hours between 10:00 and 15:00 CET.",
]


def make_pdf(pages: list[str]) -> bytes:
    """Build a small text PDF in memory (``invariant`` makes output byte-stable)."""
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, invariant=1)
    for page in pages:
        text_obj = pdf.beginText(60, 760)
        words, line = page.split(), ""
        for word in words:
            if len(line) + len(word) > 85:
                text_obj.textLine(line)
                line = ""
            line += word + " "
        text_obj.textLine(line)
        pdf.drawText(text_obj)
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


@pytest.fixture
def pdf_factory() -> Callable[[list[str]], bytes]:
    return make_pdf


@pytest.fixture
def handbook_pdf() -> bytes:
    return make_pdf(HANDBOOK_PAGES)


def _reset_postgres(url: str) -> None:
    """Give every test a pristine schema on the CI PostgreSQL service."""

    async def reset() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())


@pytest.fixture
def settings(tmp_path) -> Settings:
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        _reset_postgres(url)
    else:
        url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    return Settings(
        _env_file=None,
        llm_provider="fake",
        database_url=url,
        qdrant_collection=f"test_{uuid.uuid4().hex[:8]}",
        guardrail_mode="stream",
        judge_enabled=True,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, lambda s: build_services(s, AsyncQdrantClient(":memory:")))
    with TestClient(app) as test_client:
        yield test_client


def chunk(content: str, page: int = 1, filename: str = "doc.pdf", doc_id=None) -> IndexedChunk:
    return IndexedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id or uuid.uuid4(),
        filename=filename,
        page_number=page,
        chunk_index=0,
        content=content,
    )


def retrieved(content: str, page: int = 1) -> RetrievedChunk:
    return RetrievedChunk(chunk=chunk(content, page), fused_score=0.03)
