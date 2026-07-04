from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    active_pack: str = "dental_saas"
    log_level: str = "INFO"
    environment: str = "development"

    # Escape hatch: allow booting in production with empty Vapi secrets
    # (endpoints publicly callable). Off by default — production fails closed.
    allow_insecure_public_endpoints: bool = False

    # Reject request bodies larger than this (DoS / LLM-cost amplification guard).
    # Vapi turn payloads are a few KB; 1 MB leaves room for very long transcripts.
    max_request_bytes: int = 1_000_000

    # Model routing — Sonnet for response generation (instruction-following matters),
    # Haiku for classification (one-line output, cheap)
    generation_model: str = "claude-sonnet-4-6"
    classifier_model: str = "claude-haiku-4-5-20251001"
    generation_temperature: float = 0.4

    # Voice latency budgets — a hung upstream call means dead air on the phone,
    # so these are much tighter than SDK defaults (10 min).
    generation_timeout_seconds: float = 30.0
    classifier_timeout_seconds: float = 10.0

    # Redis (Upstash)
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # Vapi shared secrets — when set, the matching endpoints require the right header.
    # Leave empty in dev to skip auth (CI tests run without these).
    vapi_llm_secret: str = ""      # Authorization: Bearer <this>   on /vapi/llm*
    vapi_server_secret: str = ""   # x-vapi-secret: <this>          on /vapi/server

    # Postgres (Supabase / asyncpg — use postgresql:// not postgresql+asyncpg://)
    database_url: str = ""

    # RAG
    embedding_model: str = "text-embedding-3-small"
    rag_top_k: int = 3

    # Calendar integration — which provider a pack uses is set per-pack
    # (pack.calendar.provider); the secret lives here. Empty ⇒ that provider is
    # unavailable and booking degrades to DB-only (like a missing DB pool).
    calcom_api_key: str = ""
    calcom_base_url: str = "https://api.cal.com/v1"
    # Google service-account credentials: either the raw JSON blob or a path to it.
    google_calendar_credentials_json: str = ""


settings = Settings()
