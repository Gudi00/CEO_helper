from functools import lru_cache
from pathlib import Path
from secrets import token_urlsafe

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_timeout_s: float = 10.0

    ollama_enabled: bool = False
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"

    backend_host: str = "127.0.0.1"
    backend_port: int = 8765
    backend_token: str = ""

    database_url: str = "sqlite+aiosqlite:///./quiz.db"

    cdp_port: int = 9222

    log_level: str = "INFO"
    log_events: bool = True

    token_file: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "lms-tool" / "token"
    )

    @field_validator(
        "gemini_api_key", "backend_token", "ollama_host", "ollama_model",
        "gemini_model", "backend_host", mode="before",
    )
    @classmethod
    def _strip_inline_comment(cls, v: object) -> object:
        """pydantic-settings doesn't strip `KEY=value # comment` — we do
        it ourselves so a stray inline comment doesn't become the token.
        """
        if isinstance(v, str):
            cleaned = v.split("#", 1)[0].strip()
            return cleaned
        return v

    def ensure_token(self) -> str:
        if self.backend_token:
            return self.backend_token
        if self.token_file.exists():
            return self.token_file.read_text().strip()
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        token = token_urlsafe(32)
        self.token_file.write_text(token)
        self.token_file.chmod(0o600)
        return token


@lru_cache
def get_settings() -> Settings:
    return Settings()
