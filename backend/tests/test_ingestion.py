import pytest

from app.services.ingestion import IngestionError, PageText, chunk_pages, parse_pdf
from tests.conftest import HANDBOOK_PAGES, make_pdf


def test_parse_pdf_extracts_pages():
    pages = parse_pdf(make_pdf(HANDBOOK_PAGES))
    assert [p.page_number for p in pages] == [1, 2, 3]
    assert "25 days of paid vacation" in pages[0].text
    assert "EXP-4471" in pages[1].text


def test_parse_pdf_rejects_garbage():
    with pytest.raises(IngestionError):
        parse_pdf(b"%PDF-1.4 definitely not a pdf")


def test_chunks_never_span_pages():
    long_page = " ".join(f"Sentence number {i} talks about retention." for i in range(120))
    pages = [PageText(1, long_page), PageText(2, ""), PageText(3, "Short final page text here.")]
    chunks = chunk_pages(pages, chunk_size=300, chunk_overlap=50)

    assert len(chunks) > 5
    assert all(len(c.content) <= 300 for c in chunks)
    assert {c.page_number for c in chunks} == {1, 3}
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_tiny_fragments_are_dropped():
    assert chunk_pages([PageText(1, "12")], chunk_size=300, chunk_overlap=0) == []
