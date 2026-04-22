from datetime import date
from decimal import Decimal

from app.models.enums import Market
from app.models.stock import Stock
from app.models.price import StockPrice


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
        industry="半導體業",
    )
    assert stock.symbol == "2330.TW"
    assert stock.name == "台積電"
    assert stock.market == Market.TW_TWSE
    assert stock.industry == "半導體業"


def test_stock_price_model_creation() -> None:
    price = StockPrice(
        symbol="2330.TW",
        market=Market.TW_TWSE,
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
