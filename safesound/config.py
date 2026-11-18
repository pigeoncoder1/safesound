import logging
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("safesound.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: Literal["anthropic", "ollama", "none"] = "none"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-5-5"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    whisper_model: str = "base.en"

    match_threshold: float = 0.55
    min_chunk_seconds: float = 1.5
    unknown_chunks_to_flip: int = 2
    room_cooldown_seconds: int = 180

    host: str = "127.0.0.1"
    port: int = 8000

    def resolved_llm_provider(self) -> str:
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            log.warning("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty; using rule-based mode.")
            return "none"
        return self.llm_provider


settings = Settings()
