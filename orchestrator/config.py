from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    active_pack: str = "dental_saas"
    log_level: str = "INFO"
    environment: str = "development"

    # Model routing
    generation_model: str = "claude-haiku-4-5-20251001"
    classifier_model: str = "claude-haiku-4-5-20251001"


settings = Settings()
