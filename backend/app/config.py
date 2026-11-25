"""Application configuration loaded from environment variables."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _repository_env_file() -> Path | None:
    env_file = PROJECT_ROOT / ".env"
    return env_file if env_file.is_file() else None


class Settings(BaseSettings):
    """Central configuration for the backend application."""

    model_config = SettingsConfigDict(
        env_file=_repository_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    primary_model: str = Field(
        default="gemini-3.8-flash", validation_alias="PRIMARY_MODEL"
    )
    fallback_model: str = Field(
        default="gemini-3.5-flash-lite", validation_alias="FALLBACK_MODEL"
    )
    embedding_model: str = Field(
        default="models/gemini-embedding-001", validation_alias="EMBEDDING_MODEL"
    )

    langchain_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
    )
    langchain_tracing_v2: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "LANGSMITH_TRACING",
            "LANGCHAIN_TRACING_V2",
        ),
    )
    langchain_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        validation_alias=AliasChoices("LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT"),
    )
    langchain_project: str = Field(
        default="ai-powered-procurement",
        validation_alias=AliasChoices("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT"),
    )

    fastapi_host: str = Field(default="0.0.0.0", validation_alias="FASTAPI_HOST")
    fastapi_port: int = Field(default=8000, validation_alias="FASTAPI_PORT")
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        validation_alias="CORS_ORIGINS",
    )

    langgraph_checkpoint_db_path: str = Field(
        default="./backend/data/langgraph_checkpoints.sqlite",
        validation_alias="LANGGRAPH_CHECKPOINT_DB_PATH",
    )
    recursion_limit: int = Field(default=8, validation_alias="RECURSION_LIMIT")

    erp_database_path: str = Field(
        default="./backend/data/erp_database.sqlite",
        validation_alias="ERP_DATABASE_PATH",
    )
    erp_database_url: str = Field(
        default="sqlite:///./backend/data/erp_database.sqlite",
        validation_alias="ERP_DATABASE_URL",
    )

    qdrant_url: str = Field(
        default="http://localhost:6333", validation_alias="QDRANT_URL"
    )
    qdrant_api_key: str = Field(default="", validation_alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(
        default="procurement_policies", validation_alias="QDRANT_COLLECTION"
    )

    hitl_approval_threshold: float = Field(
        default=500.0, validation_alias="HITL_APPROVAL_THRESHOLD"
    )
    rag_top_k: int = Field(default=5, validation_alias="RAG_TOP_K")
    rag_min_confidence: float = Field(
        default=0.72, validation_alias="RAG_MIN_CONFIDENCE"
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if value is None:
            return ["http://localhost:5173"]
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        return [str(value)]

    @field_validator(
        "fastapi_port",
        "recursion_limit",
        "rag_top_k",
        mode="after",
    )
    @classmethod
    def validate_positive_integers(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @field_validator("hitl_approval_threshold", "rag_min_confidence")
    @classmethod
    def validate_non_negative_or_confidence(cls, value: float, info: Any) -> float:
        if value < 0:
            raise ValueError("must be non-negative")
        if info.field_name == "rag_min_confidence" and value > 1:
            raise ValueError("must be between 0 and 1")
        return value

    def _resolve_repo_path(self, raw_path: str) -> Path:
        path = Path(raw_path.strip())
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    def checkpoint_db_path(self) -> Path:
        """Return the checkpoint database path as an absolute path."""
        return self._resolve_repo_path(self.langgraph_checkpoint_db_path)

    def erp_db_path(self) -> Path:
        """Return the ERP database path as an absolute path."""
        return self._resolve_repo_path(self.erp_database_path)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


def configure_langsmith(settings: Settings) -> bool:
    """Configure LangChain/LangSmith tracing environment variables."""
    tracing_enabled = bool(settings.langchain_api_key and settings.langchain_tracing_v2)

    os.environ["LANGSMITH_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGSMITH_TRACING"] = str(tracing_enabled).lower()
    os.environ["LANGCHAIN_TRACING_V2"] = str(tracing_enabled).lower()

    if settings.langchain_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = settings.langchain_endpoint
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint
    if settings.langchain_project:
        os.environ["LANGSMITH_PROJECT"] = settings.langchain_project
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project

    return tracing_enabled


# Shared import used by application modules.
settings = get_settings()