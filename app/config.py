from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    request_timeout_seconds: float = 20
    max_download_bytes: int = 5_000_000
    max_llm_input_chars: int = 60_000
    enable_browser_fallback: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

