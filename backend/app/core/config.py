"""Application settings, loaded from environment variables (and an optional `.env`)."""

from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Used for CHAT_MODEL and JUDGE_MODEL when LLM_PROVIDER=groq and they are unset.
GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- General -----------------------------------------------------------
    app_name: str = "Attest RAG"
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    # --- Model provider ----------------------------------------------------
    llm_provider: Literal["openai", "groq", "fake"] = "openai"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    chat_model: str = "gpt-4o-mini"
    judge_model: str = "gpt-4o-mini"
    # "openai" calls the embeddings API, "local" uses offline hashing embeddings.
    # Unset means "openai" for the openai provider and "local" otherwise
    # (Groq has no embeddings API).
    embedding_provider: Literal["openai", "local"] | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    llm_temperature: float = 0.1

    # --- Storage -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://attestrag:attestrag@localhost:5432/attestrag"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "attestrag_chunks"

    # --- Ingestion ---------------------------------------------------------
    chunk_size: int = 1000
    chunk_overlap: int = 150
    max_upload_mb: int = 25
    embedding_batch_size: int = 64

    # --- Hybrid retrieval --------------------------------------------------
    dense_top_k: int = 20
    sparse_top_k: int = 20
    final_top_k: int = 6
    rrf_k: int = 60
    dense_weight: float = 1.0
    sparse_weight: float = 1.0

    # --- LLM-as-a-Judge ----------------------------------------------------
    judge_enabled: bool = True
    guardrail_mode: Literal["stream", "strict"] = "stream"
    faithfulness_threshold: float = 0.6
    context_relevance_threshold: float = 0.4
    toxicity_threshold: float = 0.5

    @model_validator(mode="after")
    def _apply_groq_model_defaults(self) -> Self:
        if self.llm_provider == "groq":
            for field in ("chat_model", "judge_model"):
                if field not in self.model_fields_set:
                    setattr(self, field, GROQ_DEFAULT_MODEL)
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def resolved_embedding_provider(self) -> Literal["openai", "local"]:
        if self.embedding_provider is not None:
            return self.embedding_provider
        return "openai" if self.llm_provider == "openai" else "local"

    @property
    def vector_size(self) -> int:
        """Dimensionality of the dense vectors stored in Qdrant."""
        return self.embedding_dim if self.resolved_embedding_provider == "openai" else 384


@lru_cache
def get_settings() -> Settings:
    return Settings()
