"""Grounded answer generation with inline numeric citations."""

import asyncio
import re
from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.services.text import tokenize
from app.services.types import RetrievedChunk

NO_ANSWER = "I couldn't find information about that in the uploaded documents."

SYSTEM_PROMPT = """You are SmartRAG, an enterprise document assistant.

Answer the user's question using ONLY the numbered context passages provided.
Rules:
- Every factual sentence must end with a citation to the passage(s) that support it,
  written as [1] or [1][3]. Never cite a passage number that does not exist.
- If the passages do not contain the answer, reply exactly: "{no_answer}"
- Do not use outside knowledge, do not speculate, and do not invent numbers or names.
- Be concise and well structured. Use short paragraphs or bullet points when helpful.
"""

_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def format_context(chunks: Sequence[RetrievedChunk]) -> str:
    blocks = []
    for i, item in enumerate(chunks, start=1):
        c = item.chunk
        blocks.append(f"[{i}] (source: {c.filename}, page {c.page_number})\n{c.content}")
    return "\n\n".join(blocks)


def extract_citations(answer: str, max_index: int) -> set[int]:
    """Return the 1-based passage numbers cited in ``answer`` (ignoring invalid ones)."""
    cited: set[int] = set()
    for group in _CITATION_RE.findall(answer):
        for number in group.split(","):
            n = int(number)
            if 1 <= n <= max_index:
                cited.add(n)
    return cited


def to_history(turns: Sequence[tuple[str, str]], max_turns: int = 6) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for role, content in list(turns)[-max_turns:]:
        messages.append(HumanMessage(content) if role == "user" else AIMessage(content))
    return messages


class AnswerGenerator(Protocol):
    model_name: str

    def astream(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
        history: Sequence[BaseMessage] = (),
    ) -> AsyncIterator[str]: ...


class LLMAnswerGenerator:
    """LangChain chain: prompt | chat model, streamed token by token."""

    def __init__(self, llm: BaseChatModel, model_name: str) -> None:
        self.model_name = model_name
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                MessagesPlaceholder("history"),
                ("human", "Context passages:\n\n{context}\n\nQuestion: {question}"),
            ]
        ).partial(no_answer=NO_ANSWER)
        self.chain = prompt | llm

    async def astream(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
        history: Sequence[BaseMessage] = (),
    ) -> AsyncIterator[str]:
        inputs = {"context": format_context(chunks), "question": question, "history": list(history)}
        async for message_chunk in self.chain.astream(inputs):
            if isinstance(message_chunk.content, str) and message_chunk.content:
                yield message_chunk.content


class ExtractiveAnswerGenerator:
    """Offline generator: stitches together the most relevant source sentences.

    Used with ``LLM_PROVIDER=fake``. It is genuinely grounded (every sentence is
    copied from a passage and cited), so the judge and the UI behave realistically.
    """

    model_name = "extractive-offline"

    def __init__(self, max_sentences: int = 3, token_delay: float = 0.01) -> None:
        self.max_sentences = max_sentences
        self.token_delay = token_delay

    def compose(self, question: str, chunks: Sequence[RetrievedChunk]) -> str:
        q_terms = set(tokenize(question))
        scored: list[tuple[float, int, str]] = []
        for i, item in enumerate(chunks, start=1):
            sentences = _SENTENCE_RE.split(item.chunk.content.replace("\n", " "))
            for pos, sentence in enumerate(sentences):
                terms = set(tokenize(sentence))
                overlap = len(q_terms & terms)
                if not overlap:
                    continue
                score = overlap / (len(terms) ** 0.5)
                if len(terms) < 6 and pos > 0:  # very short hit: keep the lead-in sentence
                    sentence = f"{sentences[pos - 1].strip()} {sentence.strip()}"
                scored.append((score, i, sentence.strip()))
        if not scored:
            return NO_ANSWER
        scored.sort(key=lambda s: s[0], reverse=True)
        picked, seen = [], set()
        for _, idx, sentence in scored:
            if sentence in seen:
                continue
            seen.add(sentence)
            body, end = sentence.rstrip(), "."
            if body[-1:] in ".!?":
                body, end = body[:-1], body[-1]
            picked.append(f"{body} [{idx}]{end}")
            if len(picked) >= self.max_sentences:
                break
        return " ".join(picked)

    async def astream(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
        history: Sequence[BaseMessage] = (),
    ) -> AsyncIterator[str]:
        answer = self.compose(question, chunks)
        for i, word in enumerate(answer.split(" ")):
            yield word if i == 0 else f" {word}"
            if self.token_delay:
                await asyncio.sleep(self.token_delay)
