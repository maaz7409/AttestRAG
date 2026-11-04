from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.schemas.judge import JudgeVerdict
from app.services.generation import NO_ANSWER
from app.services.judge import (
    EvaluationService,
    HeuristicJudge,
    JudgeResult,
    LLMJudge,
    Thresholds,
    apply_thresholds,
)
from tests.conftest import retrieved

CONTEXT = [retrieved("Employees get 25 days of paid vacation per year.")]
QUESTION = "How many vacation days do employees get?"


def verdict(**scores) -> JudgeVerdict:
    base = dict(faithfulness=1.0, context_relevance=1.0, answer_relevance=1.0, toxicity=0.0)
    base.update(scores)
    return JudgeVerdict(
        faithfulness_reasoning="", relevance_reasoning="", toxicity_reasoning="", **base
    )


def test_thresholds_and_blocking_policy():
    t = Thresholds(faithfulness=0.6, context_relevance=0.4, toxicity=0.5)
    assert apply_thresholds(verdict(), t) == []

    low_relevance = JudgeResult(
        verdict(), "j", 1.0, apply_thresholds(verdict(context_relevance=0.1), t)
    )
    assert low_relevance.failed_checks == ["context_relevance"]
    assert not low_relevance.passed and not low_relevance.blocked  # warn, don't block

    hallucination = apply_thresholds(verdict(faithfulness=0.3), t)
    toxic = apply_thresholds(verdict(toxicity=0.5), t)
    assert JudgeResult(verdict(), "j", 1.0, hallucination).blocked
    assert JudgeResult(verdict(), "j", 1.0, toxic).blocked


async def test_heuristic_judge_scores_grounded_answer_highly():
    v = await HeuristicJudge().grade(
        QUESTION, "Employees get 25 days of paid vacation [1].", CONTEXT
    )
    assert v.faithfulness == 1.0 and v.toxicity == 0.0 and v.context_relevance > 0.5


async def test_heuristic_judge_flags_hallucination_and_toxicity():
    judge = HeuristicJudge()
    fabricated = await judge.grade(QUESTION, "The CEO owns a yacht in Monaco.", CONTEXT)
    assert fabricated.faithfulness == 0.0
    assert fabricated.unsupported_claims == ["The CEO owns a yacht in Monaco."]

    rude = await judge.grade(
        QUESTION, "Stupid question, idiot. Employees get 25 days [1].", CONTEXT
    )
    assert rude.toxicity >= 0.5


async def test_refusal_counts_as_faithful():
    v = await HeuristicJudge().grade(QUESTION, NO_ANSWER, CONTEXT)
    assert v.faithfulness == 1.0


class StructuredFakeChatModel(FakeListChatModel):
    """Fake chat model whose structured output parses the canned JSON response."""

    def with_structured_output(self, schema, **kwargs):  # type: ignore[override]
        return self | (lambda message: schema.model_validate_json(message.content))


async def test_llm_judge_returns_validated_structured_output():
    payload = verdict(faithfulness=0.25, toxicity=0.1).model_dump_json()
    judge = LLMJudge(StructuredFakeChatModel(responses=[payload]), "judge-model")
    service = EvaluationService(judge, Thresholds())

    result = await service.evaluate(QUESTION, "Employees get 40 days.", CONTEXT)
    assert isinstance(result.verdict, JudgeVerdict)
    assert result.verdict.faithfulness == 0.25
    assert result.judge_model == "judge-model"
    assert result.failed_checks == ["faithfulness"] and result.blocked
    assert result.latency_ms >= 0
