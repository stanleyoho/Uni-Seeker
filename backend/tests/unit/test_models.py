from datetime import date
from decimal import Decimal

from app.models.enums import Market
from app.models.price import StockPrice
from app.models.stock import Stock


def test_market_enum_values() -> None:
    assert Market.TW_TWSE.value == "TW_TWSE"
    assert Market.TW_TPEX.value == "TW_TPEX"
    assert Market.US_NYSE.value == "US_NYSE"
    assert Market.US_NASDAQ.value == "US_NASDAQ"


def test_stock_model_creation() -> None:
    stock = Stock(
        symbol="2330.TW",
        name="台積電",
        market=Market.TW_TWSE,
        industry_id=None,
    )
    assert stock.symbol == "2330.TW"
    assert stock.name == "台積電"
    assert stock.market == Market.TW_TWSE
    assert stock.industry_id is None


def test_stock_price_model_creation() -> None:
    price = StockPrice(
        stock_id=1,
        date=date(2026, 4, 22),
        open=Decimal("885.00"),
        high=Decimal("892.00"),
        low=Decimal("880.00"),
        close=Decimal("890.00"),
        volume=25_000_000,
        change=Decimal("5.00"),
        change_percent=Decimal("0.56"),
    )
    assert price.close == Decimal("890.00")
    assert price.volume == 25_000_000
    assert price.change == Decimal("5.00")


def test_user_has_stripe_fields() -> None:
    """User model must expose stripe_customer_id, stripe_subscription_id,
    subscription_expires_at as optional fields."""
    from app.models.user import User

    annotations = User.__mapper__.columns.keys()
    assert "stripe_customer_id" in annotations
    assert "stripe_subscription_id" in annotations
    assert "subscription_expires_at" in annotations


def test_settings_has_stripe_keys() -> None:
    """Settings must expose stripe_secret_key, stripe_webhook_secret and price IDs."""
    from app.config import Settings

    fields = Settings.model_fields
    assert "enable_monetization" in fields
    assert "stripe_secret_key" in fields
    assert "stripe_webhook_secret" in fields
    assert "stripe_price_id_basic" in fields
    assert "stripe_price_id_pro" in fields
