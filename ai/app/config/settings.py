from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Mesosfer Agentic Discovery"
    debug: bool = False

    # Active LLM provider: "custom", "ollama", or "amd"
    llm_provider: str = "custom"

    # AMD Token Factory Configuration (OpenAI-compatible; key format "rc-" + 48 hex)
    amd_base_url: str = "https://developer.amd.com.cn/radeon/api/v1"
    amd_api_key: str = ""
    amd_default_model: str = "DeepSeek-V4-Flash"
    amd_fast_model: str = "DeepSeek-V4-Flash"
    amd_reasoning_model: str = "DeepSeek-V4-Flash"
    amd_timeout: float = 600.0

    # Global LLM limits (AMD shared team key: 30 RPM, 8 concurrent)
    llm_max_concurrency: int = 6
    llm_rpm_limit: int = 30
    llm_max_retries: int = 4
    # Products scored per trust LLM call (batched to stay inside the shared RPM limit)
    trust_batch_size: int = 8

    # Discovery (Stage 1) search + page extraction
    # Optional override (comma-separated domains); empty = use the per-country list in app/services/regions.py
    discovery_sites: str = ""
    discovery_max_candidates: int = 30
    discovery_page_timeout_ms: int = 15000
    discovery_render_wait_ms: int = 4000
    discovery_concurrency: int = 10
    discovery_search_concurrency: int = 3
    # Max share of the candidate target filled by Google Shopping items (rest goes to web product pages; unused slots are backfilled)
    discovery_shopping_share: float = 0.6

    # "marketplace" searches stores directly; "serpapi" uses its API.
    search_provider: str = "marketplace"
    serpapi_api_key: str = ""
    # Empty = derive from the request country (no country: gl "us", hl "en"); set only to pin a default for country-less requests
    serpapi_gl: str = ""
    serpapi_hl: str = ""
    serpapi_timeout: float = 20.0
    # Top N shopping candidates (after dedup) whose merchant offer link is resolved via SerpAPI; 0 disables
    serpapi_resolve_top_n: int = 10
    # Hard cap on offer resolutions per request: backfills past top N only while too few candidates have a store link
    serpapi_resolve_max: int = 15

    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"

    # Ollama Provider Configuration
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "gemma4:31b-cloud"
    ollama_timeout: float = 60.0

    # Custom OpenAI-compatible Provider Configuration (bandelbanget.xyz)
    custom_llm_base_url: str = "https://bandelbanget.xyz/v1"
    custom_llm_api_key: str = ""
    custom_llm_default_model: str = "deepseek-v4-flash"
    custom_llm_fast_model: str = "kimi-k2.5"
    custom_llm_vision_model: str = "deepseek-v4-flash-vision-exp"
    custom_llm_reasoning_model: str = "deepseek-v4-pro"
    custom_llm_timeout: float = 60.0


settings = Settings()
