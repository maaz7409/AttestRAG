"""Model provider factory.

``LLM_PROVIDER=openai`` wires real OpenAI models through LangChain.
``LLM_PROVIDER=fake`` swaps in deterministic local components so the whole
stack runs without network access or an API key (development, demos, CI).
"""

import hashlib
import math
from collections import Counter

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import Settings
from app.services.text import tokenize


class HashingEmbeddings(Embeddings):
    """Offline embedding model based on the feature-hashing trick.

    Unigrams and bigrams are hashed into a fixed-size vector with a signed hash,
    weighted with sub-linear term frequency and L2-normalised. It is *lexical*
    rather than truly semantic, but cosine similarity behaves sensibly, which
    makes it a good stand-in for ``text-embedding-3-small`` when offline.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _features(self, text: str) -> Counter[str]:
        tokens = tokenize(text)
        feats: Counter[str] = Counter(tokens)
        feats.update(f"{a} {b}" for a, b in zip(tokens, tokens[1:], strict=False))
        return feats

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for feature, count in self._features(text).items():
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def build_embeddings(settings: Settings) -> Embeddings:
    if settings.resolved_embedding_provider == "local":
        return HashingEmbeddings(dim=settings.vector_size)

    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=settings.embedding_model,
        dimensions=settings.embedding_dim,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        chunk_size=settings.embedding_batch_size,
    )


def build_chat_model(settings: Settings, model: str, *, streaming: bool = True) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        temperature=settings.llm_temperature,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        streaming=streaming,
        max_retries=2,
        timeout=60,
    )
