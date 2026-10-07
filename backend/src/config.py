import os
import sys
from functools import lru_cache
from pathlib import Path
from secrets import token_urlsafe

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR_NAME = "lms-tool"


def user_config_dir() -> Path:
    """Per-user config directory, following each OS's convention."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Roaming") / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / APP_DIR_NAME


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files win: a project-local .env overrides the per-user one.
        env_file=(str(user_config_dir() / ".env"), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_timeout_s: float = 10.0

    # Any OpenAI-compatible endpoint: OpenRouter, DeepSeek, Groq, LM Studio,
    # llama.cpp server, vLLM. Enabled when base URL and model are both set.
    openai_base_url: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    openai_model_accurate: str = ""
    openai_timeout_s: float = 60.0

    ollama_enabled: bool = False
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"
    ollama_model_accurate: str = "deepseek-r1:7b"

    backend_host: str = "127.0.0.1"
    backend_port: int = 8765
    backend_token: str = ""
    # Host headers the server answers to (DNS-rebinding guard).
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1", "localhost", "testserver"]
    )

    # Lives next to the other per-user files so the server works the same
    # from any directory (double-click launcher, autostart).
    database_url: str = Field(
        default_factory=lambda: f"sqlite+aiosqlite:///{(user_config_dir() / 'quiz.db').as_posix()}"
    )

    cdp_port: int = 9222

    log_level: str = "INFO"
    log_events: bool = True

    token_file: Path = Field(default_factory=lambda: user_config_dir() / "token")
    # Extension origins that completed pairing, one per line.
    paired_origins_file: Path = Field(
        default_factory=lambda: user_config_dir() / "paired_origins"
    )

    @field_validator(
        "gemini_api_key", "backend_token", "ollama_host", "ollama_model",
        "gemini_model", "backend_host", "openai_base_url", "openai_api_key",
        "openai_model", "openai_model_accurate", mode="before",
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

    @property
    def openai_enabled(self) -> bool:
        return bool(self.openai_base_url and self.openai_model)

    def model_label(self, preference: str) -> str | None:
        """Name of the model that serves a preference first, for display."""
        if preference == "fast":
            if self.gemini_api_key:
                return self.gemini_model
            if self.openai_enabled:
                return self.openai_model
            return self.ollama_model if self.ollama_enabled else None
        if preference == "accurate":
            if self.openai_base_url and self.openai_model_accurate:
                return self.openai_model_accurate
            return self.ollama_model_accurate if self.ollama_enabled else None
        return None

    def paired_origins(self) -> set[str]:
        if not self.paired_origins_file.exists():
            return set()
        return set(self.paired_origins_file.read_text().split())

    def add_paired_origin(self, origin: str) -> None:
        origins = self.paired_origins() | {origin}
        self.paired_origins_file.parent.mkdir(parents=True, exist_ok=True)
        self.paired_origins_file.write_text("\n".join(sorted(origins)) + "\n")

    def ensure_token(self) -> str:
        if self.backend_token:
            return self.backend_token
        if self.token_file.exists():
            return self.token_file.read_text().strip()
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        token = token_urlsafe(32)
        # Create with 0600 from the start instead of chmod-ing afterwards.
        fd = os.open(self.token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(token)
        return token


@lru_cache
def get_settings() -> Settings:
    return Settings()
