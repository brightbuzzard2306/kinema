"""Environment-driven configuration. Secrets are only ever read from the environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env"),
        extra="ignore",
    )

    anthropic_api_key: SecretStr | None = None
    anthropic_workspace_id: str | None = None  # only needed when the key is not scoped to a workspace
    claude_model: str = "claude-opus-5-5"
    claude_timeout_s: float = Field(default=30.0, gt=0)

    tmdb_api_key: SecretStr | None = None

    # comma-separated list of allowed browser origins, e.g. "https://kinema.co.in,https://www.kinema.co.in"
    frontend_origin: str = "http://localhost:3000"

    # --- deployment safeguards (all optional; unset = open, unlimited, as in local development)
    access_code: SecretStr | None = None  # when set, every API call except /health must carry it
    rate_heavy_per_min: int = Field(default=20, ge=1)  # chat / recommend / compare, per visitor
    rate_light_per_min: int = Field(default=240, ge=1)  # everything else, per visitor
    claude_daily_limit: int = 400  # Claude calls per UTC day for the whole site (0 = unlimited); then offline mode
    data_dir: Path = PROJECT_ROOT / "data"
    reports_dir: Path = PROJECT_ROOT / "reports"

    max_message_chars: int = 800
    max_results: int = 12

    @property
    def dataset_dir(self) -> Path:
        return self.data_dir / "ml-latest-small"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def origins(self) -> list[str]:
        out: list[str] = []
        for o in self.frontend_origin.split(","):
            o = o.strip().rstrip("/")
            if o:
                out += [o, o.replace("localhost", "127.0.0.1")]
        return sorted(set(out))

    @property
    def access_code_value(self) -> str | None:
        v = self.access_code.get_secret_value().strip() if self.access_code else ""
        return v or None

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value().strip())

    @property
    def tmdb_enabled(self) -> bool:
        return bool(self.tmdb_api_key and self.tmdb_api_key.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
