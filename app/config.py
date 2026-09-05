"""Konfigurasi layanan, dibaca sekali dari lingkungan."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Seluruh tombol yang bisa diputar tanpa mengubah kode."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai_service_token: str = ""
    llm_provider: str = "template"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    llm_fallback_models: str = ""
    llm_timeout_ms: int = 2000
    solver_time_limit_ms: int = 1000
    monte_carlo_draws: int = 2000
    log_level: str = "INFO"


settings = Settings()
