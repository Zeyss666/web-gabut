from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "SocialPoster"
    secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 hari

    database_url: str = "sqlite:///./socialposter.db"
    upload_dir: str = "./uploads"
    base_url: str = "http://localhost:8000"

    # Meta (Facebook + Instagram)
    meta_app_id: str = ""
    meta_app_secret: str = ""

    # TikTok
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
