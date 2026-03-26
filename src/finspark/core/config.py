"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "FinSpark Integration Engine"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = "sqlite+aiosqlite:///./finspark.db"

    # Security
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60
    encryption_key: str = "change-me-in-production"

    # File uploads
    upload_dir: Path = Path("./uploads")
    max_upload_size_mb: int = 50

    # AI (optional)
    llm_api_key: str = ""
    openai_api_key: str = ""
    ai_enabled: bool = False

    model_config = {"env_prefix": "FINSPARK_", "env_file": ".env"}


settings = Settings()
