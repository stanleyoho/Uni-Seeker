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

    # FinMind
    finmind_api_url: str = "https://api.finmindtrade.com/api/v4"
    finmind_api_token: str = ""

    # Telegram (legacy single-channel notifier used by app.modules.notifier)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Telegram (Uni-Seeker per-user fan-out — 13F new-filing alerts).
    # Kept separate so the 13F notifier has its own bot identity and
    # the legacy single-channel notifier above continues to work
    # untouched. Empty string disables 13F TG notifications globally.
    uni_telegram_bot_token: str = ""
    # Frontend URL used when building "看詳情" links in TG messages.
    app_url: str = "http://localhost:3000"

    # Security
    jwt_secret_key: str = ""  # MUST set via UNI_JWT_SECRET_KEY env var
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # App
    app_name: str = "Uni-Seeker"
    debug: bool = False

    # Feature toggle: when False, require_tier passes all users as PRO
    enable_monetization: bool = False  # UNI_ENABLE_MONETIZATION

    # Stripe configuration
    stripe_secret_key: str = ""  # UNI_STRIPE_SECRET_KEY
    stripe_webhook_secret: str = ""  # UNI_STRIPE_WEBHOOK_SECRET
    stripe_price_id_basic: str = ""  # UNI_STRIPE_PRICE_ID_BASIC
    stripe_price_id_pro: str = ""  # UNI_STRIPE_PRICE_ID_PRO

    # OpenFIGI — CUSIP → ticker resolution for 13F backfill (Phase 3).
    # None / empty → free tier (25 req/min, 10 mappings/call). Auth → 250
    # req/min, 100 mappings/call, 60k/day. Wired by run_cusip_backfill.py
    # when --use-figi is passed.
    openfigi_api_key: str | None = None  # UNI_OPENFIGI_API_KEY

    # ── Email notification channel (Round 14) ─────────────────────────
    #
    # SMTP send-only configuration. We use Python's stdlib ``smtplib`` so
    # no new dependency lands; the operator points us at any SMTP server
    # (Gmail, SendGrid, AWS SES, etc.). All fields default to None /
    # safe values so a missing config short-circuits to a no-op in
    # ``email_sender.send_email`` — never raises into the caller.
    #
    # Why not a third-party HTTP API (Resend / SendGrid)? Adding a dep
    # for a single send path is overkill. SMTP is universal, well
    # understood, and the failure surface (transport + auth + 5xx) is
    # the same shape we already log for Telegram.
    uni_smtp_host: str | None = None  # e.g. smtp.gmail.com
    uni_smtp_port: int = 587  # 587 STARTTLS, 465 SSL, 25 plain
    uni_smtp_user: str | None = None  # SMTP AUTH username
    uni_smtp_password: str | None = None  # SMTP AUTH password / app pwd
    uni_smtp_from_addr: str | None = None  # MAIL FROM (must be set)
    uni_smtp_use_tls: bool = True  # STARTTLS on submission port

    model_config = {"env_prefix": "UNI_", "env_file": ".env"}


settings = Settings()
