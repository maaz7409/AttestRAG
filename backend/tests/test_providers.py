import pytest
from langchain_openai import OpenAIEmbeddings

from app.core.config import Settings
from app.services.providers import HashingEmbeddings, build_embeddings


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


@pytest.mark.parametrize(
    ("llm_provider", "embedding_provider", "expected"),
    [
        ("fake", None, "local"),
        ("openai", None, "openai"),
        ("openai", "local", "local"),
        ("fake", "openai", "openai"),
    ],
)
def test_embedding_provider_resolution(llm_provider, embedding_provider, expected):
    settings = make_settings(llm_provider=llm_provider, embedding_provider=embedding_provider)
    assert settings.resolved_embedding_provider == expected


def test_local_embeddings_use_hashing_vectors():
    settings = make_settings(llm_provider="openai", embedding_provider="local")
    embeddings = build_embeddings(settings)
    assert isinstance(embeddings, HashingEmbeddings)
    assert settings.vector_size == 384
    assert len(embeddings.embed_query("vacation policy")) == 384


def test_openai_embeddings_use_configured_dimensions():
    settings = make_settings(llm_provider="openai", openai_api_key="sk-test", embedding_dim=512)
    assert isinstance(build_embeddings(settings), OpenAIEmbeddings)
    assert settings.vector_size == 512
