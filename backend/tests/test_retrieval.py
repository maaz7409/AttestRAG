from app.services.analytics import percentile
from app.services.retrieval import reciprocal_rank_fusion
from tests.conftest import chunk


def test_rrf_rewards_agreement_between_retrievers():
    a, b, c = chunk("a"), chunk("b"), chunk("c")
    fused = reciprocal_rank_fusion([(a, 0.9), (b, 0.8)], [(c, 9.0), (a, 4.0)], k=60, top_n=3)

    assert fused[0].chunk_id == a.chunk_id  # found by both retrievers
    assert (fused[0].dense_rank, fused[0].sparse_rank) == (1, 2)
    assert fused[0].fused_score == 1 / 61 + 1 / 62
    assert {r.chunk_id for r in fused} == {a.chunk_id, b.chunk_id, c.chunk_id}


def test_rrf_weights_and_top_n():
    a, b = chunk("a"), chunk("b")
    fused = reciprocal_rank_fusion([(a, 0.9)], [(b, 5.0)], dense_weight=0.2, top_n=1)
    assert len(fused) == 1
    assert fused[0].chunk_id == b.chunk_id
    assert fused[0].dense_score is None and fused[0].sparse_score == 5.0


def test_rrf_handles_empty_inputs():
    assert reciprocal_rank_fusion([], []) == []


def test_percentile_matches_linear_interpolation():
    assert percentile([], 0.5) is None
    assert percentile([10.0], 0.95) == 10.0
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile(list(range(1, 101)), 0.95) == 95.05
