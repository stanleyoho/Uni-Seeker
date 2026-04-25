import enum

from sqlalchemy.dialects.postgresql import ENUM as PgEnum


class Market(str, enum.Enum):
    TW_TWSE = "TW_TWSE"
    TW_TPEX = "TW_TPEX"
    US_NYSE = "US_NYSE"
    US_NASDAQ = "US_NASDAQ"


class UserTier(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"


class NotificationStatus(str, enum.Enum):
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
)

NotificationStatusType = PgEnum(
    NotificationStatus,
    name="notification_status_enum",
    create_type=False,
)
