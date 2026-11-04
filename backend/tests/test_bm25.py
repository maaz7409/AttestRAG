import uuid

from app.services.bm25 import BM25Index
from tests.conftest import chunk


async def test_exact_identifier_ranks_first():
    index = BM25Index()
    target = chunk("Travel above 500 EUR requires pre-approval under policy code EXP-4471.")
    await index.add(
        [
            chunk("Our travel policy covers flights, hotels and per-diem allowances."),
            target,
            chunk("Expense reports are submitted through the Concur portal."),
        ]
    )
    results = index.search("what does EXP-4471 say", k=3)
    assert results[0][0].chunk_id == target.chunk_id
    assert all(score > 0 for _, score in results)


async def test_no_match_returns_empty():
    index = BM25Index()
    await index.add([chunk("alpha beta gamma")])
    assert index.search("delta", k=5) == []
    assert BM25Index().search("anything", k=5) == []


async def test_document_filter_and_removal():
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    index = BM25Index()
    await index.add([chunk("vacation policy", doc_id=doc_a), chunk("vacation days", doc_id=doc_b)])

    filtered = index.search("vacation", k=5, document_ids={doc_b})
    assert [c.document_id for c, _ in filtered] == [doc_b]

    await index.remove_document(doc_b)
    assert len(index) == 1
    assert [c.document_id for c, _ in index.search("vacation", k=5)] == [doc_a]


async def test_common_terms_keep_positive_idf():
    # Classic Okapi IDF turns negative when a term is in most documents.
    index = BM25Index()
    await index.add([chunk("policy one"), chunk("policy two"), chunk("policy three")])
    assert all(score > 0 for _, score in index.search("policy", k=3))


async def test_rebuild_replaces_contents():
    index = BM25Index()
    await index.add([chunk("old content")])
    await index.rebuild([chunk("new content")])
    assert index.search("old", k=5) == []
    assert len(index.search("new", k=5)) == 1
