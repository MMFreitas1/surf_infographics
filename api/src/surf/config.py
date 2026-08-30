"""Runtime configuration. Secrets come from the environment only."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, populated from environment variables or a local .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_host: str = Field(default="127.0.0.1", alias="SURF_API_HOST")
    api_port: int = Field(default=8000, alias="SURF_API_PORT")
    log_level: str = Field(default="INFO", alias="SURF_LOG_LEVEL")
    data_dir: Path = Field(default=Path("./data"), alias="SURF_DATA_DIR")

    error_buffer_size: int = Field(default=200, alias="SURF_ERROR_BUFFER_SIZE")
    """How many recent errors the /diagnostics endpoint keeps in memory."""

    llm_enabled: bool = Field(default=False, alias="SURF_LLM_ENABLED")
    llm_model: str = Field(default="qwen2.5:7b-instruct-q4_K_M", alias="SURF_LLM_MODEL")
    llm_host: str = Field(default="http://127.0.0.1:11434", alias="SURF_LLM_HOST")
    llm_idle_ttl_seconds: float = Field(default=600.0, alias="SURF_LLM_IDLE_TTL_SECONDS")

    @property
    def cache_dir(self) -> Path:
        """Directory holding cached pipeline stage outputs."""
        return self.data_dir / "cache"

    @property
    def log_dir(self) -> Path:
        """Directory holding JSONL logs, readable by a person or an agent."""
        return self.data_dir / "logs"

    @property
    def log_file(self) -> Path:
        """Append-only structured log for the API process."""
        return self.log_dir / "api.jsonl"


def get_settings() -> Settings:
    """Build settings from the current environment."""
    return Settings()
