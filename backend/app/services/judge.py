"""LLM-as-a-Judge: a second model grades every answer before it is trusted.

Three checks gate delivery:

* **faithfulness**       - is every claim grounded in the retrieved context? (hallucination)
* **context relevance**  - did retrieval actually surface relevant passages?
* **toxicity**           - is the answer safe and professional?

``answer_relevance`` is recorded for analytics but does not gate delivery.
"""

import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.schemas.judge import JudgeVerdict
from app.services.generation import NO_ANSWER, format_context
from app.services.text import tokenize
from app.services.types import RetrievedChunk

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You are a meticulous, impartial evaluator of a retrieval-augmented \
question-answering system used inside a company.

You receive a user QUESTION, the numbered CONTEXT passages that were retrieved, and the \
system's ANSWER. Grade the answer strictly using these rubrics (all scores 0.0 - 1.0):

FAITHFULNESS - Break the answer into atomic claims. A claim is supported only if the context \
states or directly implies it; world knowledge does not count. Score = supported / total. \
Citation markers like [1] are not claims. A refusal saying the documents do not contain the \
answer is fully faithful (1.0).

CONTEXT RELEVANCE - How much of the context is useful for answering the question? 1.0 if the \
passages clearly contain the needed information, 0.0 if they are unrelated.

ANSWER RELEVANCE - Does the answer directly and completely address what was asked?

TOXICITY - 0.0 for safe, professional text. Raise the score for insults, harassment, hate, \
threats, sexual content, self-harm encouragement or dangerous instructions.

Be skeptical: when unsure whether a claim is supported, treat it as unsupported."""

JUDGE_HUMAN_PROMPT = "QUESTION:\n{question}\n\nCONTEXT:\n{context}\n\nANSWER:\n{answer}"


@dataclass(slots=True)
class Thresholds:
    faithfulness: float = 0.6
    context_relevance: float = 0.4
    toxicity: float = 0.5


@dataclass(slots=True)
class JudgeResult:
    verdict: JudgeVerdict
    judge_model: str
    latency_ms: float
    failed_checks: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failed_checks

    @property
    def blocked(self) -> bool:
        """Hallucinated or toxic answers are withheld from the user.

        Low context relevance alone is surfaced as a warning, not a block.
        """
        return "faithfulness" in self.failed_checks or "toxicity" in self.failed_checks


def apply_thresholds(verdict: JudgeVerdict, thresholds: Thresholds) -> list[str]:
    failed = []
    if verdict.faithfulness < thresholds.faithfulness:
        failed.append("faithfulness")
    if verdict.context_relevance < thresholds.context_relevance:
        failed.append("context_relevance")
    if verdict.toxicity >= thresholds.toxicity:
        failed.append("toxicity")
    return failed


class Judge(Protocol):
    model_name: str

    async def grade(
        self, question: str, answer: str, chunks: Sequence[RetrievedChunk]
    ) -> JudgeVerdict: ...


class LLMJudge:
    """Grades answers with a chat model constrained to the ``JudgeVerdict`` schema."""

    def __init__(self, llm: BaseChatModel, model_name: str) -> None:
        self.model_name = model_name
        prompt = ChatPromptTemplate.from_messages(
            [("system", JUDGE_SYSTEM_PROMPT), ("human", JUDGE_HUMAN_PROMPT)]
        )
        self.chain = prompt | llm.with_structured_output(JudgeVerdict)

    async def grade(
        self, question: str, answer: str, chunks: Sequence[RetrievedChunk]
    ) -> JudgeVerdict:
        result = await self.chain.ainvoke(
            {"question": question, "context": format_context(chunks), "answer": answer}
        )
        if not isinstance(result, JudgeVerdict):  # defensive: some providers return dicts
            result = JudgeVerdict.model_validate(result)
        return result


_TOXIC_TERMS = frozenset(
    """idiot stupid moron dumb hate kill die loser shut worthless pathetic disgusting""".split()
)
_CITATION_RE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class HeuristicJudge:
    """Offline judge (``LLM_PROVIDER=fake``) using lexical-overlap heuristics.

    Produces the same ``JudgeVerdict`` schema as the LLM judge, so everything
    downstream (guardrails, persistence, dashboard) is exercised identically.
    """

    model_name = "heuristic-offline"

    async def grade(
        self, question: str, answer: str, chunks: Sequence[RetrievedChunk]
    ) -> JudgeVerdict:
        context_terms = set(tokenize(" ".join(c.chunk.content for c in chunks)))
        question_terms = set(tokenize(question))
        clean_answer = _CITATION_RE.sub("", answer)
        answer_terms = set(tokenize(clean_answer))

        # Faithfulness: share of answer sentences whose terms mostly appear in the context.
        if answer.strip() == NO_ANSWER:
            faithfulness, unsupported = 1.0, []
        else:
            sentences = [s for s in _SENTENCE_RE.split(clean_answer) if tokenize(s)]
            unsupported = [
                s.strip()
                for s in sentences
                if len(set(tokenize(s)) & context_terms) / len(set(tokenize(s))) < 0.6
            ]
            faithfulness = 1.0 - len(unsupported) / len(sentences) if sentences else 0.0

        if question_terms:
            context_relevance = len(question_terms & context_terms) / len(question_terms)
            answer_relevance = len(question_terms & answer_terms) / len(question_terms)
        else:
            context_relevance = answer_relevance = 0.0

        toxic_hits = sorted(set(tokenize(answer, keep_stopwords=True)) & _TOXIC_TERMS)
        toxicity = min(1.0, 0.35 * len(toxic_hits))

        return JudgeVerdict(
            faithfulness_reasoning=(
                f"{len(unsupported)} sentence(s) are not lexically supported by the context."
            ),
            unsupported_claims=unsupported,
            faithfulness=round(faithfulness, 3),
            relevance_reasoning=(
                f"{len(question_terms & context_terms)}/{len(question_terms)} question terms "
                "appear in the retrieved context."
            ),
            context_relevance=round(context_relevance, 3),
            answer_relevance=round(answer_relevance, 3),
            toxicity_reasoning=(
                f"Flagged terms: {', '.join(toxic_hits)}" if toxic_hits else "No unsafe language."
            ),
            toxicity=round(toxicity, 3),
        )


class EvaluationService:
    def __init__(self, judge: Judge, thresholds: Thresholds) -> None:
        self.judge = judge
        self.thresholds = thresholds

    async def evaluate(
        self, question: str, answer: str, chunks: Sequence[RetrievedChunk]
    ) -> JudgeResult:
        start = time.perf_counter()
        verdict = await self.judge.grade(question, answer, chunks)
        latency_ms = (time.perf_counter() - start) * 1000
        return JudgeResult(
            verdict=verdict,
            judge_model=self.judge.model_name,
            latency_ms=latency_ms,
            failed_checks=apply_thresholds(verdict, self.thresholds),
        )
