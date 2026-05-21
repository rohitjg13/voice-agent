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

    # Redis (Upstash)
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # Postgres (Supabase / asyncpg — use postgresql:// not postgresql+asyncpg://)
    database_url: str = ""

    # RAG
    embedding_model: str = "text-embedding-3-small"
    rag_top_k: int = 3


settings = Settings()
