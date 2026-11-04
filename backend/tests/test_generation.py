from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.services.generation import (
    NO_ANSWER,
    ExtractiveAnswerGenerator,
    LLMAnswerGenerator,
    extract_citations,
    format_context,
    to_history,
)
from tests.conftest import retrieved


def test_extract_citations_handles_groups_and_ignores_invalid():
    assert extract_citations("A [1]. B [2][3]. C [1, 4]. D [9].", max_index=4) == {1, 2, 3, 4}
    assert extract_citations("no citations here", max_index=3) == set()


def test_format_context_numbers_passages_with_source():
    text = format_context([retrieved("alpha", page=3), retrieved("beta", page=7)])
    assert text.startswith("[1] (source: doc.pdf, page 3)\nalpha")
    assert "[2] (source: doc.pdf, page 7)\nbeta" in text


def test_history_is_truncated_and_typed():
    turns = [("user", f"q{i}") if i % 2 == 0 else ("assistant", f"a{i}") for i in range(10)]
    history = to_history(turns, max_turns=4)
    assert [m.content for m in history] == ["q6", "a7", "q8", "a9"]
    assert history[-1].type == "ai"


async def test_llm_generator_streams_tokens():
    llm = GenericFakeChatModel(messages=iter([AIMessage("Employees get 25 days [1].")]))
    generator = LLMAnswerGenerator(llm, "fake-model")
    tokens = [t async for t in generator.astream("vacation?", [retrieved("25 days")])]
    assert len(tokens) > 1
    assert "".join(tokens) == "Employees get 25 days [1]."


async def test_extractive_generator_is_grounded_and_cited():
    generator = ExtractiveAnswerGenerator(token_delay=0)
    chunks = [retrieved("Offices close at 18:00."), retrieved("Employees get 25 vacation days.")]
    answer = "".join([t async for t in generator.astream("how many vacation days", chunks)])
    assert answer.startswith("Employees get 25 vacation days [2]")


async def test_extractive_generator_refuses_without_overlap():
    generator = ExtractiveAnswerGenerator(token_delay=0)
    answer = "".join(
        [t async for t in generator.astream("quantum chromodynamics", [retrieved("x y z")])]
    )
    assert answer == NO_ANSWER
