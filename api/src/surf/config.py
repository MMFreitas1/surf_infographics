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

    wave_speed_corroboration: float = Field(
        default=0.65, alias="SURF_WAVE_SPEED_CORROBORATION", gt=0.0, le=1.0
    )
    """How much of a candidate's claimed top speed the watch's own speedometer must have
    measured before L5 will call it a wave (ADR-0023).

    **The only stage parameter that comes from the environment**, and the reason every other
    one is a field in code is this stage cache: a stage is keyed on its params, so the
    *resolved* value travels into L5's key and a verdict can never be served under a cutoff
    it was not computed under. Two ``.env`` files therefore give two cache keys and two wave
    counts, which is correct rather than a bug. The default lives in ``ClassifyStage`` so the
    repo can reproduce its own published numbers with no ``.env`` at all; this only overrides
    it. Measured safe anywhere in 0.4-0.7 on the one labelled session there is.
    """

    max_upload_bytes: int = Field(default=64 * 1024 * 1024, alias="SURF_MAX_UPLOAD_BYTES")
    """Ceiling on an ingested file. A season of surfing is a few hundred KB per session."""

    web_origins: str = Field(
        default="http://127.0.0.1:3000,http://localhost:3000", alias="SURF_WEB_ORIGINS"
    )
    """Browser origins allowed to call this API, comma separated.

    The UI runs on :3000 and the API on :8000, which are different origins, so without this
    the browser refuses every request before it is sent. It is an explicit list rather than
    ``*`` because there is no reason for anything but the local UI to be talking to a
    process that serves someone's location history (ADR-0004: localhost only)."""

    llm_enabled: bool = Field(default=False, alias="SURF_LLM_ENABLED")
    llm_model: str = Field(default="qwen2.5:7b-instruct-q4_K_M", alias="SURF_LLM_MODEL")
    llm_host: str = Field(default="http://127.0.0.1:11434", alias="SURF_LLM_HOST")
    llm_idle_ttl_seconds: float = Field(default=600.0, alias="SURF_LLM_IDLE_TTL_SECONDS")

    @property
    def allowed_origins(self) -> list[str]:
        """``web_origins`` as a list, blanks dropped."""
        return [origin.strip() for origin in self.web_origins.split(",") if origin.strip()]

    @property
    def cache_dir(self) -> Path:
        """Directory holding cached pipeline stage outputs."""
        return self.data_dir / "cache"

    @property
    def db_path(self) -> Path:
        """The single SQLite file holding activity metadata, windows and (later) labels."""
        return self.data_dir / "surf.db"

    @property
    def tile_dir(self) -> Path:
        """Basemap tiles, kept so the map works with no network (architecture.md section 7)."""
        return self.data_dir / "tiles"

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
