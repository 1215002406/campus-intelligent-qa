from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / "backend" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    admin_username: str = ""
    admin_password: SecretStr = SecretStr("")
    admin_registration_code: SecretStr = SecretStr("")
    jwt_secret_key: SecretStr = SecretStr("")
    database_url: str = ""
    upload_dir: Path = Path("uploads")
    chroma_dir: Path = Path("data/chroma")
    model_cache_dir: Path = Path("data/model_cache")
    max_upload_mb: int = Field(default=20, ge=1, le=200)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    llm_provider: Literal["local", "remote"] = "local"
    llm_local_base_url: str = "http://127.0.0.1:8080/v1"
    llm_local_api_key: SecretStr = SecretStr("local-model")
    llm_local_model: str = "data/models/qwen3.8-27b.gguf"
    llm_remote_base_url: str = ""
    llm_remote_api_key: SecretStr = SecretStr("")
    llm_remote_model: str = ""
    llm_timeout_seconds: int = Field(default=180, ge=10, le=600)
    llm_max_tokens: int = Field(default=2048, ge=64, le=16384)
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    embedding_provider: Literal["local", "remote"] = "local"
    embedding_profile: Literal["bge-small", "qwen-0.6b"] = "bge-small"
    embedding_bge_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_bge_path: Path = Path("data/models/bge-small-zh-v1.5")
    embedding_bge_dimensions: int = Field(default=512, ge=1)
    embedding_bge_query_prefix: str = "为这个句子生成表示以用于检索相关文章："
    embedding_qwen_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_qwen_path: Path = Path("data/models/Qwen3-Embedding-0.6B")
    embedding_qwen_dimensions: int = Field(default=1024, ge=1)
    embedding_qwen_query_prefix: str = (
        "Instruct: Given a campus question, retrieve relevant passages that answer the question\nQuery:"
    )
    embedding_device: Literal["auto", "cpu", "cuda"] = "auto"
    embedding_remote_base_url: str = ""
    embedding_remote_api_key: SecretStr = SecretStr("")
    embedding_remote_model: str = ""
    vector_index_enabled: bool = True
    vector_backfill_on_startup: bool = True

    @field_validator("admin_username", mode="before")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip()

    @field_validator("upload_dir", "chroma_dir", "model_cache_dir")
    @classmethod
    def resolve_directory(cls, value: Path) -> Path:
        return value.resolve() if value.is_absolute() else (PROJECT_ROOT / value).resolve()

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not value:
            return value
        url = make_url(value)
        if url.drivername != "mysql+pymysql":
            raise ValueError("DATABASE_URL must use mysql+pymysql")
        if not url.host or not url.database:
            raise ValueError("DATABASE_URL must include a MySQL host and database name")
        return value

    @property
    def active_llm_base_url(self) -> str:
        return self.llm_local_base_url if self.llm_provider == "local" else self.llm_remote_base_url

    @property
    def active_llm_model(self) -> str:
        return self.llm_local_model if self.llm_provider == "local" else self.llm_remote_model

    @property
    def active_llm_api_key(self) -> str:
        key = self.llm_local_api_key if self.llm_provider == "local" else self.llm_remote_api_key
        return key.get_secret_value()

    @property
    def active_embedding_base_url(self) -> str:
        return "" if self.embedding_provider == "local" else self.embedding_remote_base_url

    @property
    def active_embedding_model(self) -> str:
        if self.embedding_provider == "remote":
            return self.embedding_remote_model
        return self.embedding_bge_model if self.embedding_profile == "bge-small" else self.embedding_qwen_model

    @property
    def active_embedding_local_path(self) -> Path:
        return self.embedding_bge_path if self.embedding_profile == "bge-small" else self.embedding_qwen_path

    @property
    def active_embedding_dimensions(self) -> int:
        if self.embedding_provider == "remote":
            return 0
        return self.embedding_bge_dimensions if self.embedding_profile == "bge-small" else self.embedding_qwen_dimensions

    @property
    def active_embedding_query_prefix(self) -> str:
        if self.embedding_provider == "remote":
            return ""
        return (
            self.embedding_bge_query_prefix
            if self.embedding_profile == "bge-small"
            else self.embedding_qwen_query_prefix
        ).replace("\\n", "\n")

    def validate_runtime(self) -> None:
        missing = []
        for name in ("admin_username", "admin_password", "jwt_secret_key", "database_url"):
            value = getattr(self, name)
            value = value.get_secret_value() if isinstance(value, SecretStr) else value
            if not value or not value.strip():
                missing.append(name.upper())
        if missing:
            raise RuntimeError("Missing required configuration: " + ", ".join(missing))
        if len(self.admin_username) > 80:
            raise RuntimeError("Configured usernames must be no longer than 80 characters")
        if len(self.jwt_secret_key.get_secret_value().encode("utf-8")) < 32:
            raise RuntimeError("JWT_SECRET_KEY must contain at least 32 bytes")
