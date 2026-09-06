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
    llm_max_tokens: int = 400
    # Lapis tujuan: satu panggilan pendek yang mendahului solver, jadi
    # anggarannya lebih ketat daripada narasi. Sembilan bobot muat di
    # bawah 60 token; sisanya kelonggaran.
    llm_intent_timeout_ms: int = 1500
    llm_intent_max_tokens: int = 120
    # Anggaran seluruh permintaan, dan ia lebih kecil dari 3,5 detik milik
    # Go dengan sengaja: yang tersisa adalah jaring untuk jaringan dan
    # serialisasi. Narasi mendapat sisa anggaran ini, bukan jatah tetap.
    request_budget_ms: int = 3000
    solver_time_limit_ms: int = 1000
    monte_carlo_draws: int = 2000
    log_level: str = "INFO"


settings = Settings()
