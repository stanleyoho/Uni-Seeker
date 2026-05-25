import enum

from sqlalchemy.dialects.postgresql import ENUM as PgEnum


class Market(enum.StrEnum):
    TW_TWSE = "TW_TWSE"
    TW_TPEX = "TW_TPEX"
    US_NYSE = "US_NYSE"
    US_NASDAQ = "US_NASDAQ"


class UserTier(enum.StrEnum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"


class NotificationStatus(enum.StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


# PostgreSQL native ENUM types for use in mapped_column()
MarketType = PgEnum(
    Market,
    name="market_enum",
    create_type=False,  # Created in migration
)

UserTierType = PgEnum(
    UserTier,
    name="user_tier_enum",
    create_type=False,
    # Python enum NAME (e.g. "FREE") differs from VALUE ("free") — PG enum
    # was created with the lowercase values, so we must serialize value, not name.
    values_callable=lambda obj: [e.value for e in obj],
)

NotificationStatusType = PgEnum(
    NotificationStatus,
    name="notification_status_enum",
    create_type=False,
    values_callable=lambda obj: [e.value for e in obj],
)
