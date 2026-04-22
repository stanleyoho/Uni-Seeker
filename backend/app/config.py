from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/uni_seeker"
    database_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # TWSE / TPEX
    twse_base_url: str = "https://openapi.twse.com.tw/v1"
    tpex_base_url: str = "https://www.tpex.org.tw/openapi/v1"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # App
    app_name: str = "Uni-Seeker"
    debug: bool = False

    model_config = {"env_prefix": "UNI_", "env_file": ".env"}


settings = Settings()
