import pytest
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import Settings
from app.services.providers import HashingEmbeddings, build_chat_model, build_embeddings


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


@pytest.mark.parametrize(
    ("llm_provider", "embedding_provider", "expected"),
    [
        ("fake", None, "local"),
        ("openai", None, "openai"),
        ("groq", None, "local"),
        ("groq", "openai", "openai"),
        ("openai", "local", "local"),
        ("fake", "openai", "openai"),
    ],
)
def test_embedding_provider_resolution(llm_provider, embedding_provider, expected):
    settings = make_settings(
        llm_provider=llm_provider, embedding_provider=embedding_provider, groq_api_key="gsk-test"
    )
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


def test_groq_chat_model_uses_groq_endpoint_and_key():
    settings = make_settings(
        llm_provider="groq", groq_api_key="gsk-test", openai_api_key="sk-unused"
    )
    llm = build_chat_model(settings, "openai/gpt-oss-20b")
    assert isinstance(llm, ChatOpenAI)
    assert llm.openai_api_base == "https://api.groq.com/openai/v1"
    assert llm.openai_api_key.get_secret_value() == "gsk-test"
    assert llm.model_name == "openai/gpt-oss-20b"


def test_openai_chat_model_ignores_groq_settings():
    settings = make_settings(
        llm_provider="openai", openai_api_key="sk-test", groq_api_key="gsk-unused"
    )
    llm = build_chat_model(settings, "gpt-4o-mini")
    assert llm.openai_api_base is None
    assert llm.openai_api_key.get_secret_value() == "sk-test"


def test_groq_defaults_to_groq_hosted_models():
    settings = make_settings(llm_provider="groq", groq_api_key="gsk-test")
    assert settings.chat_model == "openai/gpt-oss-20b"
    assert settings.judge_model == "openai/gpt-oss-20b"


def test_groq_keeps_explicitly_configured_models():
    settings = make_settings(
        llm_provider="groq", groq_api_key="gsk-test", chat_model="llama-3.3-70b-versatile"
    )
    assert settings.chat_model == "llama-3.3-70b-versatile"
    assert settings.judge_model == "openai/gpt-oss-20b"


def test_groq_model_defaults_apply_to_env_settings(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("JUDGE_MODEL", "openai/gpt-oss-120b")
    settings = Settings(_env_file=None)
    assert settings.chat_model == "openai/gpt-oss-20b"
    assert settings.judge_model == "openai/gpt-oss-120b"


def test_openai_model_defaults_unchanged():
    assert make_settings(llm_provider="openai").chat_model == "gpt-4o-mini"


def test_groq_requires_api_key():
    with pytest.raises(ValueError, match="GROQ_API_KEY is required"):
        make_settings(llm_provider="groq", groq_api_key=None)
