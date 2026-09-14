from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Clinical Decision Forest Bench"
    environment: str = "development"
    # Local Arena data must survive uvicorn reloads. PostgreSQL remains
    # available through environment overrides for deployed installations.
    database_url: str = "sqlite:///data/clincforestbench.db"
    arena_repository: str = "sqlite"
    research_api_key: str = "local-research-only"
    export_dir: Path = Path("data/exports")
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: int = 180
    model_config = SettingsConfigDict(
        env_file=(".env", "test/.env"), extra="ignore"
    )
