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

    # Auth rate limiter (per IP, per /auth endpoint).
    # Production: 5 attempts per 60s. Set to 0 to disable entirely (used by e2e).
    auth_rate_limit_max: int = 5  # UNI_AUTH_RATE_LIMIT_MAX
    auth_rate_limit_window_seconds: float = 60.0  # UNI_AUTH_RATE_LIMIT_WINDOW_SECONDS

    # CORS — additional comma-separated origins to allow on top of the
    # built-in defaults (localhost:3000 / :3001 / :3002 with both
    # localhost & 127.0.0.1 spellings). Empty string disables the
    # extension. Production override should list the prod web origins
    # only — the defaults already cover local dev + e2e.
    #
    # Why an extension list rather than full replacement? Every dev
    # workflow (`npm run dev`, the docker e2e stack, ad-hoc 3001 fallback
    # when 3000 is busy) needs the localhost defaults; making CORS purely
    # env-driven would silently break local UIs whenever the env var is
    # forgotten. The split keeps prod tight without paying that tax.
    cors_extra_origins: str = ""  # UNI_CORS_EXTRA_ORIGINS

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

    # SEC EDGAR — required `User-Agent` per SEC fair-use policy. Must
    # contain a real contact email or EDGAR returns 403 at runtime. The
    # default below matches the existing hard-coded fallback inside
    # ``EdgarClient.__init__`` so behaviour is unchanged when the env var
    # is unset; operators SHOULD override per-deployment to their own
    # contact address. Read by the F13 sync task that constructs an
    # ``EdgarClient`` from the scheduler context.
    sec_edgar_user_agent: str = "Uni-Seeker stanly7768@gmail.com"  # UNI_SEC_EDGAR_USER_AGENT

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
